"""Capability system -- MOON's autonomous capability-management subsystem.

ADDITIVE: this package never replaces existing MOON modules. It reuses the
existing ToolRegistry / BaseTool / SafetyValidator / ErrorRecovery / Planner
/ GitHub integration and layers a persistent Capability Manager on top.

Logical components (per the integration spec):
  * CapabilityManager   -- orchestrates the acquisition loop
  * ToolRegistry        -- persistent capability registry (registry.json)
  * DiscoveryEngine     -- task -> required capabilities
  * GitHubRetriever     -- search/inspect/trust-evaluate repositories
  * DependencyAnalyzer  -- read manifests, resolve deps
  * InstallationManager -- safe install via supported package managers
  * SandboxExecutor     -- run installs/tests in isolation
  * PermissionManager   -- minimal default permissions + approval levels
  * VerificationEngine  -- health-test acquired capabilities
  * SelfRepairEngine    -- bounded recovery for recoverable errors
  * CapabilityCache     -- reuse verified capabilities
"""

from __future__ import annotations

from app.capability.manager import CapabilityManager
from app.capability.registry import CapabilityRegistry, CapabilityRecord
from app.capability.permission_manager import PermissionManager, PolicyLevel
from app.capability.tool import CapabilityManagerTool
from app.capability.sandbox import SandboxExecutor
from app.capability.installer import InstallationManager
from app.capability.verification import VerificationEngine
from app.capability.self_repair import SelfRepairEngine
from app.capability.github_retriever import GitHubRetriever
from app.capability.dependency_analyzer import analyze_path, analyze_text

__all__ = [
    "CapabilityManager",
    "CapabilityRegistry",
    "CapabilityRecord",
    "PermissionManager",
    "PolicyLevel",
    "CapabilityManagerTool",
    "SandboxExecutor",
    "InstallationManager",
    "VerificationEngine",
    "SelfRepairEngine",
    "GitHubRetriever",
    "analyze_path",
    "analyze_text",
]
