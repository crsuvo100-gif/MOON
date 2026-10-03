---
name: mew-runtime
description: Use when operating the local Mew helper scripts and backups.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [mew, backup, ollama, hermes]
    related_skills: [hermes-agent]
---

# Local Mew Runtime

## Overview
Mew helper launchers are installed for the current Linux user. Their managed data lives in `~/.local/share/mew/` and their commands are exposed through `~/.local/bin/`, which is on `PATH`.

## When to Use
- The user asks to check, back up, restore, or test the local Mew setup.
- The user asks to send a prompt to the local Ollama service.

## Commands

| Goal | Command |
|---|---|
| Check integrations and backups | `mew-backup status` |
| Create a Mew backup | `mew-backup backup` |
| List backups | `mew-backup list` |
| Validate portable backup | `mew-verify-backup [path]` |
| Call local Mew once | `mew [--health|--models]` or `mew "prompt"` |
| Open interactive Mew shell | `mew-shell` |
| Call Ollama directly | `mew-model-api [model] [prompt]` |
| Check service state | `systemctl --user status mew --no-pager` |
| Restart Mew daemon | `systemctl --user restart mew` |

`mew-backup restore` overwrites files in the home directory. It requires the user to type `YES`; do not invoke it without explicit direction.
Mew is intentionally loopback-only at `127.0.0.1:11435`; do not bind it to `0.0.0.0` or expose it publicly unless an authenticated reverse proxy/tunnel is explicitly configured.

## Backup Behavior

Backups are written to `~/.local/share/mew/backups/`. The launcher protects backup recursion and excludes caches, `Downloads`, local Ollama model files, and common archives. It retains the five newest Mew backups.

## Common Pitfalls

1. The portable backup's original `mew_backup_restore.sh` is hard-coded for `/home/ngrok`; use `mew-backup`, not that archived original.
2. `mew-model-api` requires a running Ollama server and the requested model to be installed.
3. A portable backup's skill files belong under `~/.hermes/skills/`, not in a project directory.

## Verification Checklist
- [ ] `mew-backup status` identifies Hermes and Ollama.
- [ ] `mew-verify-backup` reports the expected source directories.
- [ ] Run `mew-model-api` only after verifying the desired Ollama service/model is available.
