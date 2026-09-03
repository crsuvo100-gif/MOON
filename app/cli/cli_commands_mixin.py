#!/usr/bin/env python3
"""Hermes-style slash-command handlers for Moon CLI.

Mirrors hermes_cli/cli_commands_mixin.py: CLICommandsMixin class
with _handle_*_command methods. All handlers use self.state + lazy imports.

MoonCLI inherits this mixin. Methods are instance methods (not static)
so they can access self.state and self.engine.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.cli.cli_output import (
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from app.cli.colors import Colors, color
from app.cli.commands import COMMAND_REGISTRY, resolve_command, cli_commands


class CLICommandsMixin:
    """Mixin holding the interactive-CLI slash-command handlers.

    Mirrors hermes_cli/cli_commands_mixin.py:CLICommandsMixin exactly.
    All methods use self.state (CLIState) + lazy imports from cli module.
    """

    # ── /help ──────────────────────────────────────────────────────────────

    def _handle_help(self, command: str = "") -> None:
        """Handle /help — mirrors Hermes /help handler.

        Syntax:
            /help              — show all commands
            /help <command>   — show help for one command
        """
        parts = command.split(maxsplit=1)
        target = parts[0] if parts else None

        if target:
            cmd = resolve_command(target)
            if not cmd:
                print_error("Unknown command: /" + target)
                print_info("Type /help for available commands")
                return

            print()
            print(color("  /" + cmd.name + " — " + cmd.description, Colors.YELLOW.name))
            if cmd.args_hint:
                print_info("Usage: /" + cmd.name + " " + cmd.args_hint)
            if cmd.aliases:
                print_info("Aliases: " + ", ".join(cmd.aliases))
            print_info("Category: " + cmd.category)
            if cmd.subcommands:
                print_info("Subcommands: " + ", ".join(cmd.subcommands))
            print()
            return

        # Show all commands grouped by category
        print()
        print(color("  Available Commands", Colors.YELLOW.name))
        print()

        ordered_cats = ["Session", "Configuration", "System", "Info", "Exit"]
        by_category: dict = {}
        for cmd in cli_commands():
            cat = cmd.category
            by_category.setdefault(cat, []).append(cmd)

        for cat in ordered_cats:
            cmds = by_category.get(cat, [])
            if not cmds:
                continue
            print(color("  " + cat, Colors.CYAN.name))
            for cmd in sorted(cmds, key=lambda c: c.name):
                alias_str = ""
                if cmd.aliases:
                    alias_str = " (" + ", ".join(cmd.aliases) + ")"
                args_str = ""
                if cmd.args_hint:
                    args_str = " " + cmd.args_hint
                print("    /" + cmd.name + alias_str + args_str + " — " + cmd.description)
            print()

        print_info("Type /help <command> for details on a specific command")
        print_info("Type /quit to exit")
        print()

    # ── /new or /reset ──────────────────────────────────────────────────────

    def _handle_new(self, command: str = "") -> None:
        """Handle /new — start a new session."""
        from app.cli.commands import CLIState

        parts = command.split(maxsplit=1)
        name = parts[0] if parts else None

        self.state = CLIState(
            model_name=self.state.model_name,
            agent_name=self.state.agent_name,
            session_id=name,
            voice_enabled=self.state.voice_enabled,
            tts_enabled=self.state.tts_enabled,
            verbose=self.state.verbose,
        )

        print()
        print_success("New session started" + ((" — " + name) if name else ""))
        print_info("Session: " + self.state.session_id)
        print_info("Model: " + self.state.model_name)
        print()

    # ── /clear ──────────────────────────────────────────────────────────────

    def _handle_clear(self, command: str = "") -> None:
        """Handle /clear — clear screen and start new session."""
        os.system("clear" if os.name != "nt" else "cls")
        self._handle_new("")

    # ── /history ────────────────────────────────────────────────────────────

    def _handle_history(self, command: str = "") -> None:
        """Handle /history — show recent conversation turns."""
        msgs = self.state.messages
        if not msgs:
            print_info("No messages in current session")
            return

        print()
        print(color("  Conversation History", Colors.YELLOW.name))
        for i, msg in enumerate(msgs[-20:], 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")[:200]
            timestamp = msg.get("timestamp", "")
            if timestamp:
                print("    [" + timestamp + "] " + role + ":", content)
            else:
                print("    " + role + ":", content)
        print()

        total = len(msgs)
        if total > 20:
            print_info("... and " + str(total - 20) + " more messages (showing last 20)")

    # ── /save ───────────────────────────────────────────────────────────────

    def _handle_save(self, command: str = "") -> None:
        """Handle /save — save session to file."""
        parts = command.split(maxsplit=1)
        fmt = parts[0].split()[0] if parts and parts[0] else "json"
        rest = " ".join(parts[1].split()[1:]) if parts and len(parts[1].split()) > 1 else None

        if fmt not in ("json", "md", "html"):
            print_error("Usage: /save <json|md|html> [filename]")
            print_info("  /save                — save as JSON (default)")
            print_info("  /save md [file]      — save as Markdown")
            print_info("  /save html [file]    — save as HTML")
            return

        if not rest:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            rest = "moon_session_" + ts + "." + fmt

        path = Path(rest)
        if not path.suffix:
            path = path.with_suffix("." + fmt)

        try:
            if fmt == "json":
                path.write_text(json.dumps(self.state.messages, indent=2))
            elif fmt == "md":
                self._save_as_markdown(path)
            elif fmt == "html":
                self._save_as_html(path)
            print_success("Session saved to " + str(path))
        except Exception as e:
            print_error("Failed to save: " + str(e))

    def _save_as_markdown(self, path: Path) -> None:
        lines = ["# MOON Session", "", "Session ID: " + self.state.session_id, ""]
        for msg in self.state.messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            lines.append("## " + role.capitalize())
            lines.append("")
            lines.append(content)
            lines.append("")
        path.write_text("\n".join(lines))

    def _save_as_html(self, path: Path) -> None:
        html = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>MOON Session " + self.state.session_id + "</title></head><body>",
            "<h1>MOON Session</h1><p>Session ID: " + self.state.session_id + "</p>",
        ]
        for msg in self.state.messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            html.append("<div class='" + role + "'><h2>" + role.capitalize() + "</h2><p>" + content + "</p></div>")
        html.append("</body></html>")
        path.write_text("\n".join(html))

    # ── /retry ──────────────────────────────────────────────────────────────

    def _handle_retry(self, command: str = "") -> None:
        """Handle /retry — resend last message to agent."""
        if not self.state.last_prompt:
            print_error("No previous prompt to retry")
            return

        print_info("Retrying: " + self.state.last_prompt)
        from app.cli.oneshot import run_oneshot
        import asyncio
        asyncio.run(
            run_oneshot(
                self.state.last_prompt,
                model=self.state.model_name,
                agent=self.state.agent_name,
            )
        )

    # ── /undo ───────────────────────────────────────────────────────────────

    def _handle_undo(self, command: str = "") -> None:
        """Handle /undo — back up N user turns and re-prompt."""
        parts = command.split()
        n = int(parts[0]) if parts and parts[0].isdigit() else 1

        msgs = self.state.messages
        if not msgs:
            print_info("Nothing to undo")
            return

        removed = 0
        new_msgs = []
        for msg in reversed(msgs):
            if msg.get("role") == "user" and removed < n:
                removed += 1
                continue
            new_msgs.insert(0, msg)

        self.state.messages = new_msgs
        if removed:
            print_success("Undid " + str(removed) + " user turn(s)")
        else:
            print_info("No user turns to undo")

    # ── /title ──────────────────────────────────────────────────────────────

    def _handle_title(self, command: str = "") -> None:
        """Handle /title — set or show session title."""
        if not command:
            print_info("Session title: " + self.state.session_id)
            return

        self.state.session_id = command
        print_success("Session title set to: " + command)

    # ── /branch ─────────────────────────────────────────────────────────────

    def _handle_branch(self, command: str = "") -> None:
        """Handle /branch — branch current session."""
        from app.cli.commands import CLIState

        name = command or "branch-" + str(int(time.time()))
        branch_state = CLIState(
            model_name=self.state.model_name,
            agent_name=self.state.agent_name,
            session_id=name,
            voice_enabled=self.state.voice_enabled,
            tts_enabled=self.state.tts_enabled,
            verbose=self.state.verbose,
            messages=list(self.state.messages),
        )

        print_success("Branched session —> " + name)
        print_info("Original: " + self.state.session_id)
        print_info("Branch: " + name)
        print()
        print_info("Use /new <name> to switch to the branch")

    # ── /compress ───────────────────────────────────────────────────────────

    def _handle_compress(self, command: str = "") -> None:
        """Handle /compress — compress conversation context."""
        print_info("Compressing conversation context...")
        print_info("  Before: " + str(len(self.state.messages)) + " messages")

        keep = 10
        msgs = self.state.messages
        if len(msgs) <= keep:
            print_info("  Already compact (<= " + str(keep) + " messages)")
            return

        self.state.messages = msgs[-keep:]
        print_success("  After: " + str(len(self.state.messages)) + " messages (kept last " + str(keep) + ")")

    # ── /model ──────────────────────────────────────────────────────────────

    def _handle_model(self, command: str = "") -> None:
        """Handle /model — show or switch model.

        Syntax:
            /model                  — show current model
            /model <name>          — switch to <name>
            /model --query <prompt>  — one-shot on current model
            /model <name> --query <prompt>  — switch + query
        """
        from app.config.settings import Settings

        s = Settings()

        if not command or command.strip() == "--query":
            print_info("Current model: " + str(s.model_name))
            print_info("Base URL: " + str(s.model_base_url))
            return

        # Parse: "name --query prompt" or just "name"
        query = None
        name = command
        if "--query" in command:
            parts = command.split("--query", 1)
            name = parts[0].strip()
            query = parts[1].strip() if len(parts) > 1 else None

        if not name:
            print_info("Current model: " + str(s.model_name))
            return

        old = s.model_name
        s.model_name = name
        self.state.model_name = name
        print_success("Model switched: " + str(old) + " -> " + str(name))

        if query:
            print_info("Running one-shot on " + name + ": " + query)
            from app.cli.oneshot import run_oneshot
            import asyncio
            asyncio.run(
                run_oneshot(query, model=name, agent=self.state.agent_name)
            )

    # ── /agent ──────────────────────────────────────────────────────────────

    def _handle_agent(self, command: str = "") -> None:
        """Handle /agent — show or switch agent."""
        from app.config.settings import Settings

        s = Settings()

        if not command:
            print_info("Current agent: " + str(s.agent or self.state.agent_name or "auto"))
            return

        self.state.agent_name = command
        print_success("Agent switched: " + command)

    # ── /verbose ────────────────────────────────────────────────────────────

    def _handle_verbose(self, command: str = "") -> None:
        """Handle /verbose — toggle verbose mode."""
        self.state.verbose = not self.state.verbose
        print_info("Verbose mode " + ("enabled" if self.state.verbose else "disabled"))

    # ── /voice ──────────────────────────────────────────────────────────────

    def _handle_voice(self, command: str = "") -> None:
        """Handle /voice — toggle voice mode."""
        sub = command.lower().strip() if command else ""

        if not sub or sub == "status":
            print_info("Voice enabled: " + str(self.state.voice_enabled))
            print_info("TTS enabled: " + str(self.state.tts_enabled))
            return

        if sub in ("on", "true", "yes"):
            self.state.voice_enabled = True
            print_success("Voice enabled")
        elif sub in ("off", "false", "no"):
            self.state.voice_enabled = False
            print_success("Voice disabled")
        elif sub == "tts":
            self.state.tts_enabled = not self.state.tts_enabled
            print_info("TTS " + ("enabled" if self.state.tts_enabled else "disabled"))
        else:
            print_info("Usage: /voice [on|off|tts|status]")

    # ── /shell ──────────────────────────────────────────────────────────────

    def _handle_shell(self, command: str = "") -> None:
        """Handle /shell — run a shell command."""
        if not command:
            print_info("Usage: /shell <command>")
            return

        from app.terminal_interface import _shell_dispatch
        out, code = _shell_dispatch(command.strip())

        if code == 0:
            if out:
                print(out.rstrip("\n"))
        else:
            if out:
                print_error(out.rstrip("\n"))
            print_error("Exit code: " + str(code))

    # ── /status ─────────────────────────────────────────────────────────────

    def _handle_status(self, command: str = "") -> None:
        """Handle /status — show backend health."""
        import httpx

        try:
            r = httpx.get("http://127.0.0.1:8777/api/health", timeout=5.0)
        except Exception as e:
            print_error("Cannot reach backend: " + str(e))
            return

        if r.status_code != 200:
            print_error("Backend returned HTTP " + str(r.status_code))
            return

        data = r.json()

        print()
        print(color("  MOON Backend Status", Colors.YELLOW.name))
        print()

        model = data.get("model", "N/A")
        locked = data.get("locked", "?")
        summary = data.get("summary", "N/A")
        agents = data.get("agents", 0)
        tools = data.get("tools", 0)
        ltm = data.get("ltm", 0)
        stm = data.get("stm", 0)
        episodic = data.get("episodic", 0)
        knowledge = data.get("knowledge", 0)

        print(color("  Model:   ", Colors.CYAN.name) + str(model))
        print(color("  Locked:  ", Colors.CYAN.name) + str(locked))
        print(color("  Summary: ", Colors.CYAN.name) + str(summary))
        print()

        print("  Components:")
        print("    Agents:   " + str(agents))
        print("    Tools:    " + str(tools))
        print("    LTM:      " + str(ltm))
        print("    STM:      " + str(stm))
        print("    Episodic: " + str(episodic))
        print("    Knowledge:" + str(knowledge))
        print()

        checks = data.get("checks", [])
        if checks:
            print("  Subsystem Checks:")
            for check in checks:
                name = check.get("subsystem", "?")
                state = check.get("state", "?")
                detail = check.get("detail", "")
                icon = "OK" if state == "OK" else "FAIL"
                icon_color = Colors.GREEN.name if state == "OK" else Colors.RED.name
                print("    " + color(icon, icon_color) + " " + name + ": " + detail)
            print()

        from app.config.settings import Settings
        s = Settings()
        print_info("Configured model (local .env): " + str(s.model_name))

    # ── /doctor ─────────────────────────────────────────────────────────────

    def _handle_doctor(self, command: str = "") -> None:
        """Handle /doctor — check configuration and dependencies."""
        from app.cli.subcommands.doctor import run as _run_doctor
        import argparse

        ns = argparse.Namespace(verbose=bool(command))
        _run_doctor(ns)

    # ── /quit ───────────────────────────────────────────────────────────────

    def _handle_quit(self, command: str = "") -> None:
        """Handle /quit — exit the CLI."""
        print()
        print_success("Goodbye! 👋")
        sys.exit(0)

    # ── /personality ────────────────────────────────────────────────────────

    def _handle_personality(self, command: str = "") -> None:
        """Handle /personality — set personality style."""
        options = ["default", "concise", "technical", "creative", "teacher"]

        if not command:
            print_info("Available personalities: " + ", ".join(options))
            print_info("Current: " + str(self.state.personality or "default"))
            return

        if command.lower() in options:
            self.state.personality = command.lower()
            print_success("Personality set to: " + command)
        else:
            print_error("Unknown personality: " + command)
            print_info("Available: " + ", ".join(options))

    # ── /goal ───────────────────────────────────────────────────────────────

    def _handle_goal(self, command: str = "") -> None:
        """Handle /goal — set or show session goal."""
        if not command:
            goal = getattr(self.state, "goal", None)
            if goal:
                print()
                print(color("  Current Goal", Colors.YELLOW.name))
                print(goal)
                print()
            else:
                print_info("No goal set for this session")
                print_info("Usage: /goal <text>")
            return

        self.state.goal = command
        print_success("Goal set: " + command)

    # ── /footer ─────────────────────────────────────────────────────────────

    def _handle_footer(self, command: str = "") -> None:
        """Handle /footer — toggle footer display."""
        val = not getattr(self.state, "footer", False)
        self.state.footer = val
        print_info("Footer display " + ("on" if val else "off"))

    # ── /indicator ──────────────────────────────────────────────────────────

    def _handle_indicator(self, command: str = "") -> None:
        """Handle /indicator — show thinking indicator style."""
        print_info("Thinking indicator: animated dots (default)")
        print_info("Usage: /indicator <style> (future: dots|bar|none)")

    # ── /statusbar ──────────────────────────────────────────────────────────

    def _handle_statusbar(self, command: str = "") -> None:
        """Handle /statusbar — toggle status bar."""
        val = not getattr(self.state, "statusbar", True)
        self.state.statusbar = val
        print_info("Status bar " + ("on" if val else "off"))

    # ── /timestamps ─────────────────────────────────────────────────────────

    def _handle_timestamps(self, command: str = "") -> None:
        """Handle /timestamps — toggle timestamps on messages."""
        val = not getattr(self.state, "timestamps", False)
        self.state.timestamps = val
        print_info("Timestamps " + ("on" if val else "off"))

    # ── /focus ──────────────────────────────────────────────────────────────

    def _handle_focus(self, command: str = "") -> None:
        """Handle /focus — toggle focus mode."""
        val = not getattr(self.state, "focus", False)
        self.state.focus = val
        print_info("Focus mode " + ("on" if val else "off"))

    # ── /reload ─────────────────────────────────────────────────────────────

    def _handle_reload(self, command: str = "") -> None:
        """Handle /reload — reload configuration."""
        from app.config.settings import Settings
        s = Settings()
        self.state.model_name = s.model_name
        print_success("Configuration reloaded")
        print_info("Model: " + str(s.model_name))
        print_info("Base URL: " + str(s.model_base_url))

    # ── Commands not implemented in Moon CLI ────────────────────────────────
    # /copy, /paste, /image, /usage, /version, /update, /debug, /egress,
    # /context, /snapshot, /export, /import, /worktree, /handoff, /journey,
    # /moa, /loop, /plan, /review, /refine, /queue, /steer, /btw, /bg,
    # /heartbeat, /tools, /toolsets, /skills, /memory, /bundles, /pet,
    # /hatch, /learn, /init, /cron, /suggestions, /blueprint, /curator,
    # /kanban, /reload-mcp, /reload-skills, /browser, /plugins, /stop,
    # /pause, /resume, /whoami, /profile, /sethome, /sessions, /config,
    # /codex-runtime, /battery, /diff, /yolo, /approvals, /reasoning,
    # /fast, /skin, /wake, /busy, /approve, /deny, /start, /topic,
    # /prompt, /rollback, /platforms, /platform, /insights, /subscription,
    # /topup, /agents, /tasks, /learning, /memory-graph
    # These are Hermes-specific commands not applicable to Moon CLI.
