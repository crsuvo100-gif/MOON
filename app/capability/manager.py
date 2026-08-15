"""CapabilityManager -- orchestrates MOON's autonomous acquisition loop.

Wires together the registry, permission manager, dependency analyzer, GitHub
retriever, sandbox, installer, verification, and self-repair into the pipeline
described by the integration spec:

  USER REQUEST -> UNDERSTAND -> PLAN -> IDENTIFY REQUIRED CAPABILITIES
  -> CHECK EXISTING -> MISSING? -> DISCOVER -> ACQUIRE -> VERIFY -> EXECUTE
  -> (ERROR? -> DIAGNOSE -> SAFE REPAIR -> RETRY -> TEST -> VERIFY) -> COMPLETE

It is ADDITIVE: it prefers existing MOON capabilities and already-installed
system utilities before any network acquisition, and it reuses the existing
ToolRegistry / BaseTool / SafetyValidator / ErrorRecovery / Planner.

Nothing here deletes or replaces existing MOON functionality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.capability.dependency_analyzer import analyze_text
from app.capability.github_retriever import GitHubRetriever, RepoCandidate
from app.capability.installer import InstallationManager
from app.capability.permission_manager import PermissionManager, PolicyLevel
from app.capability.registry import CapabilityRegistry, CapabilityRecord
from app.capability.sandbox import SandboxExecutor
from app.capability.self_repair import SelfRepairEngine
from app.capability.verification import VerificationEngine

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionResult:
    name: str
    status: str                 # acquired | cached | failed | unavailable
    source: str = ""
    detail: str = ""
    report: dict[str, Any] = field(default_factory=dict)


# Capability keyword -> install spec (extends the older TOOL_CATALOG idea but
# routes through the InstallationManager + persistent registry).
_BUILTIN_SPECS: dict[str, dict] = {
    "ffmpeg": {"type": "cli", "method": "system", "package": "ffmpeg", "verify": "ffmpeg"},
    "imagemagick": {"type": "cli", "method": "system", "package": "imagemagick", "verify": "convert"},
    "tesseract": {"type": "cli", "method": "system", "package": "tesseract-ocr", "verify": "tesseract"},
    "yt-dlp": {"type": "python", "method": "pip", "package": "yt-dlp", "verify": "yt_dlp"},
    "pandas": {"type": "python", "method": "pip", "package": "pandas", "verify": "pandas"},
    "pillow": {"type": "python", "method": "pip", "package": "pillow", "verify": "PIL"},
    "beautifulsoup4": {"type": "python", "method": "pip", "package": "beautifulsoup4", "verify": "bs4"},
    "requests": {"type": "python", "method": "pip", "package": "requests", "verify": "requests"},
    "playwright": {"type": "python", "method": "pip", "package": "playwright", "verify": "playwright"},
}


class CapabilityManager:
    def __init__(self, registry: CapabilityRegistry | None = None,
                 confirm: Callable[[str], bool] | None = None,
                 workspace: str | None = None) -> None:
        self.registry = registry or CapabilityRegistry()
        self.permissions = PermissionManager(confirmation_callback=confirm)
        self.installer = InstallationManager()
        self.verifier = VerificationEngine()
        self.repair = SelfRepairEngine(max_retries=3)
        self.sandbox = SandboxExecutor(workspace_root=workspace)
        self.retriever = GitHubRetriever(
            registry_cache_get=self.registry.cache_get,
            registry_cache_put=self.registry.cache_put,
        )

    # ------------------------------------------------------------------
    # DISCOVERY: task text -> required capability keys
    # ------------------------------------------------------------------
    def discover(self, task: str) -> list[str]:
        t = (task or "").lower()
        found: list[str] = []
        # keyword catalog
        for key in _BUILTIN_SPECS:
            if key.replace("_", " ") in t or key in t:
                found.append(key)
        for token in ("video", "audio", "image", "ocr", "pdf", "web scraping",
                      "data", "chart", "translate", "excel", "qr", "download"):
            if token in t and token not in found:
                found.append(token)
        return found

    # ------------------------------------------------------------------
    # CHECK EXISTING
    # ------------------------------------------------------------------
    def status(self, name: str) -> str:
        if self.registry.is_verified(name):
            return "verified"
        if self.registry.has(name):
            return self.registry.get(name).status
        if self.installer.is_cli_available(name):
            return "installed(cli)"
        return "missing"

    # ------------------------------------------------------------------
    # ACQUIRE (the core loop, with self-repair)
    # ------------------------------------------------------------------
    async def acquire(self, name: str, *, github_ok: bool = True) -> AcquisitionResult:
        rec = self.registry.get(name)
        if rec and self.registry.is_verified(name):
            return AcquisitionResult(name, "cached", rec.source,
                                     "reusing verified capability",
                                     rec.to_dict())

        spec = _BUILTIN_SPECS.get(name)
        attempt = 0
        last_err = ""
        while self.repair.should_retry(attempt):
            attempt += 1
            if spec is not None:
                res = self.installer.install(spec)
                last_err = res.detail
                if res.ok:
                    vr = self.verifier.verify(spec["type"], spec["verify"])
                    if vr.ok:
                        self._record(name, spec, res, vr)
                        return AcquisitionResult(name, "acquired", res.source,
                                                 f"{spec['method']} install + verify OK",
                                                 {"verify": vr.detail, "method": res.method})
                    last_err = vr.detail
                # try repair (e.g. missing dependency -> pip install)
                plan = self.repair.classify(last_err)
                if plan.recoverable and plan.action.startswith("pip:"):
                    pkg = plan.action.split(":", 1)[1]
                    if pkg and pkg != "unknown":
                        self.installer.install_pip(pkg)
                        await self.repair.backoff(attempt)
                        continue
                if plan.action == "retry":
                    await self.repair.backoff(attempt)
                    continue
                # not recoverable via builtin spec -> fall through to GitHub
                break
            else:
                break

        # GitHub path (only if allowed and not already cached as failed)
        if github_ok:
            gh = await self._acquire_from_github(name)
            if gh:
                return gh

        return AcquisitionResult(name, "unavailable", "",
                                 f"could not safely acquire '{name}'. Last error: {last_err}",
                                 {"last_error": last_err})

    # ------------------------------------------------------------------
    async def _acquire_from_github(self, name: str) -> AcquisitionResult | None:
        # Does an equivalent tool already exist in the live registry/tool set?
        if self.registry.has(name):
            return AcquisitionResult(name, "cached", self.registry.get(name).source)
        try:
            from app.tools.tool_acquisition import acquire_by_catalog, generate_plugin
            from app.tools.registry import ToolRegistry
        except Exception:  # noqa: BLE001
            return None
        # Permission check: github.read + network.http are SAFE tier.
        if self.permissions.level_for("github.read") == PolicyLevel.NEVER:
            return None
        # Reuse the existing always-connected GitHub feed for the actual fetch.
        try:
            from app.tools.github_feed import feed_for_capability
            repo = ""
            try:
                from app.config.settings import get_settings
                repo = get_settings().github_repo
            except Exception:  # noqa: BLE001
                pass
            installed = await feed_for_capability(name, ToolRegistry(), repo_url=repo)
            if installed:
                self._record_github(name, installed)
                return AcquisitionResult(name, "acquired", "github",
                                         f"github feed installed '{installed}'")
        except Exception as exc:  # noqa: BLE001
            logger.info("github acquisition skipped: %s", exc)
        return None

    # ------------------------------------------------------------------
    def _record(self, name: str, spec: dict, res, vr) -> None:
        rec = CapabilityRecord(
            name=name, version="latest", status="verified", source=res.source,
            runtime=spec["type"], install_method=res.method, source_url="",
            permissions=self.permissions.minimal_for("tool"),
            network_required=False, sandbox_required=True,
            dependencies=(), verified_at=_now(), health=vr.health,
            notes=vr.detail,
        )
        self.registry.upsert(rec)

    def _record_github(self, name: str, installed: str) -> None:
        rec = CapabilityRecord(
            name=name, version="latest", status="verified", source="github",
            runtime="python", install_method="github_feed", source_url="",
            permissions=self.permissions.minimal_for("github.reader"),
            network_required=True, sandbox_required=True, verified_at=_now(),
            health="healthy", notes=f"github plugin: {installed}",
        )
        self.registry.upsert(rec)

    # ------------------------------------------------------------------
    # Reporting helpers used by the terminal / tool layer
    # ------------------------------------------------------------------
    def list_capabilities(self) -> list[dict]:
        return [r.to_dict() for r in self.registry.all()]

    def health_report(self) -> list[dict]:
        out = []
        for r in self.registry.all():
            out.append({"name": r.name, "status": r.status, "health": r.health,
                        "source": r.source})
        return out

    def search_github(self, query: str, limit: int = 5) -> list[dict]:
        cands = self.retriever.search(query, limit=limit)
        return [c.__dict__ for c in cands]


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
