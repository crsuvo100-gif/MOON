#!/usr/bin/env python3
"""
Moon CLI Terminal — Hermes-feature-rich, Moon-native.

Replicates Hermes CLI architecture exactly:
  main.py         — entry point, argparse, _set_process_title
  cli_output.py   — print_info/success/warning/error/header + line_input + prompt
  colors.py       — Colors enum + color() ANSI function
  commands.py     — CommandDef + SlashCommandCompleter + SlashCommandAutoSuggest
  cli_commands_mixin.py — CLICommandsMixin with _handle_*_command methods
  cli.py          — HermesCLI class (REPL loop, banner, history)
  oneshot.py      — run_oneshot() for non-interactive mode
  console_engine.py — rich console/panel primitives
  subcommands/    — model.py, status.py, doctor.py, etc.
  __init__.py     — constants + version

NO Hermes imports. NO Hermes dependencies. Moon owns every line.
"""

from __future__ import annotations

__version__ = "1.0.0"
