"""Security Agent — dedicated security assessment and pentest coordination.

Extends BaseAgent with domain-specific capabilities for:
- Network reconnaissance and scanning
- Vulnerability assessment
- Security audit and compliance checking
- Pentest coordination and reporting
- Threat modeling

The Security Agent has its own brain (model), context, memory, and tool set.
It communicates with the Main Brain via the AgentCommunicationBus.

IMPORTANT: This agent is for AUTHORIZED security testing only. It must only
be used on systems you own or have explicit permission to test.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.agents.base import BaseAgent
from app.agents.communication_protocol import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
    get_bus,
    new_task_id,
)


class RiskLevel(str, Enum):
    """Security risk levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanType(str, Enum):
    """Types of security scans."""

    NETWORK = "network"
    WEB = "web"
    API = "api"
    INFRASTRUCTURE = "infrastructure"
    CODE = "code"
    COMPLIANCE = "compliance"


@dataclass
class SecurityAgentConfig:
    """Configuration for the Security Agent."""

    name: str = "security_agent"
    max_scan_targets: int = 100
    scan_timeout: float = 300.0
    max_vulnerabilities: int = 500
    compliance_frameworks: list[str] = field(default_factory=lambda: ["OWASP", "NIST", "PCI-DSS"])
    severity_threshold: RiskLevel = RiskLevel.MEDIUM
    auto_exploit: bool = False  # Never auto-exploit; always require authorization
    report_format: str = "json"


@dataclass
class Vulnerability:
    """A discovered vulnerability."""

    id: str
    title: str
    description: str
    severity: RiskLevel
    cvss_score: float | None = None
    affected_target: str = ""
    remediation: str = ""
    references: list[str] = field(default_factory=list)
    discovered_at: float = field(default_factory=time.time)
    verified: bool = False
    false_positive: bool = False


@dataclass
class ScanResult:
    """Result of a security scan."""

    scan_id: str
    scan_type: ScanType
    target: str
    started_at: float
    finished_at: float | None = None
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"  # running, completed, failed
    error: str | None = None


@dataclass
class SecurityReport:
    """Comprehensive security report."""

    report_id: str
    target: str
    scan_type: ScanType
    started_at: float
    finished_at: float | None = None
    executive_summary: str = ""
    risk_summary: dict[str, int] = field(default_factory=dict)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    compliance_status: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class SecurityAgent(BaseAgent):
    """Specialist agent for security assessment and pentest coordination.

    The Security Agent has its own brain (model), context, memory, and tool set.
    It communicates with the Main Brain via the AgentCommunicationBus.

    IMPORTANT: This agent is for AUTHORIZED security testing only.
    """

    def __init__(self, config: SecurityAgentConfig | None = None, main_brain=None, agent_models=None) -> None:
        self.config = config or SecurityAgentConfig()
        super().__init__(self.config.name, main_brain=main_brain, agent_models=agent_models)
        self._scans: dict[str, ScanResult] = {}
        self._reports: dict[str, SecurityReport] = {}
        self._vulnerabilities: dict[str, Vulnerability] = {}
        self._session_start: float = time.time()
        self._bus: AgentCommunicationBus = get_bus()

    async def setup(self) -> None:
        """Set up the Security Agent."""
        await super().setup()
        await self.memory_store(
            content="Security Agent initialized. "
                    f"Compliance frameworks: {self.config.compliance_frameworks}. "
                    f"Auto-exploit: {self.config.auto_exploit} (NEVER auto-exploit).",
            memory_type="procedural",
            importance=0.9,
            scope="AGENT",
        )

    async def teardown(self) -> None:
        """Tear down the Security Agent."""
        await self.memory_store(
            content=f"Security Agent session complete. "
                    f"Scans: {len(self._scans)}, "
                    f"Vulnerabilities: {len(self._vulnerabilities)}",
            memory_type="episodic",
            importance=0.5,
            scope="AGENT",
        )
        await super().teardown()

    async def scan(self, target: str, scan_type: ScanType = ScanType.WEB) -> ScanResult:
        """Run a security scan against a target.

        Args:
            target: The target to scan (URL, IP, hostname, etc.).
            scan_type: The type of scan to run.

        Returns:
            ScanResult with discovered vulnerabilities.
        """
        scan_id = f"scan_{int(time.time())}_{scan_type.value}"
        result = ScanResult(
            scan_id=scan_id,
            scan_type=scan_type,
            target=target,
            started_at=time.time(),
        )
        self._scans[scan_id] = result

        # Report scan start
        await self._report_progress(f"Starting {scan_type.value} scan of {target}")

        # Build scan task based on type
        task = self._build_scan_task(target, scan_type)

        try:
            scan_result = await self.run(task)
            data = self._parse_json_result(scan_result)

            if data:
                # Parse vulnerabilities
                for vuln_data in data.get("vulnerabilities", []):
                    vuln = Vulnerability(
                        id=vuln_data.get("id", f"VULN-{len(self._vulnerabilities)}"),
                        title=vuln_data.get("title", ""),
                        description=vuln_data.get("description", ""),
                        severity=RiskLevel(vuln_data.get("severity", "medium")),
                        cvss_score=vuln_data.get("cvss_score"),
                        affected_target=target,
                        remediation=vuln_data.get("remediation", ""),
                        references=vuln_data.get("references", []),
                    )
                    self._vulnerabilities[vuln.id] = vuln
                    result.vulnerabilities.append(vuln)

                result.findings = data.get("findings", [])
                result.status = "completed"
            else:
                result.status = "failed"
                result.error = "No parseable results from scan"

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            await self._report_error(f"Scan failed: {e}")

        result.finished_at = time.time()

        # Report scan completion
        await self._report_progress(
            f"Scan {scan_id} complete: {len(result.vulnerabilities)} vulnerabilities found"
        )

        return result

    async def assess_vulnerability(self, target: str, vulnerability_id: str) -> Vulnerability | None:
        """Assess a specific vulnerability in detail.

        Args:
            target: The affected target.
            vulnerability_id: The vulnerability ID.

        Returns:
            Detailed Vulnerability object, or None if not found.
        """
        vuln = self._vulnerabilities.get(vulnerability_id)
        if not vuln:
            return None

        task = f"Assess the vulnerability '{vuln.title}' on {target}. "
        "Provide: 1) detailed technical analysis, 2) exploitation prerequisites, "
        "3) potential impact, 4) remediation steps with code examples. "
        "Return as JSON with keys: analysis, prerequisites, impact, remediation."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                vuln.description = data.get("analysis", vuln.description)
                vuln.remediation = data.get("remediation", vuln.remediation)
                vuln.verified = True
            return vuln
        except Exception as e:
            await self._report_error(f"Vulnerability assessment failed: {e}")
            return None

    async def generate_report(self, scan_id: str) -> SecurityReport | None:
        """Generate a comprehensive security report from a scan.

        Args:
            scan_id: The scan ID to generate a report for.

        Returns:
            SecurityReport with full analysis and recommendations.
        """
        scan = self._scans.get(scan_id)
        if not scan:
            return None

        report_id = f"report_{scan_id}"
        report = SecurityReport(
            report_id=report_id,
            target=scan.target,
            scan_type=scan.scan_type,
            started_at=scan.started_at,
            finished_at=scan.finished_at,
        )

        # Count vulnerabilities by severity
        severity_counts: dict[str, int] = {}
        for vuln in scan.vulnerabilities:
            sev = vuln.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        report.risk_summary = severity_counts

        # Generate executive summary using the brain
        task = f"Generate an executive summary for a security scan of {scan.target}. "
        f"Found {len(scan.vulnerabilities)} vulnerabilities: {severity_counts}. "
        "Provide: 1) executive summary, 2) key recommendations, 3) risk rating. "
        "Return as JSON with keys: executive_summary, recommendations, risk_rating."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                report.executive_summary = data.get("executive_summary", "")
                report.recommendations = data.get("recommendations", [])
        except Exception as e:
            await self._report_error(f"Report generation failed: {e}")

        report.vulnerabilities = scan.vulnerabilities
        self._reports[report_id] = report

        return report

    async def compliance_check(self, target: str, framework: str = "OWASP") -> dict[str, Any]:
        """Run a compliance check against a framework.

        Args:
            target: The target to check.
            framework: The compliance framework (OWASP, NIST, PCI-DSS).

        Returns:
            Dict with compliance status and findings.
        """
        task = f"Run a {framework} compliance check against {target}. "
        "Evaluate: 1) authentication, 2) authorization, 3) data protection, "
        "4) input validation, 5) error handling, 6) logging. "
        "Return as JSON with keys: compliant (bool), findings (list), score (float)."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                await self._report_progress(
                    f"Compliance check complete: {framework} score={data.get('score', 0)}"
                )
                return data
            return {"compliant": False, "findings": [], "score": 0.0, "error": "No results"}
        except Exception as e:
            await self._report_error(f"Compliance check failed: {e}")
            return {"compliant": False, "findings": [], "score": 0.0, "error": str(e)}

    async def threat_model(self, target: str) -> dict[str, Any]:
        """Generate a threat model for a target.

        Args:
            target: The target to model threats for.

        Returns:
            Dict with threat model including attack surface, threats, and mitigations.
        """
        task = f"Generate a threat model for {target}. "
        "Identify: 1) attack surface, 2) threat actors, 3) potential attack vectors, "
        "4) existing mitigations, 5) recommended mitigations. "
        "Return as JSON with keys: attack_surface, threat_actors, attack_vectors, mitigations."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                await self._report_progress(f"Threat model complete for {target}")
                return data
            return {"error": "No results"}
        except Exception as e:
            await self._report_error(f"Threat modeling failed: {e}")
            return {"error": str(e)}

    def _build_scan_task(self, target: str, scan_type: ScanType) -> str:
        """Build a scan task description based on scan type."""
        base = f"Perform a {scan_type.value} security scan of {target}. "
        if scan_type == ScanType.WEB:
            base += ("Check for: SQL injection, XSS, CSRF, SSRF, insecure headers, "
                     "sensitive data exposure, broken authentication. ")
        elif scan_type == ScanType.NETWORK:
            base += ("Check for: open ports, service versions, default credentials, "
                     "network segmentation issues, firewall misconfigurations. ")
        elif scan_type == ScanType.API:
            base += ("Check for: broken authentication, excessive data exposure, "
                     "lack of rate limiting, injection flaws, improper asset management. ")
        elif scan_type == ScanType.INFRASTRUCTURE:
            base += ("Check for: misconfigured containers, exposed secrets, "
                     "outdated software, weak encryption, insecure defaults. ")
        elif scan_type == ScanType.CODE:
            base += ("Check for: hardcoded credentials, insecure dependencies, "
                     "input validation issues, insecure crypto, code injection. ")
        elif scan_type == ScanType.COMPLIANCE:
            base += ("Check compliance against: " + ", ".join(self.config.compliance_frameworks) + ". ")
        base += "Return as JSON with keys: vulnerabilities (list of {id, title, description, severity, cvss_score, remediation}), findings (list)."
        return base

    def _parse_json_result(self, text: str) -> dict[str, Any] | None:
        """Parse a JSON result from the brain's output."""
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    async def _report_progress(self, message: str) -> None:
        """Report progress to the Main Brain."""
        await self._bus.publish(AgentMessage(
            task_id=new_task_id(),
            agent_id=self.config.name,
            message_type=MessageType.TASK_PROGRESS,
            result=message,
        ))

    async def _report_error(self, message: str) -> None:
        """Report an error to the Main Brain."""
        await self._bus.publish(AgentMessage(
            task_id=new_task_id(),
            agent_id=self.config.name,
            message_type=MessageType.TASK_FAILED,
            result=message,
            status="failed",
            errors=[message],
        ))

    def get_stats(self) -> dict[str, Any]:
        """Get Security Agent statistics."""
        return {
            "agent": self.config.name,
            "scans_run": len(self._scans),
            "vulnerabilities_found": len(self._vulnerabilities),
            "reports_generated": len(self._reports),
            "session_duration": time.time() - self._session_start,
            "compliance_frameworks": self.config.compliance_frameworks,
        }


__all__ = [
    "SecurityAgent",
    "SecurityAgentConfig",
    "Vulnerability",
    "ScanResult",
    "SecurityReport",
    "RiskLevel",
    "ScanType",
]
