"""Specialist Agent Modules — dedicated domain-specific agents.

Each specialist agent extends BaseAgent with domain-specific capabilities:
- Web Agent: browsing, scraping, API interaction, web research
- Security Agent: recon, vulnerability assessment, pentest coordination
- GitHub Agent: repo management, PR workflow, issue tracking

These are ADDITIVE: they do not replace the 40 spec agents in
``app/agents/spec_agents.py``. Instead they provide full implementations
for the most critical specialist roles.
"""

from app.agents.specialist.web_agent import WebAgent, WebAgentConfig
from app.agents.specialist.security_agent import SecurityAgent, SecurityAgentConfig
from app.agents.specialist.github_agent import GitHubAgent, GitHubAgentConfig

__all__ = [
    "WebAgent",
    "WebAgentConfig",
    "SecurityAgent",
    "SecurityAgentConfig",
    "GitHubAgent",
    "GitHubAgentConfig",
]
