---
name: destructive-rm-safety
description: Backup-first before rm -rf or uninstall. Plan then ask.
---

# Destructive `rm` Safety Procedure

## When to load this skill
Any time the user says: "uninstall", "delete", "remove", "wipe", "rm -rf", "purge", or asks you to clean up a project / app / directory that you did not personally create in this session.

## Why this exists
`rm -rf` is **not reversible**. Trash XDG, expunged dir, `lsof`, `find /`, git remotes do NOT recover it. No undelete tool on a standard Linux ext4 root. I lost a 712 MB user project this way; the user explicitly told me afterwards to put it back. I could not.

## The Procedure (mandatory, in order)

1. **Inventory first, delete second.** Run in parallel:
   - `ls -la <target>` and all parent dirs
   - `find /home /opt /srv /var -iname "<keyword>"` to spot related stragglers the user may not have named
   - `ps -ef | grep <keyword>` for running processes
   - `ss -ltnp` for held ports
   - `command -v <binary>`, `crontab -l`, `systemctl --user list-unit-files`, grep `.bashrc`/`.zshrc`/`.profile`/`/etc/profile.d/`
   - `ls ~/.local/share/Trash/{files,expunged}` — confirm Trash is empty so user knows `rm` is final
   - `find / -xdev -name "*.tar*" -o -name "*.zip"` looking for any pre-existing backup

2. **Plan, then ASK.** Use `clarify` to get explicit approval on a numbered option. Do NOT proceed on "yes that sounds right."

3. **STOP THE PROCESS BEFORE DELETING ITS FILES.** If target is a running service, kill its PID tree FIRST (try SIGTERM down the tree, escalate to direct SIGTERM on the listener PID, then SIGKILL). Verify port is free with `ss -ltnp`. Otherwise `rm -rf` mid-process can wedge writes.

4. **BACKUP FIRST.** Before any `rm -rf`, create a tarball:
   ```bash
   tar -czf /tmp/<name>-backup-$(date +%Y%m%d_%H%M%S).tar.gz -C <parent> <target>
   tar -tzf /tmp/<name>-backup-*.tar.gz | wc -l   # confirm file count
   ```
   Keep the backup until the user explicitly says "you can delete the backup too."

5. **Delete only after backup is verified.** Run `rm -rf` and capture stderr.

6. **Verify post-delete.** Re-run step 1 commands. Confirm: no processes, port free, no stragglers in PATH/systemd/cron/rc, /tmp clean, df shows freed space.

7. **Report exactly what happened.** Real bytes freed, real exit codes, real before/after listings. Never say "restored" or "undone" if it wasn't.

## Hard rules

- **NEVER `rm -rf` without a backup tarball** when target is anything larger than a single config file.
- **NEVER claim a delete is reversible.** It isn't.
- **NEVER assume the user wants related artifacts gone.** Ask about zips, screenshots, plans, skills, templates that name-match the target.
- **NEVER delete `.git` directories** — they're the only recovery path. Ask twice, confirm git status is clean first.
- **NEVER touch another user's home or `/root`** without explicit sudo + per-path approval.

## Recovery when you've already deleted without a backup

You cannot. Be honest. Tell the user:
- `rm -rf` is not in Trash on Linux ext4
- Kernel freed the inodes; data is being overwritten by ongoing writes
- Recovery options that DON'T exist here: undelete, extundelete, photorec (not installed; ext4 doesn't keep deleted inodes long)
- Recovery options that MIGHT exist (check each): git remote, external drive, snapshot service, second machine, another user's home, Docker volume, borg/restic, /root, /opt, /srv

Then ask the user how to proceed (rebuild, accept loss, etc.) — don't fabricate a path forward.

## Pitfalls hit in practice

- **zsh pipelines ignore SIGTERM.** `kill -TERM <zsh_pid>` for `cmd1 | tee log | cmd2` does NOT propagate. SIGTERM each child PID individually. Verify with `ps` and `ss`.
- **Empty dirs print nothing on `rm -rfv`.** Easy to miss. Always `ls` after to confirm.
- **`make serve` / tmux / screen parent masks the real listener.** Find the port-owning PID with `ss -ltnp` and kill THAT specifically.
- **Hidden name-matched artifacts.** zips, screenshots, plan files, skill references INSIDE OTHER skills — `find -iname "*<keyword>*"` catches them all.
- **The user may rebuild in parallel.** If files appear in the target dir during investigation, stop touching that path and ask what's writing.
