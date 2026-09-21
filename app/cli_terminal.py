#!/usr/bin/env python3
"""Backed up before removal — app/cli_terminal.py.

MOON now has a single terminal type: the Hermes-style CLI REPL in app/cli/
(app/cli/main.py + app/cli/cli.py + app/cli/cli_commands_mixin.py). This file
was a dead fallback that was never wired into the dispatch; removed per user
request to strip extra terminals. """
