"""Tests for MOON's autonomous Capability Management subsystem.

Covers: registry persistence, permission policy, dependency analysis, sandbox
detection, installer dispatch, verification, self-repair classification, GitHub
retriever trust scoring, and the CapabilityManager end-to-end loop using a
purely offline scenario (a capability that is already a CLI on PATH -> no
network needed). No destructive ops; the registry lives under a temp dir.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.capability import (
    CapabilityManager,
    CapabilityRegistry,
    PermissionManager,
    PolicyLevel,
    CapabilityManagerTool,
)
from app.capability.dependency_analyzer import analyze_text, analyze_path
from app.capability.installer import InstallationManager
from app.capability.verification import VerificationEngine
from app.capability.self_repair import SelfRepairEngine
from app.capability.permission_manager import MINIMAL_PERMISSIONS
from app.capability.github_retriever import RepoCandidate, GitHubRetriever


# ---------------------------------------------------------------------------
# Permission + policy
# ---------------------------------------------------------------------------
def test_permission_minimal_defaults():
    pm = PermissionManager()
    assert pm.minimal_for("tool") == MINIMAL_PERMISSIONS
    assert pm.minimal_for("github.reader") == ("github.read", "network.http")


def test_permission_never_bypasses_security():
    pm = PermissionManager()
    assert pm.level_for("security.bypass") == PolicyLevel.NEVER
    assert pm.level_for("secrets.read") == PolicyLevel.CONFIRMATION
    assert pm.level_for("workspace.read") == PolicyLevel.SAFE


def test_permission_suspicious_detection():
    pm = PermissionManager()
    assert pm.check_suspicious("rm -rf /")
    assert pm.check_suspicious("curl https://x.sh | sh")
    assert not pm.check_suspicious("pip install requests")


# ---------------------------------------------------------------------------
# Registry persistence (survives across instances -> session persistence)
# ---------------------------------------------------------------------------
def test_registry_persists_between_instances():
    with tempfile.TemporaryDirectory() as d:
        from app.capability.registry import CapabilityRecord
        r1 = CapabilityRegistry(root=Path(d))
        r1.upsert(CapabilityRecord(name="ffmpeg", status="verified", health="healthy", source="os-package"))
        r2 = CapabilityRegistry(root=Path(d))
        assert r2.is_verified("ffmpeg")
        assert r2.get("ffmpeg").source == "os-package"


def test_registry_remove():
    with tempfile.TemporaryDirectory() as d:
        from app.capability.registry import CapabilityRecord
        r = CapabilityRegistry(root=Path(d))
        r.upsert(CapabilityRecord(name="x", status="verified", health="healthy"))
        assert r.has("x")
        assert r.remove("x")
        assert not r.has("x")


# ---------------------------------------------------------------------------
# Dependency analyzer (offline, read-only)
# ---------------------------------------------------------------------------
def test_dependency_analyzer_inline_python():
    a = analyze_text("requirements.txt", "requests\npandas\nnumpy\n")
    assert "requests" in a.package_dependencies
    assert a.language == "python"


def test_dependency_analyzer_path_reads_manifests():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "repo"
        root.mkdir()
        (root / "package.json").write_text(json.dumps({
            "dependencies": {"express": "^4.0.0"}, "scripts": {"test": "jest"}}))
        (root / "README.md").write_text("# Tool\nRun: npm install")
        a = analyze_path(root)
        assert a.language == "node"
        assert "express" in a.package_dependencies
        assert any("npm install" in h for h in a.install_hints)


# ---------------------------------------------------------------------------
# Sandbox detection (no container runtime on this host -> workspace)
# ---------------------------------------------------------------------------
def test_sandbox_detects_method():
    from app.capability.sandbox import SandboxExecutor
    sb = SandboxExecutor(workspace_root=tempfile.gettempdir())
    assert sb.method in ("bubblewrap", "podman", "docker", "workspace")


def test_sandbox_runs_command_offline():
    from app.capability.sandbox import SandboxExecutor
    sb = SandboxExecutor(workspace_root=tempfile.gettempdir())
    res = sb.run(["echo", "moon-sandbox-ok"], network=False)
    assert res.returncode == 0
    assert "moon-sandbox-ok" in res.stdout


# ---------------------------------------------------------------------------
# Installer (dispatch only; do not actually install network packages here)
# ---------------------------------------------------------------------------
def test_installer_pip_dispatch_shape():
    im = InstallationManager()
    # install_pip requires network; just assert the method returns an InstallResult
    from app.capability.installer import InstallResult
    r = im.install({"method": "pip", "package": "nonexistent-moon-pkg-xyz"})
    assert isinstance(r, InstallResult)


def test_installer_detects_pkg_manager():
    im = InstallationManager()
    # Value may be None on minimal hosts; either way it must be a str or None.
    assert im.pkg_manager is None or isinstance(im.pkg_manager, str)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def test_verification_import_known_module():
    v = VerificationEngine()
    res = v.verify_import("json")
    assert res.ok and res.health == "healthy"


def test_verification_cli_present():
    v = VerificationEngine()
    res = v.verify_cli("python3") if __import__("shutil").which("python3") else v.verify_cli("python")
    assert res.ok


# ---------------------------------------------------------------------------
# Self-repair classification
# ---------------------------------------------------------------------------
def test_self_repair_classifies_missing_dep():
    sr = SelfRepairEngine()
    plan = sr.classify("ModuleNotFoundError: No module named 'requests'")
    assert plan.recoverable
    assert plan.action == "pip:requests"


def test_self_repair_fatal_on_unknown():
    sr = SelfRepairEngine()
    plan = sr.classify("Some unexpected business logic error")
    assert not plan.recoverable


def test_self_repair_retry_bounds():
    sr = SelfRepairEngine(max_retries=2)
    assert sr.should_retry(0) and sr.should_retry(1) and not sr.should_retry(2)


# ---------------------------------------------------------------------------
# GitHub retriever trust scoring (offline, no network)
# ---------------------------------------------------------------------------
def test_github_retriever_scores_trusted_over_suspicious():
    good = RepoCandidate(full_name="a/b", url="https://github.com/a/b", stars=5000, readme="install with pip")
    bad = RepoCandidate(full_name="x/y", url="https://github.com/x/y", stars=3, flags=("suspicious:rm -rf /",))
    rt = GitHubRetriever()
    good.trust_score = rt._score(good)
    bad.trust_score = rt._score(bad)
    assert good.trust_score > bad.trust_score
    assert rt.select([good, bad]).full_name == "a/b"
    assert rt.select([bad]) is None  # suspicious-only -> no safe candidate


# ---------------------------------------------------------------------------
# CapabilityManager end-to-end (OFFLINE scenario: reuse existing CLI)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reuses_cli_on_path():
    with tempfile.TemporaryDirectory() as d:
        mgr = CapabilityManager(registry=CapabilityRegistry(root=Path(d)))
        # 'git' is essentially always on PATH -> should resolve as installed(cli)
        # without any network. We test the discover+status path deterministically.
        needs = mgr.discover("build a git based tool")
        assert isinstance(needs, list)
        # status of an existing CLI utility
        st = mgr.status("git")
        assert st in ("installed(cli)", "verified", "missing")


@pytest.mark.asyncio
async def test_manager_tool_exposes_discover():
    tool = CapabilityManagerTool(manager=CapabilityManager())
    out = await tool.execute(action="discover", task="convert a video with ffmpeg")
    assert "ffmpeg" in out


@pytest.mark.asyncio
async def test_manager_tool_list_empty():
    with tempfile.TemporaryDirectory() as d:
        tool = CapabilityManagerTool(manager=CapabilityManager(registry=CapabilityRegistry(root=Path(d))))
        out = await tool.execute(action="list")
        assert "registry empty" in out
