"""Web Agent — dedicated web browsing, scraping, and API interaction.

Extends BaseAgent with domain-specific capabilities for:
- Web page fetching and content extraction
- API discovery and interaction
- Web research and information gathering
- Form interaction and data extraction

The Web Agent has its own brain (model), context, memory, and tool set.
It communicates with the Main Brain via the AgentCommunicationBus.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from app.agents.base import BaseAgent
from app.agents.communication_protocol import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
    get_bus,
    new_task_id,
)


@dataclass
class WebAgentConfig:
    """Configuration for the Web Agent."""

    name: str = "web_agent"
    max_depth: int = 3
    max_pages_per_session: int = 50
    request_timeout: float = 30.0
    respect_robots_txt: bool = True
    user_agent: str = "MOON-WebAgent/1.0"
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class WebPage:
    """A fetched web page with extracted content."""

    url: str
    title: str
    content: str
    links: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: float = field(default_factory=time.time)
    status_code: int = 200


@dataclass
class APIEndpoint:
    """A discovered API endpoint."""

    url: str
    method: str
    parameters: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    discovered_at: float = field(default_factory=time.time)


class WebAgent(BaseAgent):
    """Specialist agent for web browsing, scraping, and API interaction.

    The Web Agent has its own brain (model), context, memory, and tool set.
    It communicates with the Main Brain via the AgentCommunicationBus.
    """

    def __init__(self, config: WebAgentConfig | None = None, main_brain=None, agent_models=None) -> None:
        self.config = config or WebAgentConfig()
        super().__init__(self.config.name, main_brain=main_brain, agent_models=agent_models)
        self._pages: dict[str, WebPage] = {}
        self._endpoints: dict[str, APIEndpoint] = {}
        self._session_start: float = time.time()
        self._bus: AgentCommunicationBus = get_bus()

    async def setup(self) -> None:
        """Set up the Web Agent."""
        await super().setup()
        # Store agent-specific memory
        await self.memory_store(
            content="Web Agent initialized with config: "
                    f"max_depth={self.config.max_depth}, "
                    f"max_pages={self.config.max_pages_per_session}",
            memory_type="procedural",
            importance=0.7,
            scope="AGENT",
        )

    async def teardown(self) -> None:
        """Tear down the Web Agent."""
        # Store session summary
        await self.memory_store(
            content=f"Web Agent session complete. "
                    f"Pages fetched: {len(self._pages)}, "
                    f"Endpoints discovered: {len(self._endpoints)}",
            memory_type="episodic",
            importance=0.5,
            scope="AGENT",
        )
        await super().teardown()

    async def fetch_page(self, url: str, *, depth: int = 0) -> WebPage | None:
        """Fetch a web page and extract its content.

        Args:
            url: The URL to fetch.
            depth: Current crawl depth.

        Returns:
            WebPage with extracted content, or None if fetch failed.
        """
        if depth > self.config.max_depth:
            return None

        if len(self._pages) >= self.config.max_pages_per_session:
            return None

        # Check domain restrictions
        parsed = urlparse(url)
        if self.config.allowed_domains and parsed.hostname not in self.config.allowed_domains:
            return None
        if parsed.hostname in self.config.blocked_domains:
            return None

        # Use the brain to fetch and extract content
        task = f"Fetch the web page at {url} and extract: 1) the page title, "
        "2) the main text content, 3) all links found on the page. "
        "Return the result as JSON with keys: title, content, links."

        try:
            result = await self.run(task)
            # Parse the result
            data = self._parse_json_result(result)
            if not data:
                return None

            page = WebPage(
                url=url,
                title=data.get("title", ""),
                content=data.get("content", ""),
                links=data.get("links", []),
                metadata={"depth": depth, "agent": self.config.name},
            )
            self._pages[url] = page

            # Report progress to Main Brain
            await self._report_progress(f"Fetched page: {url}")

            return page
        except Exception as e:
            await self._report_error(f"Failed to fetch {url}: {e}")
            return None

    async def crawl(self, start_url: str, *, max_pages: int | None = None) -> list[WebPage]:
        """Crawl starting from a URL, following links up to max_depth.

        Args:
            start_url: The starting URL.
            max_pages: Maximum pages to fetch (defaults to config).

        Returns:
            List of fetched WebPage objects.
        """
        max_pages = max_pages or self.config.max_pages_per_session
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url, 0)]
        results: list[WebPage] = []

        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            page = await self.fetch_page(url, depth=depth)
            if page:
                results.append(page)
                # Add links to queue
                for link in page.links:
                    absolute = urljoin(url, link)
                    if absolute not in visited:
                        queue.append((absolute, depth + 1))

        return results

    async def discover_api(self, base_url: str) -> list[APIEndpoint]:
        """Discover API endpoints from a base URL.

        Args:
            base_url: The base URL to discover APIs from.

        Returns:
            List of discovered APIEndpoint objects.
        """
        task = f"Discover API endpoints at {base_url}. Look for: "
        "1) REST API endpoints, 2) GraphQL endpoints, 3) WebSocket endpoints. "
        "Return the result as JSON with keys: endpoints (list of {url, method, parameters})."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if not data:
                return []

            endpoints = []
            for ep_data in data.get("endpoints", []):
                endpoint = APIEndpoint(
                    url=ep_data.get("url", ""),
                    method=ep_data.get("method", "GET"),
                    parameters=ep_data.get("parameters", {}),
                )
                self._endpoints[endpoint.url] = endpoint
                endpoints.append(endpoint)

            await self._report_progress(f"Discovered {len(endpoints)} API endpoints at {base_url}")
            return endpoints
        except Exception as e:
            await self._report_error(f"API discovery failed for {base_url}: {e}")
            return []

    async def research(self, query: str, *, max_sources: int = 5) -> dict[str, Any]:
        """Research a topic using web search and page fetching.

        Args:
            query: The research query.
            max_sources: Maximum number of sources to consult.

        Returns:
            Dict with research results including sources and findings.
        """
        task = f"Research the following topic: {query}. "
        f"Find at least {max_sources} relevant sources and summarize the key findings. "
        "Return the result as JSON with keys: findings (list), sources (list of {url, title, snippet})."

        try:
            result = await self.run(task)
            data = self._parse_json_result(result)
            if not data:
                return {"findings": [], "sources": [], "query": query}

            # Store research in memory
            await self.memory_store(
                content=f"Research on '{query}': {json.dumps(data.get('findings', []))}",
                memory_type="semantic",
                importance=0.6,
                scope="AGENT",
                metadata={"query": query, "sources": len(data.get("sources", []))},
            )

            await self._report_progress(f"Research complete: {query} ({len(data.get('sources', []))} sources)")
            return data
        except Exception as e:
            await self._report_error(f"Research failed for '{query}': {e}")
            return {"findings": [], "sources": [], "query": query, "error": str(e)}

    async def submit_task(self, task: str, context: str = "") -> str:
        """Submit a task to the Web Agent and return the result.

        Args:
            task: The task description.
            context: Additional context.

        Returns:
            The task result as a string.
        """
        task_id = new_task_id()

        # Send task request to Main Brain
        await self._bus.publish(AgentMessage(
            task_id=task_id,
            agent_id=self.config.name,
            message_type=MessageType.TASK_REQUEST,
            objective=task,
            input=context,
        ))

        # Execute the task
        result = await self.run(task, context)

        # Send result to Main Brain
        await self._bus.publish(AgentMessage(
            task_id=task_id,
            agent_id=self.config.name,
            message_type=MessageType.TASK_RESULT,
            objective=task,
            input=context,
            result=result,
            status="completed",
        ))

        return result

    def _parse_json_result(self, text: str) -> dict[str, Any] | None:
        """Parse a JSON result from the brain's output."""
        if not text:
            return None
        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        # Try to find JSON object in text
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
        """Get Web Agent statistics."""
        return {
            "agent": self.config.name,
            "pages_fetched": len(self._pages),
            "endpoints_discovered": len(self._endpoints),
            "session_duration": time.time() - self._session_start,
            "max_depth": self.config.max_depth,
            "max_pages": self.config.max_pages_per_session,
        }


__all__ = ["WebAgent", "WebAgentConfig", "WebPage", "APIEndpoint"]
