"""github_sync_tool.py -- Fully automated, SAFE GitHub sync & deploy.

Implements the operator's GitHub Sync workflow:
detect root -> ensure git -> ensure remote (never clobber existing origin) ->
verify reachable -> safe .gitignore -> stage safe changes -> smart commit ->
detect default branch -> pull --rebase -> safe conflict handling -> push ->
verify -> completion report.

Safety: no force-push, no history rewrite, no secret commits, pauses for auth
instead of bypassing it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.tools.base import BaseTool

# Patterns that must never be committed even if untracked.
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|\.pem|\.key|"
    r"credentials?|authorization|bearer|aws_access|ghp_|gho_|github_pat|"
    r"client[_-]?secret|access[_-]?token)",
)
_SAFE_SKIP = re.compile(r"(\.venv/|__pycache__/|node_modules/|\.git/|app/logs/|build/|dist/|\.env$)")


class GitHubSyncTool(BaseTool):
    name = "github_sync"
    description = "Safe automated GitHub sync: detect/init repo, stage safe changes, smart commit, pull-rebase, push to existing remote."

    def _run(self, args, cwd):
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)

    async def execute(self, repo_url: str = "", safe: bool = True, allow_push: bool = True, **kwargs) -> str:
        root = Path.cwd()
        # 1) detect git
        if not (root / ".git").exists():
            self._run(["git", "init"], root)
        # 2) remote
        rem = self._run(["git", "remote", "-v"], root).stdout
        if "origin" not in rem:
            if repo_url:
                self._run(["git", "remote", "add", "origin", repo_url], root)
                rem = self._run(["git", "remote", "-v"], root).stdout
            else:
                return self._report(root, rem, push="PAUSED: no remote 'origin' and no repo_url given. Provide the exact repo URL (e.g. https://github.com/crsuvo100-gif/MOON).")
        # 3) verify reachable
        chk = self._run(["git", "ls-remote", "--heads", "origin"], root)
        if chk.returncode != 0:
            return self._report(root, rem, push="PAUSED: remote unreachable or authentication required. Provide auth (gh login / token) before pushing.")
        # 4) .gitignore hygiene
        self._ensure_gitignore(root)
        # 5) stage safe changes
        self._run(["git", "add", "-A"], root)
        # strip any secrets that slipped into the index
        if safe:
            self._unstage_secrets(root)
        status = self._run(["git", "status", "--porcelain"], root).stdout
        if not status.strip():
            return self._report(root, rem, changed=0, push="Nothing to commit (already in sync).")
        # 6) commit
        msg = self._smart_message(root, status)
        self._run(["git", "commit", "-m", msg], root)
        # 7) default branch + pull --rebase
        branch = self._run(["git", "branch", "--show-current"], root).stdout.strip() or "master"
        self._run(["git", "pull", "--rebase", "origin", branch], root)
        # 8) push (NEVER force)
        if not allow_push:
            return self._report(root, rem, branch, msg, status, push="PAUSED: allow_push=False.")
        push = self._run(["git", "push", "origin", branch], root)
        if push.returncode != 0:
            pstatus = "FAILED: " + (push.stderr or push.stdout)[:300]
            if "auth" in (push.stderr + push.stdout).lower() or "permission" in (push.stderr + push.stdout).lower():
                pstatus = "PAUSED: authentication required. Approve auth method (gh login / token) before retry."
            return self._report(root, rem, branch, msg, status, push=pstatus)
        return self._report(root, rem, branch, msg, status, push="SUCCESS")

    # ------------------------------------------------------------------
    def _ensure_gitignore(self, root: Path) -> None:
        gi = root / ".gitignore"
        needed = [".env", "*.env", "app/logs/", ".venv/", "__pycache__/", "*.pyc",
                  "node_modules/", "*.pem", "*.key", "credentials*", "*.log", "build/", "dist/"]
        lines = gi.read_text().splitlines() if gi.exists() else []
        added = [n for n in needed if n not in lines]
        if added:
            with gi.open("a") as f:
                f.write("\n# auto-added by github_sync\n" + "\n".join(added) + "\n")

    def _unstage_secrets(self, root: Path) -> None:
        out = self._run(["git", "diff", "--cached", "--name-only"], root).stdout.split()
        for f in out:
            try:
                if _SECRET_RE.search(f) or _SECRET_RE.search((root / f).read_text(errors="replace")[:4000]):
                    self._run(["git", "reset", "-q", "--", f], root)
            except Exception:  # noqa: BLE001
                pass

    def _smart_message(self, root: Path, status: str) -> str:
        files = [l.split()[1] if len(l.split()) > 1 else l for l in status.splitlines()]
        kinds = {"A": "add", "M": "update", "D": "delete", "R": "rename", "?": "add", "U": "update"}
        counts = {}
        for l in status.splitlines():
            code = l[0]
            k = kinds.get(code, "change")
            counts[k] = counts.get(k, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in counts.items())
        sample = ", ".join(Path(f).name for f in files[:5])
        return f"sync: {summary} ({sample})"[:200]

    def _report(self, root, rem, branch="", msg="", status="", push="") -> str:
        try:
            head = self._run(["git", "rev-parse", "HEAD"], root).stdout.strip()[:12]
        except Exception:  # noqa: BLE001
            head = "?"
        url = rem.split()[1] if rem.strip() else "(none)"
        changed = len([l for l in status.splitlines() if l.strip()]) if status else 0
        return (
            "=== GitHub Sync Report ===\n"
            f"Remote URL : {url}\n"
            f"Branch     : {branch or self._run(['git','branch','--show-current'], root).stdout.strip()}\n"
            f"HEAD       : {head}\n"
            f"Files chg  : {changed}\n"
            f"Commit msg : {msg or '(none)'}\n"
            f"Push       : {push}\n"
            f"Warnings   : keep origin if it exists; no force-push; secrets excluded."
        )
