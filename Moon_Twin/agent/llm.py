"""
MOON LLM Client — Ollama-backed (OpenAI-compatible) LLM integration.

Provides:
- OllamaClient: wraps openai.AsyncOpenAI pointed at local Ollama
- Configurable model, base URL, temperature
- Conversation history (list of role/content messages)
- Tool-calling support (function calling via Ollama)
- Streaming via async generator
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator, Callable, Sequence

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# ---------------------------------------------------------------------------
# Default configuration (override via env or kwargs)
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_URL = os.getenv("MOON_OLLAMA_URL", "http://127.0.0.1:11434/v1")
DEFAULT_MODEL = os.getenv("MOON_MODEL", "qwen3:0.6b")
DEFAULT_TEMPERATURE = float(os.getenv("MOON_TEMPERATURE", "0.7"))
DEFAULT_MAX_TOKENS = int(os.getenv("MOON_MAX_TOKENS", "4096"))
DEFAULT_TIMEOUT = float(os.getenv("MOON_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------

class OllamaClient:
    """
    Async LLM client backed by local Ollama (OpenAI-compatible API).

    Usage:
        client = OllamaClient(model="qwen3:0.6b")
        response = await client.chat(message="Hello", system="You are helpful.")
        # or with streaming:
        async for token in client.stream(message="Hello", system="..."):
            print(token, end="", flush=True)
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ):
        if not HAS_OPENAI:
            raise RuntimeError(
                "openai package required for LLM integration. "
                "Install with: pip install openai"
            )

        self.model = model or DEFAULT_MODEL
        self.base_url = base_url or DEFAULT_OLLAMA_URL
        self.temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key="not-needed",
            timeout=self.timeout,
        )
        self._conversation: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    def reset_conversation(self) -> None:
        """Clear conversation history."""
        self._conversation.clear()

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self._conversation.append({"role": role, "content": content})

    def get_conversation(self) -> list[dict[str, str]]:
        """Return a copy of the conversation history."""
        return list(self._conversation)

    def set_conversation(self, messages: list[dict[str, str]]) -> None:
        """Replace conversation history."""
        self._conversation = list(messages)

    # ------------------------------------------------------------------
    # Chat completion (non-streaming)
    # ------------------------------------------------------------------

    async def chat(
        self,
        message: str,
        system: str | None = None,
        history: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Send a chat completion request and return the full response.

        Args:
            message: User message content.
            system: System prompt (overrides conversation history system message).
            history: Prior conversation messages (user + assistant).
            tools: Optional list of tool definitions for function calling.

        Returns:
            Dict with keys: content, role, model, tool_calls (if any).
        """
        messages = []

        # System prompt
        if system:
            messages.append({"role": "system", "content": system})
        elif history:
            # Check if first message is system
            if history and history[0].get("role") == "system":
                messages.append(history[0])
                messages.extend(history[1:])
            else:
                messages.extend(history)
        else:
            messages.append({"role": "system", "content": "You are a helpful assistant."})

        # User message
        messages.append({"role": "user", "content": message})

        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            params["tools"] = tools

        try:
            resp = await self._client.chat.completions.create(**params)
            choice = resp.choices[0]
            message_obj = choice.message

            result: dict[str, Any] = {
                "content": message_obj.content or "",
                "role": message_obj.role,
                "model": self.model,
                "tool_calls": [],
            }

            # Extract tool calls if present
            if hasattr(message_obj, "tool_calls") and message_obj.tool_calls:
                for tc in message_obj.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })

            return result

        except Exception as e:
            return {
                "content": f"Error: {e}",
                "role": "assistant",
                "model": self.model,
                "tool_calls": [],
                "error": True,
            }

    # ------------------------------------------------------------------
    # Streaming chat completion
    # ------------------------------------------------------------------

    async def stream(
        self,
        message: str,
        system: str | None = None,
        history: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream a chat completion token by token.

        Yields dicts with keys: token, role, model, done, tool_calls (when complete).
        """
        messages = []

        if system:
            messages.append({"role": "system", "content": system})
        elif history:
            if history and history[0].get("role") == "system":
                messages.append(history[0])
                messages.extend(history[1:])
            else:
                messages.extend(history)
        else:
            messages.append({"role": "system", "content": "You are a helpful assistant."})

        messages.append({"role": "user", "content": message})

        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if tools:
            params["tools"] = tools

        try:
            resp = await self._client.chat.completions.create(**params)
            try:
                async for chunk in resp:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield {
                            "token": delta.content,
                            "role": "assistant",
                            "model": self.model,
                            "done": False,
                        }
                    if chunk.choices[0].finish_reason:
                        yield {
                            "token": "",
                            "role": "assistant",
                            "model": self.model,
                            "done": True,
                            "finish_reason": chunk.choices[0].finish_reason,
                        }
                        return
            except (RuntimeError, GeneratorExit, StopAsyncIteration):
                pass  # Stream ended
        except Exception as e:
            yield {
                "token": f"Error: {e}",
                "role": "assistant",
                "model": self.model,
                "done": True,
                "error": True,
            }

    # ------------------------------------------------------------------
    # Tool-calling loop (LLM decides to call tools, we execute and feed back)
    # ------------------------------------------------------------------

    async def chat_with_tools(
        self,
        message: str,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Callable[..., Any] | None = None,
        max_iterations: int = 5,
    ) -> dict[str, Any]:
        """
        Chat with tool-calling support.

        The LLM may request tool calls. We execute them via tool_executor
        and feed results back until the LLM produces a final response.

        Args:
            message: User message.
            system: System prompt.
            tools: List of tool definitions (name, description, parameters).
            tool_executor: Async callable that takes a tool_call dict and returns result dict.
            max_iterations: Max tool-call rounds before giving up.

        Returns:
            Final response dict with content, role, model, and tool_results.
        """
        if not tools or not tool_executor:
            # Fall back to simple chat
            return await self.chat(message, system=system, tools=tools)

        # Build initial messages
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})

        tool_results: list[dict] = []
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            params: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "tools": tools,
            }

            try:
                resp = await self._client.chat.completions.create(**params)
                choice = resp.choices[0]
                msg = choice.message

                # Check for tool calls
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # Add assistant message with tool calls to history
                    assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        assistant_msg["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in msg.tool_calls
                        ]
                    messages.append(assistant_msg)

                    # Execute each tool call
                    for tc in msg.tool_calls:
                        tool_call: dict[str, Any] = {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        result = await tool_executor(tool_call)
                        tool_results.append(result)

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(result),
                            "tool_call_id": tc.id,
                        })

                    # Continue loop — LLM sees tool results and may call more tools or respond
                    continue

                # No tool calls — final response
                return {
                    "content": msg.content or "",
                    "role": msg.role,
                    "model": self.model,
                    "tool_results": tool_results,
                }

            except Exception as e:
                return {
                    "content": f"Error: {e}",
                    "role": "assistant",
                    "model": self.model,
                    "tool_results": tool_results,
                    "error": True,
                }

        # Max iterations reached
        return {
            "content": "Max tool iterations reached without final response.",
            "role": "assistant",
            "model": self.model,
            "tool_results": tool_results,
            "error": True,
        }


# ---------------------------------------------------------------------------
# Tool definition helper
# ---------------------------------------------------------------------------

def tool_def(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """
    Create a tool definition for function calling.

    Args:
        name: Tool name.
        description: What the tool does.
        parameters: JSON Schema for parameters.

    Returns:
        Dict suitable for the 'tools' parameter of chat completions.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


# ---------------------------------------------------------------------------
# Convenience: create client from env or defaults
# ---------------------------------------------------------------------------

def create_client(**kwargs) -> OllamaClient:
    """Create an OllamaClient with defaults from env or kwargs."""
    return OllamaClient(**kwargs)
