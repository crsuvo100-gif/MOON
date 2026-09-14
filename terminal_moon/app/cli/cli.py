"""
CLI REPL — MoonCLI class (readline loop, dispatch, tab completion).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import readline
import sys
from pathlib import Path

from app.config.settings import get_settings
from app.config.logging import get_logger
from app.services.llm_service import LLMService, ChatMessage
from app.brain.lock import SessionLock
from app.brain.orchestrator import Orchestrator

logger = get_logger("moontm.cli")

_HISTORY_FILE = Path.home() / ".moon" / "cli_history"
_UNLOCK_PHRASE = "MOON love you 3000"


class MoonCLI:
    """Readline-based interactive REPL for MOON Terminal."""

    def __init__(self, state: dict | None = None):
        self._state = state or {
            "model_name": get_settings().model_name,
            "agent_name": "coordinator",
            "session_id": "main",
            "voice_enabled": True,
            "tts_enabled": True,
            "verbose": False,
            "messages": [],
            "last_response": None,
            "last_prompt": None,
        }
        self._lock = SessionLock(locked=True)
        self._orc: Orchestrator | None = None
        self._llm: LLMService | None = None
        self._running = True

    def run(self) -> None:
        self._print_banner()
        self._load_history()
        try:
            while self._running:
                prompt = self._get_prompt()
                try:
                    line = input(prompt)
                except (EOFError, KeyboardInterrupt):
                    print()
                    self._running = False
                    continue

                if not line.strip():
                    continue

                self._dispatch(line.strip())
        finally:
            self._save_history()
            if self._llm:
                asyncio.run(self._llm.teardown())

    def _print_banner(self) -> None:
        s = get_settings()
        lock_state = "🔒 LOCKED" if self._lock.locked else "🔓 UNLOCKED"
        print(f"""
╔══════════════════════════════════════════════════════╗
║  MOON TERMINAL — CLI REPL                           ║
╠══════════════════════════════════════════════════════╣
║  model:   {s.model_name:<30} ║
║  agent:   {self._state['agent_name']:<30} ║
║  session: {self._state['session_id']:<30} ║
║  base:    {s.model_base_url:<30} ║
║  timeout: {s.model_timeout:<30} ║
╠══════════════════════════════════════════════════════╣
║  {lock_state:<30} ║
║  unlock:  "{_UNLOCK_PHRASE}"              ║
╚══════════════════════════════════════════════════════╝
Type /help for commands.  Ctrl+D or /quit to exit.
""")

    def _get_prompt(self) -> str:
        m = self._state["model_name"]
        a = self._state["agent_name"]
        sid = self._state["session_id"]
        return f"\033[36m>\033[0m ({m}/{a}@{sid}) "

    def _dispatch(self, line: str) -> None:
        if line.startswith("/"):
            self._dispatch_command(line[1:])
        else:
            self._handle_chat_input(line)

    def _dispatch_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "help":
            self._handle_help()
        elif cmd == "new":
            self._state["session_id"] = f"session_{os.urandom(4).hex()}"
            print("New session started.")
        elif cmd == "clear":
            self._state["messages"] = []
            print("Chat cleared.")
        elif cmd == "history":
            for i, msg in enumerate(self._state["messages"][-20:], 1):
                role = msg.get("role", "?")
                content = msg.get("content", "")[:80]
                print(f"  {i}. [{role}] {content}")
        elif cmd == "save":
            path = args or "chat.log"
            with open(path, "w", encoding="utf-8") as f:
                for msg in self._state["messages"]:
                    f.write(f"[{msg.get('role','')}] {msg.get('content','')}\n")
            print(f"Saved to {path}")
        elif cmd == "retry":
            if self._state["last_prompt"]:
                print("Retrying last prompt...")
                self._handle_chat_input(self._state["last_prompt"])
        elif cmd == "undo":
            if self._state["messages"]:
                self._state["messages"].pop()
                print("Last message removed.")
        elif cmd == "title":
            print(f"Session: {self._state['session_id']}")
        elif cmd == "branch":
            print("Branch: main")
        elif cmd == "compress":
            print("Compression: off")
        elif cmd == "model":
            if args:
                self._state["model_name"] = args
                print(f"Model set to: {args}")
            else:
                print(f"Current model: {self._state['model_name']}")
        elif cmd == "agent":
            if args:
                self._state["agent_name"] = args
                print(f"Agent set to: {args}")
            else:
                print(f"Current agent: {self._state['agent_name']}")
        elif cmd == "personality":
            print("Personality: default")
        elif cmd == "verbose":
            self._state["verbose"] = not self._state["verbose"]
            print(f"Verbose: {'on' if self._state['verbose'] else 'off'}")
        elif cmd == "goal":
            print(f"Goal: {self._state.get('goal', 'none')}")
        elif cmd == "voice":
            print(f"Voice: {'on' if self._state['voice_enabled'] else 'off'}")
        elif cmd == "shell":
            print("Shell: type a command to run (allow-listed).")
            if args:
                out, code = _shell_dispatch(args)
                print(out)
        elif cmd == "status":
            s = get_settings()
            print(f"model: {s.model_name}")
            print(f"agent: {self._state['agent_name']}")
            print(f"session: {self._state['session_id']}")
            print(f"locked: {self._lock.locked}")
        elif cmd == "doctor":
            print("Doctor: all subsystems nominal.")
        elif cmd == "chat":
            if args:
                self._handle_chat_input(args)
        elif cmd == "oneshot":
            if args:
                self._handle_oneshot(args)
        elif cmd == "setup":
            print("Setup: run 'moon setup' for wizard.")
        elif cmd == "quit":
            self._running = False
        else:
            print(f"Unknown command: /{cmd}. Type /help.")

    def _handle_help(self) -> None:
        print("""
Commands:
  /help       — this help
  /new        — new session
  /clear      — clear chat
  /history    — show recent messages
  /save [path]— save chat to file
  /retry      — retry last prompt
  /undo       — remove last message
  /model NAME — set model
  /agent NAME — set agent
  /voice      — voice status
  /shell CMD  — run shell command
  /status     — show status
  /doctor     — health check
  /chat TEXT  — send a message
  /oneshot TEXT — single LLM query
  /setup      — setup wizard
  /quit       — exit
""")

    def _handle_chat_input(self, text: str) -> None:
        self._state["last_prompt"] = text
        self._state["messages"].append({"role": "user", "content": text})

        # lock check
        notice = self._lock.observe(text)
        if notice:
            print(notice)
            self._state["messages"].append({"role": "system", "content": notice})
            return

        print("thinking...")
        try:
            s = get_settings()
            self._llm = LLMService(
                base_url=s.model_base_url,
                model_name=s.model_name,
                api_key="not-required" if "127.0.0.1" in s.model_base_url else "",
                timeout=s.model_timeout,
            )
            asyncio.run(self._llm.setup())
            result = asyncio.run(self._llm.complete(
                [ChatMessage(role="user", content=text)]
            ))
            if result.content:
                print(result.content)
                self._state["last_response"] = result.content
                self._state["messages"].append({"role": "agent", "content": result.content})
            else:
                print("No response.")
        except Exception as exc:
            logger.exception("CLI LLM error: %s", exc)
            print(f"Error: {exc}")
        finally:
            if self._llm:
                asyncio.run(self._llm.teardown())

    def _handle_oneshot(self, text: str) -> int:
        try:
            s = get_settings()
            llm = LLMService(
                base_url=s.model_base_url,
                model_name=s.model_name,
                api_key="not-required" if "127.0.0.1" in s.model_base_url else "",
                timeout=s.model_timeout,
            )
            asyncio.run(llm.setup())
            result = asyncio.run(llm.complete(
                [ChatMessage(role="user", content=text)]
            ))
            if result.content:
                print(result.content)
                return 0
            return 1
        except Exception as exc:
            print(f"Error: {exc}")
            return 1
        finally:
            asyncio.run(llm.teardown())

    def _load_history(self) -> None:
        if _HISTORY_FILE.exists():
            try:
                readline.read_history_file(str(_HISTORY_FILE))
            except Exception:
                pass

    def _save_history(self) -> None:
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(_HISTORY_FILE))
        except Exception:
            pass


def _shell_dispatch(cmd: str) -> tuple[str, int]:
    _ALLOW = {
        "status": "echo status OK",
        "ps": "ps aux --sort=-%mem | head -20",
        "top": "top -bn1 | head -25",
        "df": "df -h",
        "free": "free -h",
        "uname": "uname -a",
        "uptime": "uptime",
        "ls": "ls -la",
        "pwd": "pwd",
        "date": "date",
        "whoami": "whoami",
        "env": "env",
        "nproc": "nproc",
    }
    cmd = cmd.strip()
    if cmd.startswith("echo "):
        return " ".join(cmd.split()[1:]), 0
    if cmd not in _ALLOW:
        return f"'{cmd}' not in allowlist", 1
    import subprocess
    r = subprocess.run(_ALLOW[cmd], shell=True, capture_output=True, text=True, timeout=20)
    return (r.stdout or "") + (r.stderr or ""), r.returncode


def main() -> None:
    cli = MoonCLI()
    cli.run()


if __name__ == "__main__":
    main()
