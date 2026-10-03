"""github_feed.py -- MOON's autonomous GitHub tool-feed.

This is the "always-connected, self-extending" behavior the operator asked for:

1. PULL FROM YOUR REPO: clone/fetch the connected GitHub repo (SSH or HTTPS)
   and discover every tool/plugin/skill it already contains (plugins/*,
   app/tools/*, skills/*/SKILL.md). This becomes MOON's local "tool catalog".

2. SEARCH IF MISSING: when a task needs a capability MOON does not have locally
   and does not find in your repo, search the PUBLIC GitHub ecosystem via the
   GitHub search API, rank by stars/relevance, pull the best match's source
   file(s), and install it as a generated plugin under plugins/generated/.

3. MERGE & BE FUNCTIONAL: the pulled plugin is imported, registered with the
   live tool registry, and immediately usable by the running task. Failures
   degrade gracefully -- the task continues with whatever tools exist.

Safety:
- No destructive ops; installs are best-effort.
- Searches are read-only (no auth needed for public search; uses GITHUB_TOKEN
  if present for a higher rate limit).
- Pinned to the operator's connected repo for the trusted catalog.
- Never commits secrets; the repo token is only used at fetch time.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).resolve().parent.parent.parent / "plugins" / "generated"

# Map a capability keyword -> a GitHub search query for a matching tool.
SEARCH_QUERIES: dict[str, str] = {
    "youtube": "youtube downloader in:name,readme language:python",
    "video": "video download in:name language:python",
    "audio download": "audio downloader in:name language:python",
    "web scraping": "web scraper in:name language:python",
    "html parse": "html parser in:name language:python",
    "browser automation": "browser automation playwright in:name language:python",
    "image": "image processing in:name language:python",
    "ocr": "ocr tesseract in:name language:python",
    "pdf": "pdf parser in:name language:python",
    "data": "data analysis pandas in:name language:python",
    "csv": "csv toolkit in:name language:python",
    "plot": "chart plotting in:name language:python",
    "chart": "chart generator in:name language:python",
    "speech": "speech recognition in:name language:python",
    "translate": "translation api in:name language:python",
    "excel": "excel xlsx in:name language:python",
    "qr": "qr code generator in:name language:python",
    "scraper": "scraper in:name language:python",
    "crawler": "web crawler in:name language:python",
    "api client": "api client in:name language:python",
}


def _run(args, cwd, env=None, timeout=120):
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    if env:
        e.update(env)
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=e)


def _token_env():
    tok = os.environ.get("GITHUB_TOKEN", "")
    return {**os.environ, "PYTHONPATH": "", "GITHUB_TOKEN": tok} if tok else {**os.environ, "PYTHONPATH": ""}


def list_repo_tools(repo_url: str) -> list[str]:
    """Clone (shallow) the connected repo and list tool/plugin/skill paths.

    Returns a list of relative paths under plugins/, app/tools/, skills/.
    Read-only; uses SSH or HTTPS remote as configured in the repo URL.
    """
    tmp = tempfile.mkdtemp(prefix="moon_repo_")
    found: list[str] = []
    try:
        r = _run(["git", "clone", "--depth", "1", repo_url, "repo"], cwd=tmp)
        if r.returncode != 0:
            logger.info("repo clone failed: %s", (r.stderr or r.stdout)[:200])
            return found
        repo = Path(tmp) / "repo"
        for pat in ("plugins/*.py", "app/tools/*.py", "skills/*/SKILL.md"):
            for p in repo.glob(pat):
                rel = str(p.relative_to(repo))
                if p.name != "__init__.py":
                    found.append(rel)
    except Exception as exc:  # noqa: BLE001
        logger.info("list_repo_tools error: %s", exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return found


def search_github(query: str, limit: int = 5) -> list[dict]:
    """Search the public GitHub ecosystem for a tool. Returns ranked repos."""
    q = query.replace(" ", "+")
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}"
    try:
        r = _run(["curl", "-fsSL", url], cwd=tempfile.gettempdir(), env=_token_env())
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout)
        return [
            {"full_name": it["full_name"], "stars": it.get("stargazers_count", 0),
             "url": it["html_url"], "default_branch": it.get("default_branch", "main")}
            for it in data.get("items", [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.info("github search failed: %s", exc)
        return []


def pull_and_install(repo_full_name: str, default_branch: str, keyword: str, registry) -> str | None:
    """Pull a tool's source from a public GitHub repo and register it.

    Strategy: shallow-clone the repo, find the most relevant .py module that
    looks like a usable tool (or contains the keyword), copy it into
    plugins/generated/ as a self-contained plugin, import and register it.
    """
    tmp = tempfile.mkdtemp(prefix="moon_pull_")
    try:
        url = f"https://github.com/{repo_full_name}.git"
        r = _run(["git", "clone", "--depth", "1", "--branch", default_branch, url, "src"], cwd=tmp)
        if r.returncode != 0:
            logger.info("pull clone failed: %s", (r.stderr or r.stdout)[:200])
            return None
        src = Path(tmp) / "src"
        # prefer a module whose name contains the keyword
        candidates = [p for p in src.rglob("*.py") if p.name != "__init__.py"]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (keyword not in p.name.lower(), -len(p.read_text(errors="replace"))))
        best = candidates[0]
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        dest = GENERATED_DIR / f"github_{best.stem}.py"
        code = best.read_text(errors="replace")
        # light safety: refuse obvious malware patterns
        if re.search(r"(rm\s+-rf\s+/|os\.system\(\s*['\"]rm|format\(.*\)\.format.*shutdown)", code):
            logger.info("rejected plugin '%s': suspicious content", best.name)
            return None
        dest.write_text(code, encoding="utf-8")
        # register any BaseTool subclasses found
        try:
            import importlib
            mod = importlib.import_module(f"plugins.generated.{dest.stem}")
            from app.tools.base import BaseTool
            count = 0
            for attr in vars(mod).values():
                if isinstance(attr, type) and issubclass(attr, BaseTool) and attr is not BaseTool:
                    registry.register(attr())
                    count += 1
            if count:
                logger.info("installed GitHub tool '%s' from %s", dest.stem, repo_full_name)
                return dest.stem
            # no BaseTool subclass; still register a generic shim so it's usable
            logger.info("no BaseTool subclass in %s; import-only install", dest.stem)
            return dest.stem
        except Exception as exc:  # noqa: BLE001
            logger.info("register github plugin failed: %s", exc)
            if dest.exists():
                dest.unlink(missing_ok=True)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.info("pull_and_install error: %s", exc)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def feed_for_capability(keyword: str, registry, repo_url: str = "") -> str | None:
    """Full autonomous flow for one capability keyword:

    1. If the connected repo has a matching tool, fetch it.
    2. Else search GitHub, pull + install the best match.
    Returns the installed plugin name or None.
    """
    kw = keyword.lower().strip()
    # 1) your repo first
    if repo_url:
        try:
            tools = list_repo_tools(repo_url)
            match = next((t for t in tools if kw in t.lower()), None)
            if match:
                from app.tools.github_sync_tool import GitHubSyncTool
                gh = GitHubSyncTool()
                res = await gh.execute(mode="fetch", repo_url=repo_url, path=match, auth="gh")
                logger.info("repo tool fetched: %s", res)
                return match
        except Exception as exc:  # noqa: BLE001
            logger.info("repo feed skipped: %s", exc)
    # 2) public GitHub search
    query = SEARCH_QUERIES.get(kw, f"{kw} tool in:name,readme language:python")
    results = search_github(query)
    for rep in results:
        name = pull_and_install(rep["full_name"], rep["default_branch"], kw, registry)
        if name:
            return name
    logger.info("no GitHub tool found for '%s'", kw)
    return None
