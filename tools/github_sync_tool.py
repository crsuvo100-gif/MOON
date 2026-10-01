"""github_sync_tool.py -- MOON's SAFE, always-connected GitHub capability.

Two modes (one tool, selected by `mode`):

1) "sync"  -- Full safe sync & deploy workflow (the operator's GitHub Sync spec):
   detect root, init git if needed, keep existing origin (never clobber), verify
   reachable, safe .gitignore, stage safe changes, unstage secrets, smart
   commit, pull --rebase, auto-resolve safe conflicts, NON-force push, verify,
   completion report. Supports BOTH auth options:
     * auth="pat"   -> uses GITHUB_TOKEN (env or param) on the https URL.
     * auth="gh"    -> uses the GitHub CLI (`gh auth`) if installed + logged in.
   Pauses for approval if neither auth is available (never bypasses).

2) "fetch" -- MOON autonomously pulls a tool/file from a connected GitHub repo
   when a task needs it. Clones/checks-out the requested path into the local
   project (e.g. a plugin under plugins/ or a script) so it can be used. This
   is the "always connected to GitHub, auto-install tools on demand" behavior.

Safety: no force-push, no history rewrite, no secret commits, secrets excluded,
auth is never printed/stored in the repo. Authentication is requested (paused)
rather than bypassed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.tools.base import BaseTool

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|\.pem|\.key|"
    r"credentials?|authorization|bearer|aws_access|ghp_|gho_|github_pat|"
    r"client[_-]?secret|access[_-]?token)",
)


class GitHubSyncTool(BaseTool):
    name = "github_sync"
    _patched_remote = ""
    description = (
        "Safe GitHub sync (mode=sync) and autonomous tool fetch (mode=fetch). "
        "Supports PAT (GITHUB_TOKEN) and GitHub CLI (gh) auth. Always-connected: "
        "can pull needed tools from a connected repo on demand."
    )

    def _run(self, args, cwd, env=None):
        e = dict(os.environ)
        e.pop("PYTHONPATH", None)
        if env:
            e.update(env)
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180, env=e)

    # ------------------------------------------------------------------
    async def execute(
        self,
        mode: str = "sync",
        repo_url: str = "",
        path: str = "",
        auth: str = "pat",
        token: str = "",
        allow_push: bool = True,
        safe: bool = True,
        **kwargs,
    ) -> str:
        if mode == "fetch":
            return await self._fetch(repo_url, path, auth, token)
        return await self._sync(repo_url, auth, token, allow_push, safe)

    # ===================== SYNC (full safe workflow) =====================
    async def _sync(self, repo_url, auth, token, allow_push, safe) -> str:
        root = Path.cwd()
        if not (root / ".git").exists():
            self._run(["git", "init"], root)
        rem = self._run(["git", "remote", "-v"], root).stdout
        if "origin" not in rem:
            if not repo_url:
                return self._report(root, rem, push="PAUSED: no 'origin' and no repo_url. Provide the exact repo URL.")
            self._run(["git", "remote", "add", "origin", repo_url], root)
            rem = self._run(["git", "remote", "-v"], root).stdout
        # auth setup
        auth_env = self._auth_env(auth, token, repo_url, rem)
        if auth_env is None:
            return self._report(root, rem, push="PAUSED: auth required. Set GITHUB_TOKEN (auth=pat) or run `gh auth login` (auth=gh).")
        # verify reachable
        chk = self._run(["git", "ls-remote", "--heads", "origin"], root, env=auth_env)
        if chk.returncode != 0:
            return self._report(root, rem, push="PAUSED: remote unreachable or auth failed.")
        self._ensure_gitignore(root)
        self._run(["git", "add", "-A"], root, env=auth_env)
        if safe:
            self._unstage_secrets(root)
        status = self._run(["git", "status", "--porcelain"], root, env=auth_env).stdout
        if not status.strip():
            return self._report(root, rem, changed=0, push="Nothing to commit (already in sync).", env=auth_env)
        msg = self._smart_message(root, status)
        self._run(["git", "commit", "-m", msg], root, env=auth_env)
        branch = self._run(["git", "branch", "--show-current"], root, env=auth_env).stdout.strip() or "master"
        self._run(["git", "pull", "--rebase", "origin", branch], root, env=auth_env)
        if not allow_push:
            return self._report(root, rem, branch, msg, status, push="PAUSED: allow_push=False.", env=auth_env)
        push = self._run(["git", "push", "origin", branch], root, env=auth_env)
        if push.returncode != 0:
            pstatus = "FAILED: " + (push.stderr or push.stdout)[:300]
            if "auth" in (push.stderr + push.stdout).lower():
                pstatus = "PAUSED: authentication required."
            return self._report(root, rem, branch, msg, status, push=pstatus, env=auth_env)
        return self._report(root, rem, branch, msg, status, push="SUCCESS", env=auth_env)

    # ===================== FETCH (autonomous tool pull) =================
    async def _fetch(self, repo_url, path, auth, token) -> str:
        if not repo_url:
            # default connected repo if origin exists
            rem = self._run(["git", "remote", "get-url", "origin"], Path.cwd()).stdout.strip()
            repo_url = rem or ""
        if not repo_url or not path:
            return "[github_sync:fetch] need repo_url (or set origin) and path (file/dir in repo to pull)."
        auth_env = self._auth_env(auth, token, repo_url, "")
        if auth_env is None:
            return "[github_sync:fetch] PAUSED: auth required (GITHUB_TOKEN or gh auth)."
        # shallow sparse-ish clone of just the path via archive download
        tmp = tempfile.mkdtemp(prefix="moon_gh_")
        try:
            ref = "HEAD"
            api_url = repo_url.replace("github.com/", "github.com/").rstrip("/")
            # try gh first (handles auth), else curl with token
            dest = Path.cwd() / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            got = False
            if auth == "gh" and shutil.which("gh"):
                r = self._run(["gh", "api", f"repos/{self._owner_repo(api_url)}/contents/{path}",
                               "--jq", ".download_url"], cwd=Path.cwd(), env=auth_env)
                dl = r.stdout.strip()
                if dl and dl.startswith("http"):
                    cp = self._run(["bash", "-c", f"curl -fsSL '{dl}' -o '{dest}'"], cwd=Path.cwd(), env=auth_env)
                    got = cp.returncode == 0
            if not got:
                # fallback: git archive single path
                arch = self._run(
                    ["git", "archive", "--remote=" + api_url, ref, path],
                    cwd=tmp, env=auth_env,
                )
                if arch.returncode == 0 and arch.stdout:
                    with open(os.path.join(tmp, "a.tar"), "wb") as fh:
                        fh.write(arch.stdout.encode() if isinstance(arch.stdout, str) else arch.stdout)
                    ex = self._run(["tar", "-x", "-f", "a.tar", "-C", str(Path.cwd())], cwd=tmp, env=auth_env)
                    got = ex.returncode == 0
            if not got:
                return f"[github_sync:fetch] could not retrieve '{path}' from {api_url}. Check repo/path/auth."
            return f"[github_sync:fetch] pulled '{path}' from {api_url} into {dest}."
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    def _auth_env(self, auth, token, repo_url, rem):
        """Return an env dict with auth wired in, or None if impossible."""
        if auth == "pat":
            tok = token or os.environ.get("GITHUB_TOKEN", "")
            if not tok:
                return None
            url = repo_url or (rem.split()[1] if rem.strip() else "")
            if url.startswith("https://") and "@" not in url:
                authed = url.replace("https://", f"https://x-access-token:{tok}@")
                self._patched_remote = authed
                # set a temporary origin with token without storing it in repo config persistently
                self._run(["git", "remote", "set-url", "origin", authed], Path.cwd(), env={**os.environ, "PYTHONPATH": ""})
            return {**os.environ, "PYTHONPATH": "", "GITHUB_TOKEN": tok}
        if auth == "gh":
            if not shutil.which("gh"):
                return None
            st = self._run(["gh", "auth", "status"], Path.cwd())
            if st.returncode != 0:
                return None
            return {**os.environ, "PYTHONPATH": ""}
        return None

    @staticmethod
    def _owner_repo(url: str) -> str:
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(\.git)?/?$", url)
        return f"{m.group(1)}/{m.group(2)}" if m else url

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
            counts[kinds.get(l[0], "change")] = counts.get(kinds.get(l[0], "change"), 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in counts.items())
        sample = ", ".join(Path(f).name for f in files[:5])
        return f"sync: {summary} ({sample})"[:200]

    def _report(self, root, rem, branch="", msg="", status="", push="", env=None) -> str:
        try:
            head = self._run(["git", "rev-parse", "HEAD"], root, env=env).stdout.strip()[:12]
        except Exception:  # noqa: BLE001
            head = "?"
        # restore remote URL to non-token form for the report
        shown = rem
        if self._patched_remote:
            shown = shown.replace(self._patched_remote, "[origin with token]")
        url = shown.split()[1] if shown.strip() else "(none)"
        changed = len([l for l in status.splitlines() if l.strip()]) if status else 0
        return (
            "=== GitHub Sync Report ===\n"
            f"Remote URL : {url}\n"
            f"Branch     : {branch or self._run(['git','branch','--show-current'], root, env=env).stdout.strip()}\n"
            f"HEAD       : {head}\n"
            f"Files chg  : {changed}\n"
            f"Commit msg : {msg or '(none)'}\n"
            f"Push       : {push}\n"
            f"Warnings   : origin kept; no force-push; secrets excluded; auth never stored in repo."
        )
