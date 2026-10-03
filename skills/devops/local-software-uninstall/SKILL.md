---
name: local-software-uninstall
description: Uninstall self-installed local software safely.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [uninstall, cleanup, destructive-ops, filesystem, linux, systemd, processes]
    related_skills: [local-service-operations, plan, verified-python-scaffolding]
---

# Local Software Uninstall

## Overview

Removing self-installed local software (an AI agent, a dev tool, a service the user stood up themselves) is **destructive and irreversible**. The job has two halves that must both succeed:

1. **Discovery** — find every artifact the named software owns: processes, listening ports, files, venvs, caches, config, log files, systemd units, shell hooks, cron lines, autostart entries, packages. Miss one and the user has a "ghost" install that later causes confusion.
2. **Discipline** — destroy ONLY what that software owns. Never touch files inside the user's project roots (`~/Projects/<user-project>/`, `~/Documents/...`, `~/code/...`) just because a name matches. Even an empty-looking project directory is the user's, not the artifact's.

These halves are independent and equally important. A perfect discovery followed by a sloppy scope is a worse failure than a clean scope that misses a log file — because the user can fix a missing log but cannot recover a wiped project.

## When to Use

Load this skill before any `rm -rf`, `pip uninstall`, `systemctl disable`, `crontab -r`-equivalent, or process-tree kill on a user's machine when:

- The user asks to "uninstall / remove / clean up / wipe / delete" a named local tool, agent, service, or project.
- You have decided a self-installed component should be removed (e.g., a previous session installed it).
- You're tempted to use `rm -rf` against any path that starts with `/home/<user>/`.

Do NOT use this for: removing a single file the user just named, uninstalling a system package via `apt remove <pkg>` (one-shot, no scoping), or cleaning build artifacts (`rm -rf node_modules dist build`) — those are normal task steps, not "uninstall an installed thing".

## Required Workflow

### Phase 0 — Plan mode (mandatory for non-trivial uninstalls)

If the discovery phase finds more than one or two artifacts, OR anything the user installed themselves (project dirs, venvs, custom config), STOP and present a plan before mutating. Use the `plan` skill's discipline: list every artifact with its size and path, ask the user to confirm scope, then execute. Destructive edits are exactly what plan-mode is for.

A user saying "just uninstall it" is not the same as "delete whatever you find that has this name". Default to confirming scope when the artifact name could plausibly appear inside user-owned directories.

### Phase 1 — Discover (read-only, exhaustive)

Run all of these in parallel:

1. **Live processes** — `ps -ef --forest | grep -i <name>` (note parent/child tree, PIDs, owning user).
2. **Listening sockets** — `ss -ltnp` for any port the software owns (especially the bind address, not just `:LISTEN`).
3. **On-disk artifacts** — `find /home/<user> -maxdepth 6 -iname "*<name>*"` scoped to user dirs, then widen to `/etc`, `/usr/local`, `/opt`, `/var` if relevant.
4. **System integration** — `systemctl --user list-unit-files`, `systemctl list-unit-files`, `crontab -l`, `~/.config/autostart/`, `~/.bashrc`/`.zshrc`/`.profile`, `/etc/profile.d/*.sh`.
5. **PATH binaries** — `command -v <name>` and any sibling names the install script mentioned (e.g., `launch_<name>`, `<name>.py`).
6. **Temp / runtime** — `ls /tmp | grep -i <name>`, `ls /var/tmp | grep -i <name>`.
7. **The installer script itself** — read it. Most installers are idempotent scripts that say exactly what they create. Reverse those steps.

**Pitfall**: a name appearing inside `node_modules/`, `.venv/lib/python*/site-packages/`, or system type stubs (`typeshed-fallback`) is upstream package noise, not the software you're removing. Filter these out before reporting scope. See `references/false-match-filter.md` for the regex set.

### Phase 2 — Categorize into three buckets

For every artifact discovered, classify it as exactly one:

- **OWNED by the target software**: the install script wrote it, the running process opened it, or the docs say it belongs. Will be removed.
- **OUT OF SCOPE (system / upstream / unrelated)**: keep, do not touch.
- **USER PROJECT that happens to contain a matching name**: keep, do not touch. The user explicitly told us this in past sessions ("just unintall but my project stays" — the project root is theirs even if a matching name lives inside). If you cannot prove a path is owned by the software, leave it alone.

### Phase 3 — Stop processes safely

`kill -TERM` to a shell PID does NOT cascade to its children when `set +m` is in effect or when the parent is a `zsh -lic` / `bash -lic` shell running a pipeline. Verify after every signal:

```
ps -p <pid,...> -o pid,ppid,stat,cmd
ss -ltnp | grep :<port>
```

Full recipe for killing a pipeline-owned service tree: see `references/killing-pipeline-process-trees.md`. Summary:

1. Identify the process that owns the listening socket from `ss -ltnp`'s `users:(("python",pid=N))`.
2. `kill -TERM <server-pid>` directly. Don't try to walk down from the shell.
3. `kill -TERM` siblings (`make`, `tee`, sibling scripts).
4. `kill -TERM` the shell last.
5. Re-verify: `ps` shows no survivors, `ss` shows port free.
6. Only escalate to `SIGKILL` if `SIGTERM` left a zombie holding the port.

### Phase 4 — Remove (with verification per step)

For every owned artifact:

```
ls -la <path>     # confirm it exists at the path the inventory said
du -sh <path>     # confirm size matches
rm -rf <path>     # (or rm -f for files)
ls -la <path>     # confirm gone (expect "No such file or directory")
```

Capture sizes BEFORE the rm so the final report can show bytes freed. `rm -rfv` is fine but its output can be truncated by terminal caps — pipe to `tail -5` for the record.

For project directories under `~/Projects/` or `~/code/` or `~/Documents/`: **never `rm -rf` a parent just because a name inside matches**. Open the dir, look at contents, only remove the artifacts that are clearly owned.

### Phase 5 — Sweep and prove

Re-run the Phase 1 commands (minus `find` against already-deleted paths). Specifically:

```
ps -ef | grep -i <name> | grep -v grep        # → none
ss -ltnp | grep :<port>                       # → none
ls /tmp | grep -i <name>                      # → none
command -v <name>                             # → empty
systemctl --user list-unit-files | grep <name># → none
crontab -l | grep <name>                      # → none
grep -i <name> ~/.bashrc ~/.zshrc ~/.profile  # → none
find /home/<user> -maxdepth 6 -iname "*<name>*" | grep -v <known-noise>
                                              # → none
```

If any re-check finds residue, classify it (Phase 2) and either remove or report it for user decision. Do not silently delete.

### Phase 6 — Report

The final report must contain:

- Every process killed (PID, signal, before/after `ps` evidence).
- Every file removed (path, size).
- Total bytes freed.
- The "clean" check results (each one explicitly verified, not asserted).
- Anything you intentionally did NOT touch and why (so the user can sanity-check your scope).

## Execution Style

- Default to **confirming scope** with the user via `clarify()` whenever the artifact name could appear in user-owned paths. One extra round-trip is cheaper than wiping the wrong thing.
- When the user gives a sweeping "delete everything named X" instruction, list what "everything named X" actually means (the seven buckets from Phase 1) BEFORE executing, then ask. This pattern beat a silent over-delete in past sessions.
- **Mid-turn user steering overrides your plan.** If the user interrupts with "but my project stays", stop the sweep at the project boundary immediately and re-verify.
- Verify AFTER every destructive step, not just at the end. `rm -rf` that fails silently (e.g., wrong path because `ls` lied about sort order) is caught by the next `ls`.
- Update `memory` to drop facts about artifacts that no longer exist. A skill file referencing a deleted project is worse than no skill file — it makes future sessions search for things that aren't there.

## Common Pitfalls

1. **Trusting `ls -la` over the absolute path.** A previous inventory step can list a path under one parent and the path actually lives under another (e.g., you wrote `~/Projects/MOON_X` but it's at `~/Downloads/MOON_X`). `stat <path>` immediately before `rm` to confirm. Real bug from past session: A and B were reported as deleted by `rm -rfv` but produced no output — they had moved; the verification step caught it.

2. **Scope creep into project roots.** A user project directory is the user's, even if a matching artifact lives inside. If `~/Projects/myapp/` contains `moon_persona_lock.md`, the file belongs to myapp, not to the moon uninstall. Open, look, classify, then act.

3. **`kill` to the parent when job control is off.** `zsh -lic set +m; ...` and similar pipelines do not propagate SIGTERM to children. Target the port-owning PID from `ss -ltnp`, not the shell PID. Then sweep the rest.

4. **Treating "match by name" as ground truth.** `Moon.pyi`, `moonshot_schema.py`, npm icon `moon.svg`, Chromium actor list `khalilmamoon.com` — none of these are the target software. A blanket name-search-and-delete destroys them. Always re-read the file's purpose before deleting.

5. **Silently deleting with no plan presented.** A `rm -rf` against the user's home tree without an inventory + scope-confirm is the worst failure mode of this skill. If you can't enumerate what you're about to delete, you don't know enough to delete it.

6. **Forgetting to clean `/tmp`** of the target's runtime files (logs, sockets, lockfiles). Many tools write here and the user can't tell the difference between a real residue and yours.

7. **Not removing the memory entries.** If a previous session wrote durable memory about a now-uninstalled project (paths, default models, env vars), those facts mislead the next session. Drop them in the same pass.

8. **Underestimating the restore surface.** When the user says "undo the uninstall, put everything back," the artifacts to restore can span far more than the project dir: a venv inside the project dir, a PATH launcher, a desktop entry, multiple systemd units, multiple timers, and a timer stamp. Missing any layer leaves a half-restored install (e.g., services fail `203/EXEC` because `.venv/bin/python` doesn't exist yet). See `references/moon-uninstall-restore.md` for MOON's specific layers and the proven restore sequence. The general rule: enumerate the target's install layers BEFORE attempting the undo, not after the first failure.

 **Escalation — when `StartLimitBurst` doesn't clear with `reset-failed` + pause.** A oneshot monitor service that trips `start-limit-hit` during restore may not clear with `reset-failed` + a short pause alone if the unit's own dependency wiring is contributing. Two patterns to check before resigning to "wait for the next timer tick":

 1. **The unit `Requires=` the very service it itself restarts.** A deep monitor that `Requires=moon-terminal.service` and whose own heal logic runs `systemctl restart moon-terminal.service` gets killed by systemd when its own restart fires — the failure looks like a throttle but is actually the dependency killing the oneshot. Fix: change `Requires=` to `Wants=` so the monitor isn't tied to the service's lifecycle, then `reset-failed` + `start` again.

 2. **Duplicate `StartLimit*` stanzas.** Rapid manual `restart` calls during a verify loop can leave a unit file with duplicated `StartLimitIntervalSec`/`StartLimitBurst` lines (the second set overrides the first, but the duplication is a symptom of restore thrash, not the cause). Clean the file to a single stanza, `daemon-reload`, then `reset-failed` + `start`.

 If both are clean and the unit still won't start immediately, `reset-failed` + a longer pause (the throttle window may be wider than expected on this host) or waiting for the next timer tick (e.g., 15 min) to fire and run clean is the correct, non-patching path. Only widen `StartLimitIntervalSec`/`StartLimitBurst` as a last resort when the timer-tick wait is unacceptable AND the two causes above are ruled out — and document why.

9. **Failing to rebuild the venv after a project-dir wipe.** If the project dir (and its `.venv/`) was removed, cloning the repo alone is not a working restore — every systemd ExecStart still points at a non-existent Python. Confirm `.venv/bin/python` exists and deps are installed before `daemon-reload` + `enable --now`. For MOON specifically, also confirm `.env` exists (services can fail or behave unexpectedly without it) — see `references/moon-uninstall-restore.md`.

10. **Assuming pinned requirements pins resolve everywhere.** A `requirements.txt` that pins e.g. `torch==2.9.0+cpu` may FAIL to install on a host whose Python version has no published `+cpu` wheel for that release — pip then errors with "No matching distribution found." Before blaming the repo or the network, check whether the pinned variant is actually published for the host's Python version. The fix is usually to resolve the package from the official PyTorch CPU index (or the relevant index for the package) first, then install the rest of requirements. See `references/moon-uninstall-restore.md` for the MOON/torch case and the working sequence. This is a real wheel-availability problem, not a transient network blip — don't retry-blindly.

## Verification Checklist

Before reporting "uninstall complete", every box must be checked with real command output:

- [ ] Inventory list (processes, ports, files, units, crons, rc lines) shown to user
- [ ] Scope confirmed (or task is small enough not to need it)
- [ ] Mid-turn user steering listened for and respected
- [ ] Each live process SIGTERM'd, port released, post-`ps` shown empty
- [ ] Each owned file/dir removed with size captured before, `ls` shown empty after
- [ ] No path under `~/Projects/`, `~/code/`, `~/Documents/`, `~/Desktop/` deleted without explicit user approval for that path
- [ ] Re-grep across filesystem returns no target-named artifacts (excluding known-noise filters)
- [ ] PATH binaries, systemd units, cron lines, /tmp all confirmed clean
- [ ] Total bytes freed reported
- [ ] Memory entries referencing the uninstalled artifact dropped

## Related

- `references/killing-pipeline-process-trees.md` — the exact recipe for killing a server tree when `zsh -lic set +m` is the parent.
- `references/false-match-filter.md` — the regex set that excludes npm icons, astronomy stubs, and unrelated provider code from name-searches.
- `local-service-operations` — for checking service health BEFORE deciding to uninstall it.
- `plan` — for the plan-mode discipline this skill relies on.
- `verified-python-scaffolding` — for the inverse problem (building, not tearing down).
