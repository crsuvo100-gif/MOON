"""Tests for specialist agents — WebAgent, SecurityAgent, GitHubAgent."""

from __future__ import annotations

import pytest

from app.agents.specialist import (
    WebAgent,
    WebAgentConfig,
    SecurityAgent,
    SecurityAgentConfig,
    GitHubAgent,
    GitHubAgentConfig,
)
from app.agents.specialist.web_agent import WebPage, APIEndpoint
from app.agents.specialist.security_agent import (
    RiskLevel,
    ScanType,
    Vulnerability,
    ScanResult,
    SecurityReport,
)
from app.agents.specialist.github_agent import (
    PRState,
    IssueState,
    Repository,
    PullRequest,
    Issue,
    Release,
)


class TestWebAgent:
    """Test WebAgent specialist."""

    def test_config_defaults(self):
        config = WebAgentConfig()
        assert config.name == "web_agent"
        assert config.max_depth == 3
        assert config.max_pages_per_session == 50
        assert config.request_timeout == 30.0
        assert config.respect_robots_txt is True
        assert config.user_agent == "MOON-WebAgent/1.0"

    def test_agent_creation(self):
        agent = WebAgent()
        assert agent is not None
        assert agent.config.name == "web_agent"

    def test_agent_with_custom_config(self):
        config = WebAgentConfig(max_depth=5, request_timeout=60.0)
        agent = WebAgent(config=config)
        assert agent.config.max_depth == 5
        assert agent.config.request_timeout == 60.0

    def test_web_page_dataclass(self):
        page = WebPage(
            url="https://example.com",
            title="Example",
            content="Test content",
            links=["https://example.com/about"],
        )
        assert page.url == "https://example.com"
        assert page.title == "Example"
        assert len(page.links) == 1

    def test_api_endpoint_dataclass(self):
        endpoint = APIEndpoint(
            url="https://api.example.com",
            method="GET",
            parameters={"q": "test"},
        )
        assert endpoint.url == "https://api.example.com"
        assert endpoint.method == "GET"


class TestSecurityAgent:
    """Test SecurityAgent specialist."""

    def test_config_defaults(self):
        config = SecurityAgentConfig()
        assert config.name == "security_agent"
        assert config.max_scan_targets == 100
        assert config.scan_timeout == 300.0
        assert config.auto_exploit is False

    def test_agent_creation(self):
        agent = SecurityAgent()
        assert agent is not None
        assert agent.config.name == "security_agent"

    def test_risk_level_enum(self):
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.INFO.value == "info"

    def test_scan_type_enum(self):
        assert ScanType.NETWORK.value == "network"
        assert ScanType.WEB.value == "web"
        assert ScanType.INFRASTRUCTURE.value == "infrastructure"

    def test_vulnerability_dataclass(self):
        vuln = Vulnerability(
            id="CVE-2024-0001",
            title="SQL Injection",
            description="SQL injection in login form",
            severity=RiskLevel.CRITICAL,
            remediation="Use parameterized queries",
        )
        assert vuln.id == "CVE-2024-0001"
        assert vuln.title == "SQL Injection"
        assert vuln.severity == RiskLevel.CRITICAL

    def test_scan_result_dataclass(self):
        result = ScanResult(
            scan_id="scan_001",
            target="example.com",
            scan_type=ScanType.WEB,
            started_at=1000.0,
            finished_at=1120.0,
        )
        assert result.target == "example.com"
        assert result.scan_type == ScanType.WEB
        assert result.status == "running"

    def test_security_report_dataclass(self):
        report = SecurityReport(
            report_id="report_001",
            target="example.com",
            scan_type=ScanType.WEB,
            started_at=1000.0,
            recommendations=["Update dependencies"],
        )
        assert report.target == "example.com"
        assert report.scan_type == ScanType.WEB


class TestGitHubAgent:
    """Test GitHubAgent specialist."""

    def test_config_defaults(self):
        config = GitHubAgentConfig()
        assert config.name == "github_agent"
        assert config.auto_merge is False
        assert config.require_reviews == 1
        assert config.require_ci_pass is True

    def test_agent_creation(self):
        agent = GitHubAgent()
        assert agent is not None
        assert agent.config.name == "github_agent"

    def test_pr_state_enum(self):
        assert PRState.OPEN.value == "open"
        assert PRState.CLOSED.value == "closed"
        assert PRState.MERGED.value == "merged"
        assert PRState.DRAFT.value == "draft"

    def test_issue_state_enum(self):
        assert IssueState.OPEN.value == "open"
        assert IssueState.CLOSED.value == "closed"

    def test_repository_dataclass(self):
        repo = Repository(
            name="test-repo",
            full_name="test-owner/test-repo",
            description="A test repo",
            stars=100,
            language="Python",
        )
        assert repo.name == "test-repo"
        assert repo.full_name == "test-owner/test-repo"
        assert repo.stars == 100

    def test_pull_request_dataclass(self):
        pr = PullRequest(
            number=1,
            title="Fix bug",
            state=PRState.OPEN,
            author="test-user",
            source_branch="fix/bug",
            target_branch="main",
        )
        assert pr.number == 1
        assert pr.state == PRState.OPEN

    def test_issue_dataclass(self):
        issue = Issue(
            number=1,
            title="Bug report",
            state=IssueState.OPEN,
            author="test-user",
            labels=["bug"],
        )
        assert issue.number == 1
        assert issue.state == IssueState.OPEN

    def test_release_dataclass(self):
        release = Release(
            tag="v1.0.0",
            name="First Release",
            draft=False,
        )
        assert release.tag == "v1.0.0"
        assert release.draft is False
