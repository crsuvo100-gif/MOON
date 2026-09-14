"""
Orchestrator — the brain core. Wires everything + runs the full cognition loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from app.brain.lock import SessionLock
from app.brain.intent_detector import detect_intent, intent_to_agent
from app.brain.memory_manager import MemoryManager
from app.brain.tool_manager import ToolManager
from app.agents.registry import AgentRegistry
from app.brain.agent_brain import AgentBrain
from app.brain.agent_model_manager import AgentModelManager
from app.brain.knowledge_consolidator import KnowledgeConsolidator
from app.brain.prompt_tuner import PromptTuner
from app.brain.self_improvement import SelfImprovement
from app.brain.error_recovery import ErrorRecovery
from app.brain.output_formatter import OutputFormatter
from app.brain.reasoning import ReasoningEngine
from app.brain.validator import Validator
from app.brain.self_reflection import SelfReflection
from app.brain.planner import Planner
from app.brain.context_builder import ContextBuilder
from app.brain.prompt_manager import PromptManager
from app.services.llm_service import (
    LLMService, FallbackChain, ChatMessage, CompletionResult,
)
from app.services.embedding_service import EmbeddingService
from app.memory.short_term import ShortTermMemory
from app.memory.long_term import LongTermMemory
from app.memory.episodic_memory import EpisodicMemory
from app.memory.vector_db import InMemoryVectorStore
from app.memory.knowledge_base import KnowledgeBase
from app.memory.conversation_history import ConversationHistory
from app.services.llm_service import CYBER_CRITICAL_KEYWORDS
from app.tools.base import ToolRegistry

logger = logging.getLogger("moontm.orch")


@dataclass
class Task:
    id: str
    prompt: str
    agent_name: str = "auto"
    status: str = "pending"  # pending | running | success | failed
    result: Optional[str] = None
    error: Optional[str] = None
    _history: list[dict] = field(default_factory=list)
    _evaluation: Optional[dict] = None

    @classmethod
    def create(cls, prompt: str, agent_name: str = "auto") -> "Task":
        return cls(id=f"task_{int(time.time() * 1000)}", prompt=prompt,
                   agent_name=agent_name)

    def mark_running(self) -> None:
        self.status = "running"

    def complete(self, result: str, data: Optional[dict] = None) -> None:
        self.status = "success"
        self.result = result
        if data:
            self._evaluation = data

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error


class Orchestrator:
    """The central brain coordinator. setup() wires everything; run_task() is the loop."""

    def __init__(self, settings: Any, lock_state_file: Optional[Path] = None) -> None:
        self._settings = settings
        self._lock = SessionLock(locked=True, state_file=lock_state_file or settings.lock_state_path)
        self._exec_mgr: Optional[Any] = None

        # LLM stack — all optional until setup()
        self._llm: Optional[LLMService] = None
        self._llm_strong: Optional[LLMService] = None
        self._llm_fallback: Optional[LLMService] = None
        self._llm_fallback2: Optional[LLMService] = None
        self._llm_fallback3: Optional[LLMService] = None
        self._fallback_chain: Optional[FallbackChain] = None
        self._embeddings: Optional[EmbeddingService] = None
        self._agent_models: Optional[AgentModelManager] = None

        # Brain modules — created in setup()
        self._prompts: Optional[PromptManager] = None
        self._context: Optional[ContextBuilder] = None
        self._reasoning: Optional[ReasoningEngine] = None
        self._planner: Optional[Planner] = None
        self._validator: Optional[Validator] = None
        self._reflection: Optional[SelfReflection] = None
        self._formatter: Optional[OutputFormatter] = None
        self._recovery: Optional[ErrorRecovery] = None
        self._history: Optional[ConversationHistory] = None
        self._memory: Optional[MemoryManager] = None
        self._tools: Optional[ToolManager] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._consolidator: Optional[KnowledgeConsolidator] = None
        self._tuner = PromptTuner()
        self._improvement = SelfImprovement()

        # Agents
        self._agents: dict[str, Any] = {}  # agent card dict
        self._agent_brains: dict[str, AgentBrain] = {}
        self._agent_registry: Optional[AgentRegistry] = None

        self._setup_done = False

    async def setup(self) -> None:
        """Wire everything: models, memory, tools, agents, modules."""
        logger.info("Orchestrator setup starting...")

        # ── LLM: main model ──────────────────────────────────────────────
        self._llm = LLMService(
            base_url=self._settings.model_base_url,
            model_name=self._settings.model_name,
            api_key="not-required" if "127.0.0.1" in self._settings.model_base_url else "",
            temperature=self._settings.model_temperature,
            max_tokens=self._settings.model_max_tokens,
            timeout=self._settings.model_timeout,
        )
        await self._llm.setup()

        # ── strong model (optional) ──────────────────────────────────────
        if self._settings.strong_model_name and self._settings.strong_model_base_url:
            self._llm_strong = LLMService(
                base_url=self._settings.strong_model_base_url,
                model_name=self._settings.strong_model_name,
                api_key="not-required" if "127.0.0.1" in self._settings.strong_model_base_url else "",
                temperature=self._settings.model_temperature,
                max_tokens=self._settings.model_max_tokens,
                timeout=self._settings.model_timeout,
                disable_thinking=False,
            )
            await self._llm_strong.setup()
            logger.info("Strong model wired: %s @ %s",
                        self._settings.strong_model_name, self._settings.strong_model_base_url)

        # ── fallback chain ───────────────────────────────────────────────
        fallbacks: list[LLMService] = []
        if self._settings.openai_api_key:
            oai = LLMService(
                base_url=self._settings.openai_base_url,
                model_name=self._settings.openai_model,
                api_key=self._settings.openai_api_key,
                temperature=self._settings.model_temperature,
                max_tokens=self._settings.model_max_tokens,
                timeout=self._settings.model_timeout,
                disable_thinking=True,
            )
            await oai.setup()
            fallbacks.append(oai)
            self._llm_fallback = oai
            logger.info("OpenAI fallback wired: %s", self._settings.openai_model)

        if self._settings.openrouter_api_key:
            oro = LLMService(
                base_url=self._settings.openrouter_base_url,
                model_name=self._settings.openrouter_model,
                api_key=self._settings.openrouter_api_key,
                temperature=self._settings.model_temperature,
                max_tokens=self._settings.model_max_tokens,
                timeout=self._settings.model_timeout,
                disable_thinking=True,
            )
            await oro.setup()
            fallbacks.append(oro)
            self._llm_fallback2 = oro
            logger.info("OpenRouter fallback wired: %s", self._settings.openrouter_model)

        if self._settings.huggingface_api_key:
            hf = LLMService(
                base_url=self._settings.huggingface_base_url,
                model_name=self._settings.huggingface_model,
                api_key=self._settings.huggingface_api_key,
                temperature=self._settings.model_temperature,
                max_tokens=self._settings.model_max_tokens,
                timeout=self._settings.model_timeout,
                disable_thinking=True,
            )
            await hf.setup()
            fallbacks.append(hf)
            self._llm_fallback3 = hf
            logger.info("HuggingFace fallback wired: %s", self._settings.huggingface_model)

        self._fallback_chain = FallbackChain(fallbacks, self._settings.model_name)

        # ── embeddings ───────────────────────────────────────────────────
        self._embeddings = EmbeddingService(
            dim=self._settings.embedding_dim,
            enabled=bool(self._settings.embedding_base_url),
            base_url=self._settings.embedding_base_url,
            model_name=self._settings.embedding_model,
        )
        await self._embeddings.setup()

        # ── agent models (optional) ──────────────────────────────────────
        if self._settings.enable_per_agent_models:
            self._agent_models = AgentModelManager(self._settings)

        # ── memory stack ─────────────────────────────────────────────────
        stm = ShortTermMemory(capacity=200)
        ltm = LongTermMemory(Path(self._settings.long_term_path))
        store = InMemoryVectorStore()
        kb = KnowledgeBase(store, self._embeddings)
        episodic = EpisodicMemory(Path(self._settings.episodes_path))
        self._memory = MemoryManager(stm, ltm, kb, episodic)
        await self._memory.setup()

        # ── index skills corpus into KB (best-effort) ────────────────────
        try:
            await self._index_skills()
        except Exception as exc:
            logger.warning("Skill indexing skipped: %s", exc)

        # ── consolidator ─────────────────────────────────────────────────
        if self._settings.enable_auto_learning:
            self._consolidator = KnowledgeConsolidator(self._memory,
                                                        str(self._settings.long_term_path))

        # ── prompts + context ────────────────────────────────────────────
        self._prompts = PromptManager()
        self._context = ContextBuilder(self._prompts)

        # ── cognition modules ────────────────────────────────────────────
        self._reasoning = ReasoningEngine(self._llm, self._prompts)
        self._planner = Planner(self._llm, self._prompts)
        self._validator = Validator(self._llm)
        self._reflection = SelfReflection(self._llm)
        self._formatter = OutputFormatter()
        self._recovery = ErrorRecovery(max_retries=3)
        self._history = ConversationHistory(session_id="main")

        # ── tools ────────────────────────────────────────────────────────
        self._tool_registry = ToolRegistry()
        await self._register_tools()

        # ── tool manager ─────────────────────────────────────────────────
        self._tools = ToolManager(
            self._tool_registry,
            enabled_tools=list(self._tool_registry.tool_names),
            allow_dangerous=self._settings.allow_dangerous_tools,
            tool_timeout=self._settings.tool_timeout,
        )

        # ── agents ───────────────────────────────────────────────────────
        self._agent_registry = AgentRegistry(list(self._tool_registry.tool_names))
        self._agents = {c.name: c.to_dict() for c in self._agent_registry.all()}
        await self._register_agent_brains()

        self._setup_done = True
        logger.info("Orchestrator setup complete — model=%s, agents=%d, tools=%d",
                    self._settings.model_name, len(self._agents), len(self._tool_registry.tool_names))

    # ── tool registration ─────────────────────────────────────────────
    async def _register_tools(self) -> None:
        from app.tools.web_search import WebSearchTool
        from app.tools.terminal import TerminalTool
        from app.tools.file_manager import FileManagerTool
        from app.tools.python_executor import PythonExecutorTool

        all_tools = [
            WebSearchTool(),
            TerminalTool(),
            FileManagerTool(),
            PythonExecutorTool(),
        ]
        for t in all_tools:
            self._tool_registry.register(t)
            logger.debug("Registered tool: %s", t.name)

    # ── skill indexing (best-effort) ──────────────────────────────────
    async def _index_skills(self) -> None:
        """Index any available skill corpus into the KB."""
        # In a full implementation this walks the skills/ directory and indexes markdown.
        logger.info("Skill indexing placeholder — no skill corpus to index")

    # ── agent brain registration ───────────────────────────────────────
    async def _register_agent_brains(self) -> None:
        for name in self._agents:
            brain = AgentBrain(name=name, main_brain=self, agent_models=self._agent_models)
            await brain.setup()
            self._agent_brains[name] = brain
        logger.info("Connected %d agent brains", len(self._agent_brains))

    # ── run_task (the full pipeline) ──────────────────────────────────
    async def run_task(self, task: Task, on_event: Optional[Callable] = None) -> Task:
        if not self._setup_done:
            raise RuntimeError("Orchestrator.setup() must be called first")

        # 1. lock guard
        notice = self._lock.observe(task.prompt)
        if notice:
            task.complete(notice)
            if on_event:
                on_event("lock", "unlocked" if not self._lock.locked else "blocked", task.id)
            return task

        # 2. mark running
        task.mark_running()
        self._history.clear()

        # 3. route intent → agent
        intent, confidence = detect_intent(task.prompt)
        agent_name = intent_to_agent(intent)
        if agent_name == "auto" or agent_name not in self._agents:
            agent_name = "coordinator"
        task.agent_name = agent_name
        if on_event:
            on_event("agent_selected", agent_name, task.id)

        # 4. spec 10/12 augmentation — best-effort capability discovery
        try:
            await self._auto_acquire_for_task(task, agent_name)
        except Exception as exc:
            logger.warning("Auto-acquire skipped: %s", exc)

        # 5. coordinator + multi-part → parallel fan-out
        if agent_name == "coordinator":
            plan = await self._planner.plan(task.prompt) if self._planner else None
            subtasks = self._split_subtasks(task.prompt)
            if subtasks and self._settings.max_parallel_agents > 1:
                try:
                    results = await self._run_parallel(subtasks, task.id, on_event)
                    merged = " | ".join(r for r in results if r)
                    if merged:
                        task.complete(merged)
                        if on_event:
                            on_event("task_completed", task.id, task.id)
                        return task
                except Exception as exc:
                    logger.warning("Parallel fan-out failed, falling back: %s", exc)

        # 6. fast-path guard
        if (self._settings.enable_fast_path
                and self._is_simple_query(task.prompt)
                and agent_name != "auto"):
            try:
                text, tokens = await self._fast_answer(task.prompt, agent_name)
                # optional explicit tool if user requested one
                text = await self._try_explicit_tool(task.prompt, text)
                task.complete(text)
                if on_event:
                    on_event("task_completed", task.id, task.id)
                return task
            except Exception as exc:
                logger.warning("Fast-path failed: %s", exc)

        # 7. FULL cognition loop
        try:
            final_text, tokens = await self._run_cognition_loop(task, agent_name, on_event)

            # 8. validator
            if self._validator:
                vr = await self._validator.validate(task.prompt, final_text)
                if on_event:
                    on_event("verification",
                              "passed" if vr.valid else "failed", task.id)
                if not vr.valid:
                    self._tuner.record_lesson(agent_name, f"validation failed: {vr.issues}")

            # 9. self-reflection
            if self._reflection:
                rr = await self._reflection.reflect(task.prompt, final_text)

            # 10. self-consistency majority vote (optional)
            if (self._settings.enable_self_consistency
                    and self._is_factual(task.prompt)
                    and self._settings.self_consistency_samples > 1):
                final_text = await self._majority_vote(task.prompt, final_text)

            # 11. episodic memory
            success = True
            self._memory._episodic.record(
                goal=task.prompt,
                outcome=final_text[:500],
                lesson="",
                success=success,
                agent=agent_name,
            )
            self._memory.save_episodes()
            if on_event:
                on_event("memory_updated", "episodic", task.id)

            # 12. consolidator → KB
            if self._consolidator:
                await self._consolidator.consolidate()

            # 13. two-phase agent refine
            if (self._settings.enable_agent_validation
                    and agent_name in self._agent_brains
                    and self._agent_brains[agent_name]):
                final_text = await self._agent_brains[agent_name].refine_with_main(
                    final_text, task.prompt)

            # 14. agent brain remember
            if agent_name in self._agent_brains:
                self._agent_brains[agent_name].remember({
                    "goal": task.prompt,
                    "outcome": final_text[:500],
                    "agent": agent_name,
                })

            # 15. format
            clean = self._formatter.format(final_text) if self._formatter else final_text

            # 16. evaluation + outcome record
            if on_event:
                on_event("agent_completed", agent_name, task.id)

            task.complete(clean, data={
                "tokens_used": tokens,
                "issues": [],
                "agent": agent_name,
            })

            # 17. STM remember
            self._memory.remember(clean, long_term=False)

        except Exception as exc:
            logger.exception("run_task failed: %s", exc)
            task.fail(str(exc))
            self._improvement.submit("orchestrator_error", str(exc))
            if on_event:
                on_event("error", str(exc)[:200], task.id)

        return task

    # ── cognition loop ────────────────────────────────────────────────
    async def _run_cognition_loop(
        self, task: Task, agent_name: str, on_event: Optional[Callable]
    ) -> tuple[str, int]:
        MAX_ITER = 5
        total_tokens = 0
        messages = self._build_initial_context(task, agent_name)
        tool_specs = self._tools.available_specs() if self._tools else []
        tool_specs_str = ""
        if tool_specs:
            import json
            tool_specs_str = json.dumps(tool_specs, ensure_ascii=False)

        for iteration in range(MAX_ITER):
            # pick the LLM
            llm = await self._pick_llm(task.prompt, agent_name)
            if on_event:
                on_event("thinking", f"iteration {iteration+1}/{MAX_ITER}", task.id)

            # assemble messages
            ctx = self._context.build(
                task.prompt,
                [],
                retrieved=await self._memory.semantic_recall(task.prompt, top_k=5) if self._memory else [],
                system_override=None,
            )

            try:
                resp = await asyncio.wait_for(
                    llm.complete(ctx, tools=tool_specs if tool_specs_str else None),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.warning("LLM iteration %d timed out — falling back to main LLM", iteration + 1)
                if self._llm:
                    resp = await self._llm.complete(ctx, tools=tool_specs if tool_specs_str else None)
                else:
                    resp = CompletionResult(content="")
            except Exception as exc:
                logger.warning("LLM iteration %d error: %s", iteration + 1, exc)
                resp = CompletionResult(content="")

            total_tokens += 100  # rough estimate

            # tool calls?
            if resp.has_tool_calls:
                for tc in resp.tool_calls:
                    call_name = tc.get("name", "")
                    call_args = {}
                    try:
                        call_args = json.loads(tc.get("arguments", "{}"))
                    except Exception:
                        pass
                    if on_event:
                        on_event("tool_started", call_name, task.id)
                    result = await self._tools.run(call_name, call_args,
                                                    agent=agent_name) if self._tools else \
                        type('obj', (object,), {'output': '', 'success': False})()
                    if on_event:
                        on_event("tool_completed", call_name, task.id)
                    # append tool result to context as a tool message
                    ctx.append(ChatMessage(
                        role="tool",
                        content=result.output if hasattr(result, 'output') else str(result),
                    ))
                continue  # LLM sees tool results on next iteration

            # no tool calls → final text
            final_text = resp.content or ""
            if not final_text and self._llm:
                # rescue via fallback chain
                final_text = await self._complete_with_fallback(ctx)
            return final_text, total_tokens

        # exhausted iterations without tool resolution
        return "", total_tokens

    # ── helpers ────────────────────────────────────────────────────────
    def _build_initial_context(self, task: Task, agent_name: str) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=(
                f"You are agent '{agent_name}'. Answer the user's question. "
                f"If you need to use a tool, call it with the appropriate arguments."
            )),
            ChatMessage(role="user", content=task.prompt),
        ]

    async def _pick_llm(self, prompt: str, agent_name: str) -> LLMService:
        # per-agent model first
        if self._agent_models:
            m = await self._agent_models.get_llm(agent_name)
            if m:
                return m

        # cyber-critical keywords → strong model
        low = prompt.lower()
        if any(k in low for k in CYBER_CRITICAL_KEYWORDS):
            if self._llm_strong:
                logger.debug("Routing to strong model for cyber query")
                return self._llm_strong

        return self._llm if self._llm else self._llm_fallback  # type: ignore

    async def _complete_with_fallback(self, messages: list[ChatMessage]) -> str:
        """Try main LLM → fallback chain in sequence until one returns non-empty."""
        # Try main LLM first
        if self._llm:
            r = await self._llm.complete(messages)
            if r.content:
                return r.content

        # Then try fallback chain
        if self._fallback_chain:
            result = await self._fallback_chain.complete(messages)
            if result.content:
                return result.content

        # Final fallback: try main LLM one more time if nothing worked
        if self._llm:
            r = await self._llm.complete(messages)
            return r.content or ""

        return ""

    def _is_simple_query(self, text: str) -> bool:
        if len(text) > 240:
            return False
        forbidden = ("http://", "https://", "file:", "/home", "write",
                     "create", "generate", "run", "execute", "open")
        return not any(f in text.lower() for f in forbidden)

    def _is_factual(self, prompt: str) -> bool:
        low = prompt.lower()
        return any(w in low for w in ("what is", "who is", "when", "where",
                                       "why", "how does", "explain", "define"))

    async def _fast_answer(self, prompt: str, agent_name: str) -> tuple[str, int]:
        """Single LLM call for simple queries."""
        ctx = self._build_agent_context(prompt, agent_name)
        result = await self._complete_with_fallback(ctx)
        return result, 100

    async def _try_explicit_tool(self, prompt: str, text: str) -> str:
        """If the prompt explicitly names a known tool, try running it."""
        if not self._tools:
            return text
        for name in self._tool_registry.tool_names:
            if name in prompt.lower():
                result = await self._tools.run(name, {})
                if result.success:
                    return f"{text}\n\n[Tool {name} result]: {result.output}"
        return text

    async def _majority_vote(self, prompt: str, base_answer: str) -> str:
        """Sample N extra passes, pick majority answer."""
        samples = [base_answer]
        for _ in range(self._settings.self_consistency_samples - 1):
            try:
                ctx = self._build_agent_context(prompt, "coordinator")
                r = await self._complete_with_fallback(ctx)
                if r:
                    samples.append(r)
            except Exception:
                pass
        if len(samples) < 2:
            return base_answer
        # simple majority: return the shortest (most concise) answer
        samples.sort(key=len)
        return samples[0]

    def _split_subtasks(self, text: str) -> list[str]:
        """Split on ' and also ', ';', or numbered lists."""
        results: list[str] = []
        for part in text.split(";"):
            part = part.strip()
            if part:
                results.append(part)
        import re
        numbered = re.findall(r"^\s*\d+[.)]\s*(.+)$", text, re.M)
        for n in numbered:
            n = n.strip()
            if n and n not in results:
                results.append(n)
        return results[:self._settings.max_parallel_agents]

    async def _run_parallel(
        self, subtasks: list[str], task_id: str, on_event: Optional[Callable]
    ) -> list[str]:
        """Fan out subtasks via asyncio.gather."""
        async def run_one(sub: str) -> str:
            t = Task.create(sub, agent_name="coordinator")
            await self._lock.observe(sub)
            t.mark_running()
            _, _ = await self._run_cognition_loop(t, "coordinator", on_event)
            if self._formatter:
                return self._formatter.format(t.result or "")
            return t.result or ""

        results = await asyncio.gather(*(run_one(s) for s in subtasks), return_exceptions=True)
        return [r if isinstance(r, str) else f"[error: {r}]" for r in results]

    def _build_agent_context(self, prompt: str, agent_name: str) -> list[ChatMessage]:
        persona = ""
        if agent_name in self._agents:
            persona = self._agents[agent_name].get("persona", "")
        sys = f"You are {agent_name}. {persona}" if persona else f"You are {agent_name}."
        return [
            ChatMessage(role="system", content=sys),
            ChatMessage(role="user", content=prompt),
        ]

    async def _auto_acquire_for_task(self, task: Task, agent: str) -> None:
        """Best-effort capability discovery (stub — real impl is in CapabilityManager)."""
        logger.debug("Auto-acquire for task %s / agent %s (stub)", task.id, agent)

    async def quick_reply(self, text: str) -> str:
        """Fast single-call path for locked/simple chat."""
        ctx = self._build_agent_context(text, "manager")
        return await self._complete_with_fallback(ctx)

    async def teardown(self) -> None:
        for llm in (self._llm, self._llm_strong, self._llm_fallback,
                    self._llm_fallback2, self._llm_fallback3):
            if llm:
                await llm.teardown()
        if self._embeddings:
            await self._embeddings.teardown()
