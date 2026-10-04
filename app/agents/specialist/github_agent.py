"""GitHub Agent — dedicated GitHub repository management and workflow.

Extends BaseAgent with domain-specific capabilities for:
- Repository management (create, fork, clone, configure)
- Pull request workflow (create, review, merge)
- Issue tracking (create, triage, close)
- Code review and quality checks
- Release management
- GitHub Actions workflow management

The GitHub Agent has its own brain (model), context, memory, and tool set.
It communicates with the Main Brain via the AgentCommunicationBus.
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


class PRState(str, Enum):
    """Pull request states."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class IssueState(str, Enum):
    """Issue states."""

    OPEN = "open"
    CLOSED = "closed"
    IN_PROGRESS = "in_progress"
    TRIAGED = "triaged"


@dataclass
class GitHubAgentConfig:
    """Configuration for the GitHub Agent."""

    name: str = "github_agent"
    max_repos: int = 50
    max_prs_per_session: int = 20
    max_issues_per_session: int = 50
    default_branch: str = "main"
    require_reviews: int = 1
    require_ci_pass: bool = True
    auto_merge: bool = False  # Never auto-merge; always require authorization
    commit_message_template: str = "[MOON] {description}"


@dataclass
class Repository:
    """A GitHub repository."""

    name: str
    full_name: str
    description: str = ""
    url: str = ""
    default_branch: str = "main"
    private: bool = False
    language: str = ""
    stars: int = 0
    forks: int = 0
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PullRequest:
    """A GitHub pull request."""

    number: int
    title: str
    state: PRState
    author: str
    source_branch: str
    target_branch: str
    description: str = ""
    files_changed: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    created_at: float = field(default_factory=time.time)
    merged_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Issue:
    """A GitHub issue."""

    number: int
    title: str
    state: IssueState
    author: str
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    description: str = ""
    comments: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    closed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Release:
    """A GitHub release."""

    tag: str
    name: str
    description: str = ""
    draft: bool = False
    prerelease: bool = False
    assets: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class GitHubAgent(BaseAgent):
    """Specialist agent for GitHub repository management and workflow.

    The GitHub Agent has its own brain (model), context, memory, and tool set.
    It communicates with the Main Brain via the AgentCommunicationBus.
    """

    def __init__(self, config: GitHubAgentConfig | None = None, main_brain=None, agent_models=None) -> None:
        self.config = config or GitHubAgentConfig()
        super().__init__(self.config.name, main_brain=main_brain, agent_models=agent_models)
        self._repos: dict[str, Repository] = {}
        self._prs: dict[str, PullRequest] = {}
        self._issues: dict[str, Issue] = {}
        self._releases: dict[str, Release] = {}
        self._session_start: float = time.time()
        self._bus: AgentCommunicationBus = get_bus()

    async def setup(self) -> None:
        """Set up the GitHub Agent."""
        await super().setup()
        await self.memory_store(
            content="GitHub Agent initialized. "
                    f"Default branch: {self.config.default_branch}, "
                    f"Require reviews: {self.config.require_reviews}, "
                    f"Auto-merge: {self.config.auto_merge} (NEVER auto-merge).",
            memory_type="procedural",
            importance=0.8,
            scope="AGENT",
        )

    async def teardown(self) -> None:
        """Tear down the GitHub Agent."""
        await self.memory_store(
            content=f"GitHub Agent session complete. "
                    f"Repos: {len(self._repos)}, PRs: {len(self._prs)}, "
                    f"Issues: {len(self._issues)}",
            memory_type="episodic",
            importance=0.5,
            scope="AGENT",
        )
        await super().teardown()

    async def create_repo(self, name: str, *, description: str = "", private: bool = False) -> Repository | None:
        """Create a new GitHub repository.

        Args:
            name: Repository name.
            description: Repository description.
            private: Whether the repo is private.

        Returns:
            Created Repository, or None if creation failed.
        """
        task = f"Create a new GitHub repository named '{name}' with description '{description}' "
        f"and private={private}. Return as JSON with keys: name, full_name, url, default_branch."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                repo = Repository(
                    name=data.get("name", name),
                    full_name=data.get("full_name", name),
                    description=description,
                    url=data.get("url", ""),
                    default_branch=data.get("branch", self.config.default_branch),
                    private=private,
                )
                self._repos[repo.full_name] = repo
                await self._report_progress(f"Created repository: {repo.full_name}")
                return repo
            return None
        except Exception as e:
            await self._report_error(f"Failed to create repo '{name}': {e}")
            return None

    async def create_pr(
        self,
        repo: str,
        title: str,
        source_branch: str,
        target_branch: str | None = None,
        description: str = "",
    ) -> PullRequest | None:
        """Create a pull request.

        Args:
            repo: Repository full name.
            title: PR title.
            source_branch: Source branch.
            target_branch: Target branch (defaults to repo default).
            description: PR description.

        Returns:
            Created PullRequest, or None if creation failed.
        """
        target = target_branch or self.config.default_branch
        task = f"Create a pull request in '{repo}' from '{source_branch}' to '{target}' "
        f"with title '{title}' and description '{description}'. "
        "Return as JSON with keys: number, title, state, author, source_branch, target_branch."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                pr = PullRequest(
                    number=data.get("number", 0),
                    title=data.get("title", title),
                    state=PRState(data.get("state", "open")),
                    author=data.get("author", ""),
                    source_branch=data.get("source_branch", source_branch),
                    target_branch=data.get("target_branch", target),
                    description=description,
                )
                self._prs[f"{repo}#{pr.number}"] = pr
                await self._report_progress(f"Created PR #{pr.number}: {title}")
                return pr
            return None
        except Exception as e:
            await self._report_error(f"Failed to create PR '{title}': {e}")
            return None

    async def review_pr(self, repo: str, pr_number: int) -> dict[str, Any] | None:
        """Review a pull request.

        Args:
            repo: Repository full name.
            pr_number: PR number.

        Returns:
            Dict with review results, or None if review failed.
        """
        task = f"Review pull request #{pr_number} in '{repo}'. "
        "Evaluate: 1) code quality, 2) test coverage, 3) documentation, "
        "4) security concerns, 5) breaking changes. "
        "Return as JSON with keys: approved (bool), comments (list), score (float)."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                await self._report_progress(
                    f"Reviewed PR #{pr_number}: approved={data.get('approved', False)}"
                )
                return data
            return None
        except Exception as e:
            await self._report_error(f"Failed to review PR #{pr_number}: {e}")
            return None

    async def create_issue(
        self,
        repo: str,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
    ) -> Issue | None:
        """Create a GitHub issue.

        Args:
            repo: Repository full name.
            title: Issue title.
            body: Issue body.
            labels: Issue labels.

        Returns:
            Created Issue, or None if creation failed.
        """
        task = f"Create an issue in '{repo}' with title '{title}' and body '{body}'. "
        f"Labels: {labels or []}. "
        "Return as JSON with keys: number, title, state, author, labels."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                issue = Issue(
                    number=data.get("number", 0),
                    title=data.get("title", title),
                    state=IssueState(data.get("state", "open")),
                    author=data.get("author", ""),
                    labels=data.get("labels", labels or []),
                    description=body,
                )
                self._issues[f"{repo}#{issue.number}"] = issue
                await self._report_progress(f"Created issue #{issue.number}: {title}")
                return issue
            return None
        except Exception as e:
            await self._report_error(f"Failed to create issue '{title}': {e}")
            return None

    async def triage_issue(self, repo: str, issue_number: int) -> Issue | None:
        """Triage a GitHub issue.

        Args:
            repo: Repository full name.
            issue_number: Issue number.

        Returns:
            Triaged Issue, or None if triage failed.
        """
        task = f"Triage issue #{issue_number} in '{repo}'. "
        "Classify: 1) bug/feature/question/documentation, 2) priority (P0-P3), "
        "3) effort estimate, 4) suggested labels. "
        "Return as JSON with keys: type, priority, effort, labels."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                issue = self._issues.get(f"{repo}#{issue_number}")
                if issue:
                    issue.labels = data.get("labels", issue.labels)
                    issue.state = IssueState.TRIAGED
                    await self._report_progress(
                        f"Triaged issue #{issue_number}: {data.get('type', 'unknown')}"
                    )
                return issue
            return None
        except Exception as e:
            await self._report_error(f"Failed to triage issue #{issue_number}: {e}")
            return None

    async def create_release(
        self,
        repo: str,
        tag: str,
        name: str,
        description: str = "",
        *,
        draft: bool = False,
        prerelease: bool = False,
    ) -> Release | None:
        """Create a GitHub release.

        Args:
            repo: Repository full name.
            tag: Release tag.
            name: Release name.
            description: Release description.
            draft: Whether the release is a draft.
            prerelease: Whether the release is a prerelease.

        Returns:
            Created Release, or None if creation failed.
        """
        task = f"Create a release in '{repo}' with tag '{tag}' and name '{name}'. "
        f"Description: '{description}'. Draft: {draft}, Prerelease: {prerelease}. "
        "Return as JSON with keys: tag, name, draft, prerelease."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                release = Release(
                    tag=data.get("tag", tag),
                    name=data.get("name", name),
                    description=description,
                    draft=data.get("draft", draft),
                    prerelease=data.get("prerelease", prerelease),
                )
                self._releases[f"{repo}@{tag}"] = release
                await self._report_progress(f"Created release: {tag}")
                return release
            return None
        except Exception as e:
            await self._report_error(f"Failed to create release '{tag}': {e}")
            return None

    async def search_code(self, repo: str, query: str) -> list[dict[str, Any]]:
        """Search code in a repository.

        Args:
            repo: Repository full name.
            query: Search query.

        Returns:
            List of search results with file paths and snippets.
        """
        task = f"Search code in '{repo}' for '{query}'. "
        "Return as JSON with keys: results (list of {file, line, snippet, url})."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                return data.get("results", [])
            return []
        except Exception as e:
            await self._report_error(f"Code search failed: {e}")
            return []

    async def get_repo_info(self, repo: str) -> Repository | None:
        """Get information about a repository.

        Args:
            repo: Repository full name.

        Returns:
            Repository with metadata, or None if not found.
        """
        if repo in self._repos:
            return self._repos[repo]

        task = f"Get information about the GitHub repository '{repo}'. "
        "Return as JSON with keys: name, full_name, description, url, default_branch, private, language, stars, forks."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if data:
                repo_obj = Repository(
                    name=data.get("name", ""),
                    full_name=data.get("full_name", repo),
                    description=data.get("description", ""),
                    url=data.get("url", ""),
                    default_branch=data.get("default_branch", self.config.default_branch),
                    private=data.get("private", False),
                    language=data.get("language", ""),
                    stars=data.get("stars", 0),
                    forks=data.get("forks", 0),
                )
                self._repos[repo] = repo_obj
                return repo_obj
            return None
        except Exception as e:
            await self._report_error(f"Failed to get repo info for '{repo}': {e}")
            return None

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
        """Get GitHub Agent statistics."""
        return {
            "agent": self.config.name,
            "repos_managed": len(self._repos),
            "prs_created": len(self._prs),
            "issues_created": len(self._issues),
            "releases_created": len(self._releases),
            "session_duration": time.time() - self._session_start,
        }


__all__ = [
    "GitHubAgent",
    "GitHubAgentConfig",
    "Repository",
    "PullRequest",
    "Issue",
    "Release",
    "PRState",
    "IssueState",
]
