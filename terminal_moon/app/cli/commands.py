"""
CLI commands registry + CommandDef + CLIState.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandDef:
    name: str
    description: str
    category: str = "general"
    aliases: list[str] = None
    args_hint: str = ""
    subcommands: list[str] = None
    cli_only: bool = False
    gateway_only: bool = False
    busy_policy: str = "queue"
    busy_handler: Optional[str] = None
    execute: Optional[str] = None
    argument_mode: str = "text"

    def __post_init__(self) -> None:
        if self.aliases is None:
            self.aliases = []
        if self.subcommands is None:
            self.subcommands = []


COMMAND_REGISTRY: list[CommandDef] = [
    CommandDef("help", "Show command help", "general"),
    CommandDef("new", "Start a new session", "session"),
    CommandDef("clear", "Clear the chat", "session"),
    CommandDef("history", "Show recent messages", "session"),
    CommandDef("save", "Save chat to file", "session", args_hint="[path]"),
    CommandDef("retry", "Retry last prompt", "session"),
    CommandDef("undo", "Remove last message", "session"),
    CommandDef("title", "Show session title", "session"),
    CommandDef("branch", "Show current branch", "session"),
    CommandDef("compress", "Toggle compression", "session"),
    CommandDef("model", "Set or show model", "model", args_hint="[name]"),
    CommandDef("agent", "Set or show agent", "agent", args_hint="[name]"),
    CommandDef("personality", "Show personality", "agent"),
    CommandDef("verbose", "Toggle verbose mode", "general"),
    CommandDef("goal", "Show goal", "general"),
    CommandDef("voice", "Voice status", "general"),
    CommandDef("shell", "Run shell command", "general", args_hint="<cmd>"),
    CommandDef("status", "Show status", "general"),
    CommandDef("doctor", "Health check", "general"),
    CommandDef("chat", "Send a message", "chat", args_hint="<text>"),
    CommandDef("oneshot", "Single LLM query", "chat", args_hint="<text>"),
    CommandDef("setup", "Setup wizard", "general"),
    CommandDef("quit", "Exit MOON", "session"),
]

_COMMAND_LOOKUP: dict[str, CommandDef] = {c.name: c for c in COMMAND_REGISTRY}


def resolve_command(name: str) -> Optional[CommandDef]:
    return _COMMAND_LOOKUP.get(name)


def get_all_command_names() -> list[str]:
    return list(_COMMAND_LOOKUP.keys())


class CLIState:
    def __init__(self):
        self.model_name: str = ""
        self.agent_name: str = ""
        self.session_id: str = ""
        self.voice_enabled: bool = True
        self.tts_enabled: bool = True
        self.verbose: bool = False
        self.messages: list[dict] = []
        self.last_response: Optional[str] = None
        self.last_prompt: Optional[str] = None
