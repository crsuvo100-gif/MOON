---
name: agent-backup-restoration
description: "Use when restoring an agent backup safely across machines."
version: 1.0.0
---

# Agent Backup Restoration

Use this skill when a user supplies a backup of an AI-agent environment and asks to restore its scripts, skills, configuration, or local-model setup.

## Safe restoration workflow

1. **Inventory before copying or running anything.** Identify manifests, configuration, shell scripts, helper scripts, dependency files, model data, and repository metadata.
2. **Resolve the active profile and destination.** For Hermes, use `$HERMES_HOME` rather than assuming `~/.hermes`. Check `~/.hermes/profiles/` for non-default profiles — they have their own `skills/`, `config.yaml`, and `memories/` that a backup may or may not match.
3. **Diff the backup against current state BEFORE writing anything.** Run `diff <(ls backup/X | sort) <(ls current/X | sort)` and `wc -l` on each config/env file. Report what is only-in-backup, only-in-current, and the size/shape differences. This is the single most useful step: it tells you whether the restore is additive, destructive, or a no-op, and gives the user concrete data to pick a scope.
4. **Ask the user to scope the restore.** "Install" is almost never unambiguous. Common shapes:
   - Skills only (most common, safest) — merge backup `skills/` into destination `skills/`
   - Full restore — back up current to a timestamped `*.bak.<ts>` then copy everything over
   - Diff-only — show the diff and let the user pick pieces
   - Sessions only — restore just historical session dumps
   List the actual contents of the backup in the question so the user can pick accurately.
5. **Always take a timestamped safety backup of whatever you are about to overwrite.** `cp -a ~/.hermes/skills ~/.hermes/skills.bak.$(date +%Y%m%d_%H%M%S)` is the cheap insurance that turns a wrong restore from a disaster into a one-line rollback. The user's current state was reached through real work — don't risk it for a "should be fine" restore.
6. **Restore skills with `rsync -a --exclude='.git/'`, not `cp -a`.** Rsync merges by default; `cp -a` clobbers. The typical backup contains `<top-level-skill-dirs>/` whose contents should be added under `~/.hermes/skills/<same-name>/` while preserving any current-only skill directories (e.g. `local-llm-robustness`, `phone-number-osint`) that the backup doesn't have. `rsync -a "$BACKUP/skills/" "$DEST/skills/"` does this correctly; `cp -a` does not.
7. **Treat executable scripts as code, not configuration.** Read top-level scripts before installing or executing them. Check for hard-coded users/paths, destructive flags such as `rsync --delete`, privilege escalation, persistence hooks, network calls, and secrets.
8. **Do not merge shell startup files, config.yaml, or .env blindly.** Their shapes often differ between backup and current even when both look "compatible" (different `_config_version`, different line counts, different provider set). Always diff first, then ask. The user's live `.env` contains their current API keys — overwriting it with the backup's can silently break auth.
9. **Adapt or isolate machine-specific scripts.** Scripts using another user home or host-specific paths must be updated or placed in a clearly labeled compatibility location; do not imply that they work on the current machine without verification.
10. **Keep secrets and model artifacts separate.** Do not copy credentials into config files or chat output. Local-model weights can be large and may need an explicit re-download/install step.
11. **Verify each restored component.** Use non-destructive checks first:
    - Skills: `find ~/.hermes/skills -name SKILL.md | wc -l` for the count, then `skill_view(name='<one-known-skill>')` to confirm Hermes actually loads it from the merged location. File presence is not the same as discoverability.
    - Config/scripts: `validate manifests, invoke --help` or a status-only mode
    - Services: only test endpoints when the user asked to run them

## Session catalog vs. on-disk reality (Hermes-specific)

Hermes builds its in-session skill catalog (`~/.hermes/skills/.bundled_manifest` and the `available_skills` list returned by `skill_view`) ONCE at session start by walking `~/.hermes/skills/*/SKILL.md` and hashing each one. Skills added AFTER the session started are on disk and loadable by direct path, but will NOT appear in:

- the `available_skills` field of `skill_view` error responses
- the agent's system prompt skill index
- `skills_list` (when filtered to bundled)

How to detect this in the current session:
- `find ~/.hermes/skills -name SKILL.md | wc -l` (real count on disk) is HIGHER than the number of entries in `~/.hermes/skills/.bundled_manifest`
- `skill_view(name='<a-newly-installed-skill>')` returns "Skill not found" with a list that excludes the new dir
- The skill directory exists with a valid SKILL.md but is missing from the manifest

How to fix:
- The only reliable way to rebuild the catalog in a live Hermes session is to start a new session (`/new`, restart the gateway, or end the current chat). Do not promise the user that a "rescan" command exists unless you have actually verified it on this Hermes version.
- Be explicit with the user: tell them the install succeeded and was verified on disk, but the skills will be available "from the next session onward." This is the truthful, verifiable state — don't paper over it.
- If a user insists on using a skill in the same session, you can still read it directly via `read_file(path="~/.hermes/skills/<cat>/<skill>/SKILL.md")` and act on its instructions, but you cannot load it through the normal `skill_view` discovery path until the catalog is rebuilt.

## Pitfalls

- **No install script ≠ nothing to install.** Most agent backups (Hermes, Open Interpreter, custom scaffolds) are just a directory snapshot of files — no `install.sh`, no `setup.py`, no README. Don't refuse or stall looking for one; treat the directory contents as the installable unit and proceed via diff-and-ask.
- **"Install" is ambiguous: skills / full / diff / sessions.** State the four common interpretations and let the user pick. The cost of asking is one short clarification; the cost of a wrong-scope restore is real (overwritten config, lost live `.env`, dropped current-only skills).
- **A backup README may be stale** even when the files are intact; treat its commands as untrusted until compared to the current environment.
- **Backups can contain embedded `.git` directories** in skill trees (especially if the backup was made from a skills repo checkout). Always `rsync --exclude='.git/'` — never let repo metadata become part of a live skill installation.
- **Backup `.env` and `config.yaml` almost always have a different shape than current** (different provider set, different `_config_version`, different line count). Surface the line counts in the pre-flight diff so the user can see "backup is 458 lines, current is 497 — they are not the same file."
- **Use `rsync -a`, not `cp -a`, for skill trees.** Rsync merges; `cp -a` clobbers. With `cp -a` you will silently delete any current-only skill directories that the backup doesn't have.
- **"Install all scripts" is ambiguous:** copying scripts, adapting them, registering a service, and executing them have very different side effects. State the safe interpretation and ask for a choice if it materially changes the action.
- **Always leave a rollback path.** A timestamped `*.bak.<ts>` copy of whatever you overwrote is cheap and turns a wrong restore into a one-line `mv` rollback.
- **On-disk install ≠ in-session discoverability.** Hermes builds the skill catalog once at session start. After a restore, the new skills are on disk and will work in the next session, but `skill_view` and the system-prompt skill index in the current session will still show only the pre-restore list. Verify file presence with `find`, then tell the user plainly that activation waits for the next session. Don't invent a "rescan" command.

## Completion report

Report the source and destination, which categories were restored, any excluded metadata, counts verified, and any scripts held back because they need adaptation or user approval before execution.

For skill restores specifically, also state:
- on-disk SKILL.md count (backup vs destination) and a one-line per-skill file-presence summary
- whether sha256 of a spot-checked skill (e.g. one with linked files) matches the backup
- the **catalog-activation lag**: "files are on disk and verified; the in-session skill catalog will pick them up on the next session start" — and the exact one-line rollback command (e.g. `rm -rf ~/.hermes/skills && mv ~/.hermes/skills.bak.<ts> ~/.hermes/skills`)
