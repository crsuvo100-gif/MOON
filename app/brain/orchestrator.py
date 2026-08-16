"""orchestrator.py -- the agent's "brain" coordinator.

Wires together every cognitive module, the model service, the memory manager,
the tool manager, and the per-agent brains. ``run_task`` executes the full
cognition loop; ``quick_reply`` is the fast single-call path (chat/WS/voice).
Autonomous self-learning consolidates every interaction into the durable brain.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.brain.agent_brain import AgentBrain
from app.brain.agent_model_manager import AgentModelManager
from app.brain.context_builder import ContextBuilder
from app.brain.error_recovery import ErrorRecovery
from app.brain.intent_detector import detect_intent
from app.brain.lock import SessionLock
from app.brain.memory_manager import MemoryManager
from app.brain.output_formatter import OutputFormatter
from app.brain.planner import Planner
from app.brain.prompt_manager import PromptManager
from app.brain.reasoning import ReasoningEngine
from app.brain.self_reflection import SelfReflection
from app.brain.tool_manager import ToolManager
from app.brain.validator import Validator
from app.config.logging import get_logger
from app.context.retriever import ContextRetriever
from app.memory.conversation_history import ConversationHistory
from app.memory.semantic_search import SemanticSearch
from app.models.agent import AgentCard
from app.models.message import Message
from app.models.task import Task
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import ChatMessage, CompletionResult, LLMService
from app.tools.api_requests import ApiRequestsTool
from app.tools.browser import BrowserTool
from app.tools.cv_and_memory_tools import (
    AutonomousChainTool,
    HabitLearnTool,
    MultimodalSearchTool,
    MultimodalStoreTool,
    ObjectTrackTool,
)
from app.tools.database import DatabaseTool
from app.tools.docker_tool import DockerTool
from app.tools.exploit_intel_tool import ExploitIntelTool
from app.tools.file_manager import FileManagerTool
from app.tools.git_tool import GitTool
from app.tools.github_sync_tool import GitHubSyncTool
from app.tools.hardening_audit_tool import HardeningAuditTool
from app.tools.image_processing import ImageProcessingTool
from app.tools.learning_tool import LearningTool
from app.tools.log_analyzer_tool import LogAnalyzerTool
from app.tools.malware_analysis_tool import MalwareAnalysisTool
from app.tools.model_management_tool import ModelManagementTool
from app.tools.model_pull_tool import ModelPullTool
from app.tools.ocr import OcrTool
from app.tools.pdf_reader import PdfReaderTool
from app.tools.powershell_tool import PowerShellTool
from app.tools.python_executor import PythonExecutorTool
from app.tools.recon_tool import ReconTool
from app.tools.registry import ToolRegistry
from app.tools.self_evolve_tool import SelfEvolveTool
from app.tools.system_command_tool import SystemCommandTool
from app.tools.system_info_tool import SystemInfoTool
from app.tools.telegram_tool import GoogleWorkspaceTool, TelegramTool
from app.tools.terminal import TerminalTool
from app.tools.utility_tools import IpGeolocationTool, TimezoneConverterTool, UnitConverterTool
from app.tools.vuln_scanner_tool import VulnScannerTool
from app.tools.web_search import WebSearchTool
from app.capability.tool import CapabilityManagerTool
from app.connector.tool import GlobalConnectorTool
from app.tools.huggingface_deploy import HuggingFaceDeployTool
from app.tools.huggingface_tool import HuggingFaceTool

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.config.settings import Settings

_MAX_TOOL_ITERATIONS = 5


class Orchestrator:
    """Coordinates cognition, memory, tools, and agents to run tasks."""

    _persona_cache: str | None = None

    def __init__(self, settings: Settings, lock_state_file: str | Path | None = None) -> None:
        self._settings = settings
        self._llm: LLMService | None = None
        self._embeddings: EmbeddingService | None = None
        self._prompts: PromptManager | None = None
        self._context: ContextBuilder | None = None
        self._tools: ToolManager | None = None
        self._memory: MemoryManager | None = None
        self._reasoning: ReasoningEngine | None = None
        self._planner: Planner | None = None
        self._validator: Validator | None = None
        self._reflection: SelfReflection | None = None
        self._formatter: OutputFormatter | None = None
        self._recovery: ErrorRecovery | None = None
        self._history = ConversationHistory(session_id="main")
        self._agents: dict[str, AgentCard] = {}
        self._agent_brains: dict[str, Any] = {}
        self._agent_model_overrides: dict[str, str | None] = {}
        self._consolidator = None
        self._lock = SessionLock(locked=True, state_file=lock_state_file)

    async def setup(self) -> None:
        from app.config.model_config import build_embedding_config, build_model_config
        from app.memory.knowledge_base import KnowledgeBase
        from app.memory.long_term import LongTermMemory
        from app.memory.short_term import ShortTermMemory
        from app.memory.vector_db import InMemoryVectorStore

        cfg = build_model_config(self._settings)
        ecfg = build_embedding_config(self._settings)
        self._llm = LLMService(
            base_url=cfg.base_url, model_name=cfg.model_name,
            api_key=cfg.api_key, temperature=cfg.temperature,
            max_tokens=cfg.max_tokens, timeout=cfg.timeout,
        )
        await self._llm.setup()

        # Per-agent models: every agent can run on its OWN model (pulled/installed
        # on demand via Ollama) for better, domain-suited results. The agent's
        # output still flows through its AgentBrain + the main-brain accuracy gate.
        self._agent_models: AgentModelManager | None = None
        if self._settings.enable_per_agent_models:
            self._agent_models = AgentModelManager(
                base_url=cfg.base_url, api_key=cfg.api_key,
                default_model=cfg.model_name, temperature=cfg.temperature,
                max_tokens=cfg.max_tokens, timeout=cfg.timeout,
            )
            # Startup routine: pre-pull every preferred model so agents are
            # ready instantly. Best-effort; logs results, never raises.
            try:
                results = await self._agent_models.prefetch_all()
                pulled = [m for m, ok in results.items() if ok]
                logger.info("Per-agent model pre-pull: %d ready (%s)", len(pulled), ", ".join(pulled))
            except Exception as exc:  # noqa: BLE001
                logger.info("Per-agent model pre-pull skipped: %s", exc)

        # Optional STRONG model for accuracy-critical work + the main-brain
        # accuracy gate. Routes factual / cyber-critical tasks to a better model.
        self._llm_strong: LLMService | None = None
        strong_name = self._settings.strong_model_name.strip()
        if strong_name:
            strong_url = self._settings.strong_model_base_url.strip() or cfg.base_url
            self._llm_strong = LLMService(
                base_url=strong_url, model_name=strong_name,
                api_key=cfg.api_key, temperature=cfg.temperature,
                max_tokens=cfg.max_tokens, timeout=cfg.timeout,
            )
            await self._llm_strong.setup()
            logger.info("Strong model enabled: %s @ %s", strong_name, strong_url)

        # --- OpenAI-compatible FALLBACK backend ----------------------------
        # If the local endpoint (Ollama) is down or a completion fails, MOON
        # transparently retries against a hosted OpenAI-compatible API. The key
        # comes from OPENAI_API_KEY (gitignored .env) and is never logged.
        self._llm_fallback: LLMService | None = None
        self._llm_fallback2: LLMService | None = None
        self._llm_fallback3: LLMService | None = None
        if self._settings.openai_api_key.strip():
            self._llm_fallback = LLMService(
                base_url=self._settings.openai_base_url.strip() or "https://api.openai.com/v1",
                model_name=self._settings.openai_model.strip() or "gpt-4o-mini",
                api_key=self._settings.openai_api_key.strip(),
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout,
                disable_thinking=True,  # hosted models are not thinking models
            )
            await self._llm_fallback.setup()
            logger.info("Fallback backend enabled: %s @ %s", self._settings.openai_model, self._settings.openai_base_url)

        # --- OpenRouter FALLBACK backend (secondary) -------------------------
        # Tried after the local endpoint and the primary OpenAI fallback. OpenRouter
        # is OpenAI-compatible, so it reuses the LLMService client shape. Key comes
        # from OPENROUTER_API_KEY (gitignored .env, never logged).
        self._llm_fallback2: LLMService | None = None
        if self._settings.openrouter_api_key.strip():
            self._llm_fallback2 = LLMService(
                base_url=self._settings.openrouter_base_url.strip() or "https://openrouter.ai/api/v1",
                model_name=self._settings.openrouter_model.strip() or "openai/gpt-4o-mini",
                api_key=self._settings.openrouter_api_key.strip(),
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout,
                disable_thinking=True,
            )
            await self._llm_fallback2.setup()
            logger.info("Secondary fallback (OpenRouter) enabled: %s @ %s", self._settings.openrouter_model, self._settings.openrouter_base_url)

        # --- Hugging Face FALLBACK backend (tertiary) -----------------------
        # Tried after local, OpenAI, and OpenRouter. Hugging Face's router speaks
        # the OpenAI-compatible /v1/chat/completions shape. Key from
        # HUGGINGFACE_API_KEY (gitignored .env, never logged).
        self._llm_fallback3: LLMService | None = None
        if self._settings.huggingface_api_key.strip():
            self._llm_fallback3 = LLMService(
                base_url=self._settings.huggingface_base_url.strip() or "https://router.huggingface.co",
                model_name=self._settings.huggingface_model.strip() or "meta-llama/Llama-3.1-8B-Instruct",
                api_key=self._settings.huggingface_api_key.strip(),
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout,
                disable_thinking=True,
            )
            await self._llm_fallback3.setup()
            logger.info("Tertiary fallback (Hugging Face) enabled: %s @ %s", self._settings.huggingface_model, self._settings.huggingface_base_url)

        self._embeddings = EmbeddingService(
            dim=ecfg.dim, enabled=ecfg.enabled,
            base_url=ecfg.base_url, model_name=ecfg.model_name,
        )
        stm = ShortTermMemory()
        ltm = LongTermMemory(path=f"{self._settings.log_dir}/long_term.jsonl")
        store = InMemoryVectorStore(dim=ecfg.dim)
        kb = KnowledgeBase(store, self._embeddings)
        self._memory = MemoryManager(short_term=stm, long_term=ltm, knowledge_base=kb)
        await self._memory.setup()

        # Index the bundled Hermes skill corpus into the knowledge base so the
        # skills are retrievable via semantic recall (MOON can use them).
        try:
            from app.knowledge.skills_library import index_skills

            await index_skills(self._memory._kb)
        except Exception as exc:  # noqa: BLE001
            logger.info("skills index skipped: %s", exc)

        if self._settings.enable_auto_learning:
            try:
                from app.brain.knowledge_consolidator import KnowledgeConsolidator

                self._consolidator = KnowledgeConsolidator(self._memory, self._llm, use_llm=False)
                try:
                    existing = await ltm.all()
                    for e in existing:
                        await kb.index_document(f"ltm_{e.id}", e.content)
                    if existing:
                        logger.info("Seeded KB with %d prior long-term memories", len(existing))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("KB seeding from LTM skipped: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("KnowledgeConsolidator init skipped: %s", exc)

        self._prompts = PromptManager()
        self._context = ContextBuilder(self._prompts)
        _ss = SemanticSearch(knowledge_base=kb, history=self._history)
        self._reasoning = ReasoningEngine(self._llm, self._prompts)
        self._planner = Planner(self._llm, self._prompts)
        self._validator = Validator(self._llm, self._prompts)
        self._reflection = SelfReflection(self._llm, self._prompts)
        self._formatter = OutputFormatter()
        self._recovery = ErrorRecovery(max_retries=3)

        registry = ToolRegistry()
        enabled = self._settings.enable_browser_automation
        for tool in (
            WebSearchTool(), BrowserTool(enabled=enabled), TerminalTool(),
            FileManagerTool(allowed_root="."), PythonExecutorTool(), DatabaseTool(),
            ApiRequestsTool(), OcrTool(enabled=self._settings.enable_ocr),
            PdfReaderTool(enabled=self._settings.enable_pdf),
            ImageProcessingTool(enabled=self._settings.enable_pdf),
            SystemCommandTool(),
            ModelManagementTool(orchestrator=self),
            LearningTool(web_search=self._tools._registry._tools.get('web_search') if self._tools else None),
            UnitConverterTool(), TimezoneConverterTool(), IpGeolocationTool(),
            ObjectTrackTool(), AutonomousChainTool(), MultimodalStoreTool(),
            MultimodalSearchTool(), HabitLearnTool(),
            TelegramTool(), GoogleWorkspaceTool(),
            ReconTool(), VulnScannerTool(), HardeningAuditTool(), LogAnalyzerTool(),
            MalwareAnalysisTool(), ExploitIntelTool(),
            SystemInfoTool(), PowerShellTool(), DockerTool(), GitTool(), SelfEvolveTool(), ModelPullTool(), GitHubSyncTool(),
            CapabilityManagerTool(),
            GlobalConnectorTool(),
            HuggingFaceDeployTool(),
            HuggingFaceTool(),
        ):
            registry.register(tool)

        try:
            from plugins.loader import load_plugins

            plugin_summary = load_plugins(registry)
            if any(plugin_summary.values()):
                logger.info("Loaded plugins: %s", plugin_summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plugin loading skipped: %s", exc)

        allow_dangerous = True
        enabled_names = {t.name for t in registry.all()}
        self._tools = ToolManager(registry, enabled_tools=enabled_names, allow_dangerous=allow_dangerous)
        self._tools._tool_timeout = self._settings.tool_timeout

        try:
            _galaxy = None
            try:
                from app.knowledge.galaxy import GalaxyService

                gs = GalaxyService()
                _galaxy = await gs.build(registry=getattr(self._tools, "_registry", None))
            except Exception as exc:  # noqa: BLE001
                logger.info("Galaxy retriever source skipped: %s", exc)
            self._context.set_retriever(ContextRetriever(history=self._history, semantic_search=_ss, galaxy=_galaxy))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ContextRetriever wiring skipped: %s", exc)

        self._register_agents(registry)

        # Each agent gets its OWN connected brain (durable per-agent memory)
        # wired to the main brain for two-phase validation.
        for name in self._agents:
            try:
                brain = AgentBrain(name, main_brain=self, agent_models=self._agent_models)
                await brain.setup()
                self._agent_brains[name] = brain
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent brain '%s' init skipped: %s", name, exc)
        logger.info("Connected %d agent brains", len(self._agent_brains))
        logger.info("Orchestrator setup complete (model=%s)", cfg.model_name)

    def _register_agents(self, registry: ToolRegistry) -> None:
        from app.brain.agent_registry import build_agents

        tool_names = [t.name for t in registry.all()]
        self._agents = build_agents(tool_names)
        self._agent_order = list(self._agents.keys())

    async def teardown(self) -> None:
        for attr in ("_llm", "_llm_strong"):
            svc = getattr(self, attr, None)
            if svc is not None and hasattr(svc, "teardown"):
                try:
                    await svc.teardown()
                except Exception:  # noqa: BLE001
                    pass
        if getattr(self, "_agent_models", None) is not None:
            await self._agent_models.teardown()
        logger.info("Orchestrator torn down")

    # ------------------------------------------------------------------
    # Advanced workflow helpers (speed + accuracy)
    # ------------------------------------------------------------------
    def _is_factual(self, text: str) -> bool:
        """Heuristic: a question likely to have a single factual answer."""
        t = text.strip().lower()
        return t.endswith("?") or any(
            k in t for k in ("what is", "who is", "when did", "where is", "how many", "capital of")
        )

    @staticmethod
    def _majority_answer(samples: list[str]) -> str:
        """Return the most representative (majority) answer among samples."""
        import re as _re
        clean = [x for x in (s.strip() for s in samples) if x]
        if not clean:
            return ""
        # Normalize for grouping: keep full text but pick the most frequent exact,
        # else the one with highest token-overlap to the others (consensus).
        from collections import Counter
        exact = Counter(clean)
        if exact.most_common(1)[0][1] > 1:
            return exact.most_common(1)[0][0]
        def toks(t: str) -> set[str]:
            t = _re.sub(r"[^a-z0-9 ]", " ", t.lower())
            return set(t.split()) - {"the","a","an","is","are","was","of","in","on","to","and","that","it","its"}
        best, best_score = clean[0], -1
        for c in clean:
            tc = toks(c)
            score = sum(len(tc & toks(o)) for o in clean)
            if score > best_score:
                best, best_score = c, score
        return best

    @staticmethod
    def _answers_disagree(a: str, b: str) -> bool:
        """Cheap disagreement check: normalize and compare key tokens."""
        import re as _re

        def norm(s: str) -> set[str]:
            s = (s or "").lower()
            s = _re.sub(r"[^a-z0-9 ]", " ", s)
            toks = set(s.split())
            stop = {"the", "a", "an", "is", "are", "was", "of", "in", "on", "to", "and", "that", "it", "its"}
            return toks - stop

        na, nb = norm(a), norm(b)
        if not na or not nb:
            return False
        overlap = na & nb
        return len(overlap) < 0.4 * min(len(na), len(nb))

    @staticmethod
    def _github_tool_path(prompt: str, repo: str) -> str | None:
        """Guess the repo path of a tool/plugin the prompt asks for."""
        import re as _re
        m = _re.search(r"(plugins/[A-Za-z0-9_./-]+\.py|app/tools/[A-Za-z0-9_./-]+\.py|skills/[A-Za-z0-9_./-]+/SKILL\.md)", prompt)
        return m.group(1) if m else None

    async def set_main_model(self, model_name: str) -> None:
        """Switch MOON's main brain active model at runtime."""
        if not model_name:
            return
        try:
            self._settings.model_name = model_name
            self._llm.model_name = model_name  # type: ignore[attr-defined]
            logger.info("main model switched -> %s", model_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("set_main_model failed: %s", e)

    async def set_agent_model(self, role: str, model_name: str | None) -> None:
        """Set the model used by a specific agent role (or clear override)."""
        self._agent_model_overrides[role] = model_name
        logger.info("agent model override: %s -> %s", role, model_name)

    async def refresh_repo_catalog(self) -> None:
        """Continuously-connected behavior: pull the connected repo and surface
        any new tools/plugins/skills it contains into the live tool registry.
        Best-effort; never blocks the main loop."""
        repo = getattr(self._settings, "github_repo", "")
        if not repo:
            return
        try:
            from app.tools.github_feed import list_repo_tools
            tools = list_repo_tools(repo)
            if tools:
                logger.info("connected repo catalog: %d tools/plugins/skills available", len(tools))
        except Exception as exc:  # noqa: BLE001
            logger.debug("repo catalog refresh skipped: %s", exc)

    async def _auto_acquire_for_task(self, task: Task, agent) -> None:
        """Detect a missing capability and auto-acquire a tool.

        ADDITIVE integration with the new Capability Manager: we prefer the
        CapabilityManager (persistent registry + acquisition-priority + safety
        policy) when it can satisfy a discovered need, then fall back to the
        existing catalog / LLM-plugin / GitHub-feed paths so no prior behavior
        is lost.
        """
        from app.tools.tool_acquisition import acquire_by_catalog, generate_plugin

        prompt = (task.prompt or "").lower()
        # --- New Capability Manager (preferred, persistent, policy-gated) ---
        try:
            from app.capability.manager import CapabilityManager
            mgr = CapabilityManager()
            for need in mgr.discover(task.prompt or ""):
                if mgr.status(need) in ("missing", "unknown", "failed"):
                    res = await mgr.acquire(need)
                    logger.info("capability_manager %s -> %s (%s)", need, res.status, res.source)
                    if res.status == "acquired":
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.info("capability_manager auto-acquire skipped: %s", exc)

        cap = ""
        for cap in ("youtube", "video", "audio download", "web scraping", "html parse",
                    "browser automation", "image", "ocr", "pdf", "data", "csv",
                    "plot", "chart", "speech", "translate api", "excel", "yaml", "qr"):
            if cap in prompt:
                name = acquire_by_catalog(cap, self._tools._registry)
                if name:
                    logger.info("auto-acquired catalog tool '%s'", name)
                break
        # Always-connected GitHub tool-feed: if a needed capability is not local,
        # pull it from YOUR repo; if not there, search the public GitHub
        # ecosystem, pull the best match, and install it as a plugin. Then
        # continue the task with the new tool. All best-effort / non-destructive.
        repo = getattr(self._settings, "github_repo", "")
        if repo and not self._tools._registry.tool_names.__contains__("tool_" + cap.replace(" ", "_")):
            try:
                from app.tools.github_feed import feed_for_capability
                installed = await feed_for_capability(cap, self._tools._registry, repo_url=repo)
                if installed:
                    logger.info("github tool-feed installed '%s' for capability '%s'", installed, cap)
            except Exception as exc:  # noqa: BLE001
                logger.info("github tool-feed skipped: %s", exc)
        try:
            if self._llm is not None:
                sys_p = (
                    "You are MOON's tool planner. If the task needs a tool MOON lacks, "
                    "reply ONLY with JSON: {\"need\": \"<capability>\", \"name\": \"<tool_name>\", "
                    "\"purpose\": \"<one line>\", \"code\": \"<Python BaseTool subclass source>\"}. "
                    "If no new tool is needed, reply {\"need\": null}. Output JSON only."
                )
                decision = await self._llm.complete(
                    [
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": f"Task: {task.prompt}"},
                    ],
                    max_tokens=600, temperature=0.2,
                )
                import json
                import re as _re
                m = _re.search(r"\{.*\}", decision.content or "", _re.DOTALL)
                if m:
                    obj = json.loads(m.group(0))
                    if obj.get("need"):
                        cap = obj["need"]
                        if not acquire_by_catalog(cap, self._tools._registry):
                            generate_plugin(obj.get("name", "custom"), obj.get("purpose", ""), obj.get("code", ""), self._tools._registry)
        except Exception as exc:  # noqa: BLE001
            logger.info("LLM tool-plan skipped: %s", exc)

    @staticmethod
    def _final_report(task: Task, actions: list[str], evidence: str, results: str) -> str:
        """Format a task result per MOON's system-prompt report standard."""
        remaining = "None" if results else "Incomplete -- needs human input"
        return (
            f"OBJECTIVE:\n{task.prompt}\n\n"
            f"ACTIONS PERFORMED:\n" + ("\n".join(f"- {a}" for a in actions) if actions else "- (none recorded)") + "\n\n"
            f"EVIDENCE:\n{evidence or '(see tool outputs)'}\n\n"
            f"RESULTS:\n{results or '(pending)'}\n\n"
            f"REMAINING ISSUES:\n{remaining}\n\n"
            f"RECOMMENDED NEXT STEPS:\n- Verify outputs; continue or escalate as needed."
        )

    def _is_simple_query(self, text: str) -> bool:
        """Heuristic: a short factual/chat question that needs no tools."""
        t = text.strip()
        if len(t) > 240:
            return False
        if any(k in t.lower() for k in ("http://", "https://", "file:", "/home", "write", "create", "generate", "run ", "execute", "open ")):
            return False
        return True

    def _split_subtasks(self, text: str) -> list[str]:
        """Split a complex goal into parallel subtasks on ' and also ' / ';' / numbered lists."""
        parts = [p.strip() for p in text.split(" and also ") if p.strip()]
        if len(parts) <= 1:
            parts = [p.strip() for p in text.split(";") if p.strip()]
        if len(parts) <= 1:
            import re as _re
            numbered = _re.findall(r"(?m)^\s*\d+[.)]\s*(.+)$", text)
            if len(numbered) > 1:
                parts = [p.strip() for p in numbered]
        return parts[: self._settings.max_parallel_agents]

    def _pick_llm(self, task_prompt: str):
        """Use the STRONG model for factual / cyber-critical tasks when configured."""
        if self._llm_strong is None:
            return self._llm
        crit = any(k in (task_prompt or "").lower() for k in
                    ("exploit", "vuln", "cve", "scan", "red team", "offensive", "pentest",
                     "malware", "forensic", "reverse", "recon", "payload", "attack"))
        if self._is_factual(task_prompt) or crit:
            return self._llm_strong
        return self._llm

    async def _fast_answer(self, task: Task, agent) -> tuple[str, int]:
        """Single-call answer for simple queries (no tool loop, no two-phase refine)."""
        persona = self._agent_persona(task.agent_name)
        sys_p = f"{persona}\n\nAnswer concisely and accurately."
        # build() returns a list[Message]; _complete_with_fallback accepts a
        # list[Message]/list[ChatMessage] or a plain string. (Passing ctx.prompt
        # was a bug -- the list has no .prompt attribute and crashed the path.)
        ctx = await self._context.build(task=task, history=self._history, system_override=sys_p)
        resp = await self._complete_with_fallback(
            ctx, max_tokens=self._settings.model_max_tokens,
            temperature=self._settings.model_temperature,
        )
        text, tokens = (resp.content or "").strip(), 0
        return text.strip(), tokens

    def _agent_persona(self, name: str) -> str:
        from app.brain.agent_registry import persona_for
        return persona_for(name)

    async def _run_parallel(self, subtasks: list[str], agent_name: str) -> str:
        """Fan out subtasks to concurrent agent runs and merge their results."""
        async def _one(sub: str) -> str:
            sub_task = Task.create(sub, agent_name=agent_name)
            sub_task.mark_running()
            self._history.clear()
            txt, _ = await self._run_cognition_loop(sub_task, self._agents.get(agent_name, self._agents["planning"]))
            return f"- {sub}\n  {txt}"
        results = await asyncio.gather(*[_one(s) for s in subtasks])
        return "Complex goal decomposed and executed in parallel:\n\n" + "\n\n".join(results)

    def _route_intent(self, task: Task) -> None:
        """Intent detection: when no explicit agent is set, pick one from the
        classified intent. Maps intent -> agent name; unknown -> coordinator."""
        if task.agent_name and task.agent_name != "auto":
            return
        intent, conf = detect_intent(task.prompt)
        mapping = {
            "code": "coding", "research": "research", "web": "browser",
            "writing": "writing", "vision": "vision", "planning": "planning",
            "math": "math", "science": "science", "security": "security",
            "cyber": "cyber", "red_team": "red_team", "blue_team": "blue_team",
            "forensics": "forensics", "reverse_eng": "reverse_eng",
            "threat_hunt": "threat_hunt", "siem": "siem",
            "data_science": "data_science", "translation": "translation",
            "audio": "audio", "qa": "qa", "infra": "infra", "finance": "finance",
            "legal": "legal", "medical": "medical", "design": "design",
            "summarizer": "summarizer", "fact_check": "fact_checker",
            "strategy": "strategist", "tools": "toolsmith",
            "github_sync": "github_sync", "voice": "audio", "system": "infra",
            "chat": "manager",
        }
        agent = mapping.get(intent, "coordinator")
        if agent not in self._agents:
            agent = "coordinator"
        task.agent_name = agent
        logger.info("intent='%s' (conf=%.2f) -> agent='%s'", intent, conf, agent)

    async def run_task(self, task: Task, on_event=None) -> Task:
        if self._llm is None or self._tools is None or self._context is None:
            raise RuntimeError("Orchestrator.setup() must be called first")

        gate = self._lock.observe(task.prompt)
        if gate is not None:
            task.mark_running()
            task.complete(gate, data={"locked": self._lock.locked})
            return task

        task.mark_running()
        self._history.clear()
        self._route_intent(task)
        if on_event:
            try:
                await on_event({"stage": "routing", "detail": f"intent -> {task.agent_name}"})
            except Exception:
                pass
        agent = self._agents.get(task.agent_name, self._agents["planning"])
        agent_brain = self._agent_brains.get(agent.name)

        try:
            await self._auto_acquire_for_task(task, agent)
        except Exception as exc:  # noqa: BLE001
            logger.info("auto-acquire skipped: %s", exc)

        # --- Advanced: parallel fan-out for coordinator on multi-part goals ---
        if agent.name == "coordinator":
            try:
                planned = await self._planner.plan(task.prompt)
                if planned:
                    task._decomposition = planned  # store for transparency
            except Exception:  # noqa: BLE001
                pass
        if agent.name == "coordinator" and len(self._split_subtasks(task.prompt)) > 1:
            try:
                merged = await self._run_parallel(self._split_subtasks(task.prompt), agent.name)
                task.complete(merged, data={"agent": agent.name, "parallel": True})
                task.mark_done()
                return task
            except Exception as exc:  # noqa: BLE001
                logger.info("parallel fan-out fell back to standard loop: %s", exc)

        # --- Advanced: fast-path for simple queries (speed) ---
        if self._settings.enable_fast_path and self._is_simple_query(task.prompt) and task.agent_name != "auto":
            try:
                text, tokens = await self._fast_answer(task, agent)
                task.complete(text, data={"agent": agent.name, "fast_path": True, "tokens": tokens})
                task.mark_done()
                return task
            except Exception as exc:  # noqa: BLE001
                logger.info("fast-path fell back to full loop: %s", exc)
        try:
            final_text, tokens = await self._run_cognition_loop(task, agent, on_event=on_event)
            validation = await self._validator.validate(task.prompt, final_text)
            if not validation.valid:
                logger.warning("Output invalid: %s", validation.issues)
                # Self-improvement: remember the failure mode as a lesson.
                try:
                    from app.brain.prompt_tuner import record_lesson

                    record_lesson(
                        f"Avoid producing invalid output for: {task.prompt[:120]}. Issues: {', '.join(validation.issues)}",
                        kind="validation",
                        agent=agent.name,
                    )
                except Exception:  # noqa: BLE001
                    pass
            reflection = await self._reflection.reflect(task.prompt, final_text)
            if on_event:
                try:
                    await on_event({"stage": "reflection", "detail": "self-reviewing answer"})
                except Exception:
                    pass
            if not reflection.satisfactory:
                logger.info("Reflection suggested improvements: %s", reflection.improvements)

            # --- Self-consistency (accuracy): majority vote over N samples ----
            if self._settings.enable_self_consistency and self._is_factual(task.prompt):
                if on_event:
                    try:
                        await on_event({"stage": "consistency", "detail": "majority-vote self-check"})
                    except Exception:
                        pass
                try:
                    samples = [final_text]
                    for _ in range(max(1, self._settings.self_consistency_samples)):
                        extra, _ = await self._run_cognition_loop(
                            Task.create(task.prompt, agent_name=agent.name), agent
                        )
                        if extra:
                            samples.append(extra.strip())
                    # Replace with the most common answer (majority wins).
                    best = self._majority_answer(samples)
                    if best and best != final_text:
                        logger.info("Self-consistency: replaced answer via majority vote")
                        final_text = best
                except Exception as exc:  # noqa: BLE001
                    logger.info("self-consistency skipped: %s", exc)
            try:
                lesson = "; ".join(reflection.improvements) if reflection.improvements else ""
                self._memory.episodic.record(
                    goal=task.prompt, outcome=final_text[:1000], lesson=lesson, success=reflection.satisfactory,
                )
                self._memory.save_episodes()
                if self._consolidator is not None:
                    await self._consolidator.consolidate(
                        prompt=task.prompt, response=final_text,
                        tool_results=getattr(self, "_last_tool_outputs", []),
                        lesson=lesson, success=reflection.satisfactory, agent=agent.name,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Learning loop store failed (skipped): %s", exc)

            # Two-phase: let the agent's OWN brain refine the draft through the
            # main brain when validation is enabled (best quality, costs one more
            # model call). Otherwise use the draft directly.
            if agent_brain is not None and self._settings.enable_agent_validation:
                try:
                    final_text = await agent_brain.refine_with_main(final_text, task.prompt)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("agent two-phase refine skipped: %s", exc)

            # Persist the episode into the agent's OWN durable brain too.
            if agent_brain is not None:
                try:
                    await agent_brain.remember({
                        "goal": task.prompt,
                        "outcome": final_text[:1000],
                        "lesson": lesson,
                        "success": reflection.satisfactory,
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.warning("agent brain remember failed: %s", exc)

            clean = self._formatter.format(final_text)
            task.complete(clean, data={"tokens_used": tokens, "issues": validation.issues, "agent": agent.name}, tokens_used=tokens)
            await self._memory.remember(clean, long_term=False)
        except Exception as exc:
            logger.exception("Task %s failed", task.id)
            task.fail(str(exc))
        return task

    async def _run_cognition_loop(self, task: Task, agent: AgentCard, on_event=None) -> tuple[str, int]:
        assert self._llm is not None and self._tools is not None and self._context is not None
        retrieved = await self._memory.semantic_recall(task.prompt) if self._memory else []
        if self._memory is not None:
            try:
                for ep in self._memory.episodic.recall(task.prompt, k=3):
                    if ep.lesson:
                        retrieved.append({"content": f"[past lesson] goal: {ep.goal} | lesson: {ep.lesson}", "score": 0.6})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Episodic recall failed (skipped): %s", exc)
        messages = await self._context.build(task=task, history=self._history, retrieved=retrieved, agent=agent)
        tool_specs = self._tools.available_specs()
        total_tokens = 0
        final_text = ""
        tool_outputs: list[str] = []
        if on_event:
            try:
                await on_event({"stage": "thinking", "detail": f"recalled {len(retrieved)} memories; building context"})
            except Exception:
                pass

        for _ in range(_MAX_TOOL_ITERATIONS):
            # Prefer the agent's OWN model (per-agent models) for its function;
            # fall back to the shared/strong routing otherwise.
            if self._agent_models is not None:
                try:
                    llm = await self._agent_models.get_llm(agent.name)
                except Exception as exc:  # noqa: BLE001
                    logger.info("agent model unavailable, using shared llm: %s", exc)
                    llm = self._pick_llm(task.prompt)
            else:
                llm = self._pick_llm(task.prompt)
            resp = await llm.complete(messages, tools=tool_specs if tool_specs else None)
            total_tokens += 1
            if resp.has_tool_calls:
                for call in resp.tool_calls:
                    args = self._parse_args(call.get("arguments", "{}"))
                    if on_event:
                        try:
                            await on_event({"stage": "tool_call", "detail": call.get("name", "tool")})
                        except Exception:  # noqa: BLE001
                            pass
                    result = await self._tools.run(call["name"], args, agent=agent)
                    messages.append(ChatMessage(role="tool", content=json.dumps(result.to_dict(), default=str)))
                    self._history.append(Message.tool_result(str(result.output), tool=call["name"]))
                    out = str(result.output)
                    if 12 < len(out) < 600:
                        tool_outputs.append(out)
                continue
            final_text = resp.content or ""
            # A per-agent model can occasionally return an EMPTY body (cold-load /
            # transient / Ollama hiccup). Rescue it instead of failing the whole
            # task: retry on the shared main LLM and, failing that, the full
            # multi-tier fallback chain (local -> OpenAI -> OpenRouter -> HF) so
            # MOON always returns a real answer once ANY backend is reachable.
            if not final_text.strip():
                try:
                    r2 = await self._complete_with_fallback(
                        messages, max_tokens=self._settings.model_max_tokens,
                        temperature=self._settings.model_temperature,
                    )
                    final_text = (r2.content or "") if r2 is not None else ""
                except Exception as exc:  # noqa: BLE001
                    logger.info("empty-answer rescue skipped: %s", exc)
            self._history.append(Message.assistant(final_text or ""))
            break
        else:
            final_text = "(model did not produce a final answer within iteration budget)"
        self._last_tool_outputs = tool_outputs
        return final_text, total_tokens

    async def _complete_with_fallback(
        self, messages, *, tools=None, max_tokens=None, temperature=None
    ) -> "CompletionResult":
        """Run a completion on the primary (local) model, falling back through the
        configured hosted backends if the local call fails or returns no content.

        Order: local -> OpenAI (OPENAI_API_KEY) -> OpenRouter (OPENROUTER_API_KEY)
        -> Hugging Face (HUGGINGFACE_API_KEY). Each fallback is tried only while the
        previous returned nothing. Never raises; returns a CompletionResult
        (possibly empty).

        `messages` may be a list[ChatMessage] or a plain string (treated as a
        single user message)."""
        if isinstance(messages, str):
            messages = [ChatMessage(role="user", content=messages)]

        async def _try(llm):
            if llm is None:
                return None
            try:
                r = await llm.complete(
                    messages, tools=tools, max_tokens=max_tokens, temperature=temperature
                )
                return r
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM complete failed: %s", exc)
                return None

        primary = await _try(self._llm)
        if primary is not None and (primary.content or "").strip():
            return primary
        # Ordered fallback chain: OpenAI, then OpenRouter, then Hugging Face (all optional).
        for llm, label in (
            (getattr(self, "_llm_fallback", None), self._settings.openai_model),
            (getattr(self, "_llm_fallback2", None), self._settings.openrouter_model),
            (getattr(self, "_llm_fallback3", None), self._settings.huggingface_model),
        ):
            if llm is None:
                continue
            logger.info("Primary model failed/empty -> falling back to %s", label)
            fb = await _try(llm)
            if fb is not None and (fb.content or "").strip():
                return fb
        return primary if primary is not None else CompletionResult(
            content=None, has_tool_calls=False, tool_calls=[]
        )

    async def quick_reply(self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        if self._llm is None:
            await self.setup()
        if self._llm is None:
            return "MOON is not ready to reply yet."
        persona = self._system_persona()
        messages = [ChatMessage(role="system", content=persona), ChatMessage(role="user", content=prompt)]
        try:
            resp = await self._complete_with_fallback(messages, max_tokens=max_tokens, temperature=temperature)
            text = (resp.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("quick_reply failed: %s", exc)
            text = ""
        if not text:
            text = "I heard you, but I could not form a reply."
        if (
            self._consolidator is not None
            and "love you 3000" not in prompt.lower()
            and len(prompt.strip()) > 3
            and text
            and "could not form a reply" not in text
        ):
            try:
                await self._consolidator.consolidate(prompt=prompt, response=text)
            except Exception as exc:  # noqa: BLE001
                logger.debug("quick_reply self-learn skipped: %s", exc)
        return text

    async def refine(self, prompt: str, *, temperature: float | None = None) -> str:
        """Used by AgentBrain two-phase validation. Lower temperature for audits.
        Uses the STRONG model when configured (best accuracy for the gate)."""
        llm = self._llm_strong or self._llm
        if llm is None:
            return ""
        try:
            t = temperature if temperature is not None else 0.1
            resp = await llm.complete([ChatMessage(role="user", content=prompt)], max_tokens=400, temperature=t)
            return (resp.content or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _system_persona() -> str:
        if quick_reply_persona := getattr(Orchestrator, "_persona_cache", None):
            return quick_reply_persona
        path = Path(__file__).resolve().parent.parent / "prompts" / "templates" / "moon_system.md"
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = "You are MOON, a helpful autonomous AI assistant."
        Orchestrator._persona_cache = text
        return text

    @staticmethod
    def _parse_args(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
