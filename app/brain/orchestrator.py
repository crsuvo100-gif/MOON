"""orchestrator.py -- the agent's "brain" coordinator.

Wires together every cognitive module, the model service, the memory manager,
the tool manager, and the per-agent brains. ``run_task`` executes the full
cognition loop; ``quick_reply`` is the fast single-call path (chat/WS/voice).
Autonomous self-learning consolidates every interaction into the durable brain.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.agents.advanced.performance import TaskExecution
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
from app.memory.record import MemoryType, Scope, SourceType
from app.memory.semantic_search import SemanticSearch
from app.memory.enhanced_long_term import EnhancedLongTermMemory
from app.memory.enhanced_short_term import EnhancedShortTermMemory
from app.memory.memory_graph import MemoryGraph
from app.memory.memory_stats import MemoryStatsCollector
from app.memory.memory_maintenance import MemoryMaintenance
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

# --- Spec runtime integration glue (spec 10/12/28/30/41/46) ----------------
# The 0af96c2 refactor deleted app/runtime/* and with it this import, leaving
# emit() / analyze_task() / route_agent() / choose_model() called but UNDEFINED.
# Every call site sits inside `try/except Exception: pass`, so each augmentation
# silently no-op'd instead of failing loudly (no GoalSpec, no routing refinement,
# no model recommendation, zero events on the bus). Restored here.
from app.runtime.integration import (  # noqa: E402
    analyze_task,
    choose_model,
    emit,
    gate_action,
    record_evaluation,
    record_outcome,
    route_agent,
)

# The same refactor that deleted the import above also left NINE call sites
# using the private alias `_emit(...)` (verification, memory-update and tool
# telemetry). `_emit` was never imported or defined, so every one of those
# calls raised NameError inside `except Exception: pass` -- silently killing the
# spec-42 events TOOL_SELECTED / TOOL_STARTED / TOOL_COMPLETED,
# VERIFICATION_STARTED / VERIFICATION_PASSED / VERIFICATION_FAILED and
# MEMORY_UPDATED. Alias it to the real publisher.
_emit = emit

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
        self._advanced_memory = None
        self._advanced_agents = None
        self._advanced_brain = None
        self._cognitive_loop = None
        self._agent_workflow = None
        self._skill_orchestrator = None
        self._context_orchestrator = None
        self._professional_orchestrator = None
        # Cognitive memory infrastructure (spec 28/61/62)
        self._cognitive_memory = None
        self._context_engine = None
        self._sync_engine = None
        self._memory_health = None
        # spec 17/18/19/37: provider-independent brain routing + recorded fallback
        self._brain_router = None
        # spec 31/36: live agent supervision + bounded recovery decisions
        self._supervisor = None
        self._recovery_policy = None
        # Shared lock state across CLI + web backend + WebSocket so an unlock
        # in ANY surface (HUD, `moon run`, voice, TUI) persists for ALL others.
        if lock_state_file is None:
            lock_state_file = (
                Path(__file__).resolve().parent.parent.parent
                / "app" / "data" / "lock_state.json"
            )
        self._lock = SessionLock(locked=False, state_file=lock_state_file)
        self._exec_mgr = None  # lazy ExecutionManager (spec 31); created on first task

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
        stm = EnhancedShortTermMemory(max_items=50, auto_promote_threshold=0.7)
        ltm = EnhancedLongTermMemory(path=f"{self._settings.log_dir}/long_term.jsonl")
        store = InMemoryVectorStore()
        kb = KnowledgeBase(store, self._embeddings)
        self._memory = MemoryManager(short_term=stm, long_term=ltm, knowledge_base=kb)
        await self._memory.setup()

        # Enhanced memory subsystems
        self._memory_graph = MemoryGraph(
            persist_path=f"{self._settings.log_dir}/memory_graph.json",
            max_nodes=5000,
        )
        await self._memory_graph.setup()

        self._memory_stats = MemoryStatsCollector()
        self._memory_maintenance = MemoryMaintenance(
            ltm=ltm,
            stm=stm,
            graph=self._memory_graph,
            episodic=self._memory._episodic if hasattr(self._memory, '_episodic') else None,
            kb=kb,
            stats_collector=self._memory_stats,
        )
        await self._memory_maintenance.start()

        # --- Advanced memory system (unified search, consolidation, proactive) --
        try:
            from app.memory.advanced.orchestrator import AdvancedMemoryOrchestrator
            self._advanced_memory = AdvancedMemoryOrchestrator(
                memory_manager=self._memory,
                llm_service=self._llm,
            )
            await self._advanced_memory.setup()
            # Wire advanced orchestrator into MemoryManager
            self._memory._advanced = self._advanced_memory
            logger.info("Advanced memory system initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Advanced memory system init skipped: %s", exc)
            self._advanced_memory = None

        # --- Cognitive memory infrastructure (spec 28/61/62) ---
        try:
            from app.memory.cognitive import CognitiveMemoryManager
            from app.memory.context_engine import ContextEngine
            from app.memory.sync import SyncEngine, NullCloudProvider
            from app.memory.health import MemoryHealthService
            self._cognitive_memory = CognitiveMemoryManager(
                embed_fn=self._embeddings.embed if self._embeddings else None,
                vector_store=store,
            )
            self._context_engine = ContextEngine()
            self._sync_engine = SyncEngine(
                store=self._cognitive_memory._store,
                provider=NullCloudProvider(),
                device_id=self._cognitive_memory.device_id,
            )
            self._memory_health = MemoryHealthService(
                manager=self._cognitive_memory,
                context_engine=self._context_engine,
                sync=self._sync_engine,
            )
            logger.info("Cognitive memory initialized (device=%s)", self._cognitive_memory.device_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("Cognitive memory init skipped: %s", exc)
            self._cognitive_memory = None
            self._context_engine = None
            self._sync_engine = None
            self._memory_health = None

        # --- Advanced agent system (pipeline, coordination, learning) --
        try:
            from app.agents.advanced.orchestrator import AdvancedAgentOrchestrator
            self._advanced_agents = AdvancedAgentOrchestrator()
            await self._advanced_agents.initialize(agent_id="orchestrator")
            logger.info("Advanced agent system initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Advanced agent system init skipped: %s", exc)
            self._advanced_agents = None

        # --- Advanced brain system (ReAct, DAG, metacognition, reflection) ---
        try:
            from app.brain.advanced.brain_orchestrator import BrainOrchestrator
            self._advanced_brain = BrainOrchestrator(
                llm=self._llm,
                max_iterations=5,
                max_tool_calls=10,
            )
            logger.info("Advanced brain system initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Advanced brain system init skipped: %s", exc)
            self._advanced_brain = None

        # --- Professional cognitive loop (ReAct + working memory + compression) --
        try:
            from app.brain.advanced.cognitive_loop import CognitiveLoop
            self._cognitive_loop = CognitiveLoop(
                llm=self._llm,
                tool_executor=self._make_tool_executor(),
                max_iterations=5,
                max_tool_calls=10,
            )
            logger.info("Professional cognitive loop initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Cognitive loop init skipped: %s", exc)
            self._cognitive_loop = None

        # --- Professional agent workflow (lifecycle + coordination + learning) ---
        try:
            from app.agents.advanced.workflow import ProfessionalAgentWorkflow
            self._agent_workflow = ProfessionalAgentWorkflow(
                agent_id="orchestrator",
            )
            await self._agent_workflow.initialize()
            logger.info("Professional agent workflow initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Agent workflow init skipped: %s", exc)
            self._agent_workflow = None

        # --- Advanced skill system (discovery, matching, chaining, context) ---
        try:
            from app.skills.advanced.skill_orchestrator import SkillOrchestrator
            self._skill_orchestrator = SkillOrchestrator()
            await self._skill_orchestrator.initialize()
            logger.info("Advanced skill system initialized (%d skills)",
                        len(self._skill_orchestrator.get_active_skills()))
        except Exception as exc:  # noqa: BLE001
            logger.info("Advanced skill system init skipped: %s", exc)
            self._skill_orchestrator = None

        # --- Advanced context self-function system ---
        try:
            from app.context.advanced.context_orchestrator import ContextOrchestrator
            self._context_orchestrator = ContextOrchestrator(
                max_tokens=getattr(self._settings, 'context_max_tokens', 8000),
                reserved_tokens=getattr(self._settings, 'context_reserved_tokens', 2000),
            )
            logger.info("Advanced context self-function system initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Advanced context system init skipped: %s", exc)
            self._context_orchestrator = None

        # --- Professional agent system (communication, quality, self-healing) ---
        try:
            from app.agents.professional.professional_orchestrator import ProfessionalAgentOrchestrator
            self._professional_orchestrator = ProfessionalAgentOrchestrator(
                max_concurrent_tasks=getattr(self._settings, "professional_max_concurrent_tasks", 5),
                quality_threshold=0.7,
                enable_consensus=True,
                enable_self_healing=True,
                enable_proactive=True,
            )
            await self._professional_orchestrator.initialize()
            logger.info("Professional agent system initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Professional agent system init skipped: %s", exc)
            self._professional_orchestrator = None

        # --- Spec 17/18/19/37: brain provider abstraction + router + fallback --
        try:
            from app.runtime.brain_provider import BrainRouter, BrainSpec, available_providers

            specs: dict[str, BrainSpec] = {}

            def _mk(model: str, *, role: str, remote: bool = False,
                    ram: int = 0, ctx: int = 8192) -> BrainSpec | None:
                if not model:
                    return None
                return BrainSpec(
                    model_id=model,
                    provider="openai_compatible" if remote else "ollama",
                    base_url=(getattr(self._settings, "strong_model_base_url", "")
                              or cfg.base_url) if remote else cfg.base_url,
                    api_key=cfg.api_key if not remote else "",
                    context_limit=ctx,
                    temperature=getattr(self._settings, "model_temperature", 0.7),
                    max_tokens=getattr(self._settings, "model_max_tokens", 1024),
                    timeout=getattr(self._settings, "model_timeout", 60.0),
                    is_remote=remote, est_ram_mb=ram,
                )

            _d = _mk(cfg.model_name, role="default")
            if _d:
                specs["default"] = _d
            _s = _mk(getattr(self._settings, "strong_model_name", ""), role="strong", ctx=32768)
            if _s:
                specs["strong"] = _s
            # Per-agent brains as distinct roles (spec 16/47).
            if getattr(self, "_agent_models", None) is not None:
                for role in ("coding", "math", "research", "writing", "security"):
                    try:
                        m = self._agent_models._preferred(role)
                    except Exception:  # noqa: BLE001
                        m = None
                    sp = _mk(m or "", role=role)
                    if sp:
                        specs[role] = sp
            self._brain_router = BrainRouter(specs)
            logger.info("Brain router initialized: %d brains across providers %s",
                        len(specs), available_providers())
        except Exception as exc:  # noqa: BLE001
            logger.info("Brain router init skipped: %s", exc)
            self._brain_router = None

        # --- Spec 31/36: supervision + bounded failure-recovery policy ---------
        try:
            from app.agents.advanced.supervision import Supervisor
            from app.brain.recovery_policy import RecoveryPolicy

            self._supervisor = Supervisor(
                idle_timeout=getattr(self._settings, "model_timeout", 60.0) * 2,
                max_retries=2,
            )
            self._recovery_policy = RecoveryPolicy(max_attempts=3)
            logger.info("Supervisor + recovery policy initialized")
        except Exception as exc:  # noqa: BLE001
            logger.info("Supervisor init skipped: %s", exc)
            self._supervisor = None
            self._recovery_policy = None

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

        allow_dangerous = self._settings.enable_dangerous_tools
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

        # --- spec 46: agent CONFIGURATION from app/config/agents.json ---
        # Config drives enabled/tools/permissions instead of hard-coded
        # selection. Additive: an absent/!broken file leaves the built-ins alone.
        try:
            import json as _json

            cfg_path = Path(__file__).resolve().parent.parent / "config" / "agents.json"
            if cfg_path.is_file():
                cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
                for name, spec in (cfg.get("agents") or {}).items():
                    if name not in self._agents:
                        continue
                    if spec.get("enabled") is False:
                        self._agents.pop(name, None)
                        logger.info("agent '%s' disabled by config", name)
                        continue
                    tools = spec.get("tools")
                    if isinstance(tools, list):
                        allowed = [t for t in tools if t in tool_names]
                        self._agents[name].allowed_tools = allowed
                    # remember the configured brain so AgentModelManager can use it
                    brain = spec.get("brain")
                    if brain:
                        self._agent_config_brains = getattr(
                            self, "_agent_config_brains", {}) or {}
                        self._agent_config_brains[name] = brain
                logger.info("agent config applied from %s", cfg_path.name)
        except Exception as exc:  # noqa: BLE001
            logger.info("agent config skipped: %s", exc)

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
        # --- Cognitive memory shutdown (spec 56) ---
        if self._cognitive_memory is not None:
            try:
                self._cognitive_memory.close()
            except Exception:  # noqa: BLE001
                pass
        # --- Advanced memory shutdown ---
        if getattr(self, "_advanced_memory", None) is not None:
            try:
                await self._advanced_memory.shutdown()
            except Exception:  # noqa: BLE001
                pass
        # --- Advanced agent system shutdown ---
        advanced_agents = getattr(self, "_advanced_agents", None)
        if advanced_agents is not None:
            try:
                await advanced_agents.shutdown()
            except Exception:  # noqa: BLE001
                pass
        # --- Advanced brain system shutdown ---
        advanced_brain = getattr(self, "_advanced_brain", None)
        if advanced_brain is not None:
            try:
                await advanced_brain.shutdown()
            except Exception:  # noqa: BLE001
                pass
        # --- Advanced skill system shutdown ---
        skill_orch = getattr(self, "_skill_orchestrator", None)
        if skill_orch is not None:
            try:
                # SkillOrchestrator has no async shutdown; just clear references
                skill_orch._initialized = False
            except Exception:  # noqa: BLE001
                pass
        # --- Advanced context self-function system shutdown ---
        ctx_orch = getattr(self, "_context_orchestrator", None)
        if ctx_orch is not None:
            try:
                # Record final snapshot for analytics
                snap = ctx_orch.get_snapshot()
                logger.info("Context snapshot at shutdown: %d items, %.2f utilization",
                            snap.window_summary.get("total_items", 0),
                            snap.window_summary.get("utilization", 0.0))
            except Exception:  # noqa: BLE001
                pass
        # --- Professional agent system shutdown ---
        prof_orch = getattr(self, "_professional_orchestrator", None)
        if prof_orch is not None:
            try:
                await prof_orch.shutdown()
            except Exception:  # noqa: BLE001
                pass
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

        Autonomy gating (spec 46/47): high-risk auto-actions (installing tools,
        generating plugins) require autonomy level >= 3. When disallowed, we
        degrade to capability detection only (no install).
        """
        # Autonomy gate (spec 46): installing/creating tools is a high-risk action.
        _auto_allowed = True
        try:
            _auto_allowed, _why = gate_action("install_tool", high_risk=True)
        except Exception:  # noqa: BLE001
            _auto_allowed = True
        from app.tools.tool_acquisition import acquire_by_catalog, generate_plugin

        prompt = (task.prompt or "").lower()
        # --- New Capability Manager (preferred, persistent, policy-gated) ---
        try:
            from app.capability.manager import CapabilityManager
            mgr = CapabilityManager()
            for need in mgr.discover(task.prompt or ""):
                if mgr.status(need) in ("missing", "unknown", "failed"):
                    if not _auto_allowed:
                        logger.info("autonomy gate: skipping auto-acquire of '%s'", need)
                        continue
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
                        ChatMessage(role="system", content=sys_p),
                        ChatMessage(role="user", content=f"Task: {task.prompt}"),
                    ],
                    max_tokens=1024, temperature=0.2,
                )
                import json
                import re as _re
                m = _re.search(r"\{.*\}", decision.content or "", _re.DOTALL)
                if m:
                    obj = json.loads(m.group(0))
                    if obj.get("need"):
                        cap = obj["need"]
                        if not _auto_allowed:
                            logger.info("autonomy gate: skipping plugin generation for '%s'", cap)
                        elif not acquire_by_catalog(cap, self._tools._registry):
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
        """Split a complex goal into subtasks (spec 5).

        Handles the spec's own worked example
        ("Inspect my project, find the bug, fix it, test it, and explain the
        changes") in addition to explicit separators:
          * ' and also ' / ';' / numbered lists  (explicit separators)
          * comma/and-separated imperative clauses with a leading verb
            (inspect/find/fix/test/explain/...)  -- only when >=2 such clauses
            exist, so a normal sentence is never chopped up.
        """
        parts = [p.strip() for p in text.split(" and also ") if p.strip()]
        if len(parts) <= 1:
            parts = [p.strip() for p in text.split(";") if p.strip()]
        if len(parts) <= 1:
            import re as _re
            numbered = _re.findall(r"(?m)^\s*\d+[.)]\s*(.+)$", text)
            if len(numbered) > 1:
                parts = [p.strip() for p in numbered]
        if len(parts) <= 1:
            # Clause splitting: comma / 'and' boundaries followed by a verb.
            import re as _re
            verbs = (
                "inspect|find|fix|test|explain|analyze|analyse|review|refactor|"
                "implement|create|write|build|run|verify|check|deploy|install|"
                "configure|scan|audit|report|summarize|summarise|update|add|remove|"
                "migrate|benchmark|profile|document"
            )
            # split on ', ' or ' and ' only when the NEXT word is a known verb
            raw = _re.split(rf"(?:,\s*|\s+and\s+)(?=(?:{verbs})\b)", text, flags=_re.I)
            clauses = [c.strip().rstrip(".,;:") for c in raw if c.strip()]
            if len(clauses) > 1:
                parts = clauses
        return parts[: self._settings.max_parallel_agents]

    def _is_composite_goal(self, text: str) -> bool:
        """MainBrain decision (spec 5): does this goal need decomposition?

        True when the request contains >=2 distinct imperative clauses
        (inspect/fix/test/explain...) or an explicit multi-part separator.
        This is what lets the Main Brain route a multi-step request to the
        coordinator instead of answering it in one specialist pass.
        """
        try:
            return len(self._split_subtasks(text or "")) > 1
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # spec 49: memory and context budget
    # ------------------------------------------------------------------
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Cheap, dependency-free token estimate (~4 chars/token, min 1)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def _enforce_context_budget(self, messages, task) -> tuple[list, dict]:
        """Fit the prompt into the model window before inference (spec 49).

        Budget = system + task + relevant memory + tool results + output reserve.
        When over budget: (1) drop lowest-priority retrieved/history messages,
        (2) summarize the dropped tail into a single note, (3) return the fitted
        list. The model context is never blindly exceeded.
        """
        reserve = int(getattr(self._settings, "context_reserved_tokens", 0)
                      or getattr(self._settings, "model_max_tokens", 1024) or 1024)
        window = int(getattr(self._settings, "context_max_tokens", 8192) or 8192)
        budget = max(512, window - reserve)

        def _content(m) -> str:
            return getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")

        total = sum(self._estimate_tokens(_content(m)) for m in messages)
        report = {"window": window, "reserve": reserve, "budget": budget,
                  "before": total, "after": total, "evicted": 0, "summarized": False}

        if total <= budget:
            task.data["_context_budget"] = report
            return messages, report

        # Preserve the system prompt (index 0) and the final user turn; evict
        # from the middle (retrieved context / history) lowest-value first.
        if len(messages) <= 2:
            task.data["_context_budget"] = report
            return messages, report

        head = messages[0]
        tail = messages[-1]
        middle = list(messages[1:-1])
        kept: list = []
        dropped: list[str] = []
        running = self._estimate_tokens(_content(head)) + self._estimate_tokens(_content(tail))
        for m in reversed(middle):          # keep the most recent first
            t = self._estimate_tokens(_content(m))
            if running + t <= budget:
                kept.append(m)
                running += t
            else:
                dropped.append(_content(m)[:400])
        kept.reverse()

        if dropped:
            note = "[summarized: %d earlier context item(s) dropped to fit the %d-token window] " % (
                len(dropped), window)
            note += " | ".join(d[:120] for d in dropped[:5])
            try:
                from app.models.message import Message
                summary_msg = Message.system(note)
            except Exception:  # noqa: BLE001
                summary_msg = head
            fitted = [head, summary_msg, *kept, tail]
            report["summarized"] = True
        else:
            fitted = [head, *kept, tail]

        report["evicted"] = len(dropped)
        report["after"] = sum(self._estimate_tokens(_content(m)) for m in fitted)
        task.data["_context_budget"] = report
        logger.info("context budget: %d -> %d tokens (window=%d, evicted=%d)",
                    report["before"], report["after"], window, report["evicted"])
        return fitted, report

    def _pick_llm(self, task_prompt: str):
        """Use the STRONG model only for explicit cyber-critical tasks when configured.

        General factual questions (math, definitions, chat) stay on the fast main
        model: routing them to a large reasoning model (e.g. qwen3:8b) makes every
        simple query take 100+ seconds on CPU and leaves the terminal hanging.
        Only accuracy/critical offensive-security prompts get the strong model.
        """
        if self._llm_strong is None:
            return self._llm
        crit = any(k in (task_prompt or "").lower() for k in
                    ("exploit", "vuln", "cve", "scan", "red team", "offensive", "pentest",
                     "malware", "forensic", "reverse", "recon", "payload", "attack",
                     "exploitation", "privilege escalation", "lateral movement"))
        if crit:
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
        # spec 49: the fast path must respect the context budget too.
        try:
            ctx, _b = self._enforce_context_budget(ctx, task)
        except Exception:  # noqa: BLE001
            pass
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
        """Fan out subtasks to concurrent agent runs and merge their results.

        Spec 32/33 (resource-aware routing): the fan-out width is capped by
        ``settings.max_concurrent_agents`` and every subtask result is run
        through the spec-26 aggregator before it is returned, so a conflicting
        subtask answer is surfaced instead of being concatenated blindly.
        """
        limit = max(1, int(getattr(self._settings, "max_concurrent_agents", 1) or 1))
        sem = asyncio.Semaphore(limit)

        async def _one(sub: str) -> str:
            async with sem:
                sub_task = Task.create(sub, agent_name=agent_name)
                sub_task.mark_running()
                self._history.clear()
                # Spec 29/8/14: a SUBTASK still needs TOOLS -- "inspect the
                # project", "run tests" and "verify the result" are impossible
                # without them, and answering from the model alone produces the
                # "I cannot access the project" failure. But it must stay
                # BOUNDED: one tool round (not the full multi-round loop with
                # reflection + self-consistency, which multiplied LLM calls by
                # the subtask count and blew every wall-clock budget here).
                txt = ""
                try:
                    # spec 6/17: if the subtask clearly needs a tool, run it
                    # FIRST and skip the wasteful _fast_answer. On a 3.6GB/4CPU
                    # host with qwen3:0.6b, every LLM call costs 30-60s, and
                    # doing both doubled the wall clock past the 900s curl
                    # timeout. The tool result IS the answer.
                    invoked = await self._try_explicit_tool(
                        sub_task, "",
                        self._agents.get(agent_name, self._agents["planning"]))
                    if invoked is not None:
                        txt, _ = invoked
                    else:
                        txt, _ = await self._fast_answer(
                            sub_task, self._agents.get(agent_name, self._agents["planning"]))
                except Exception as exc:  # noqa: BLE001
                    logger.info("subtask fast pass failed (%s); using full loop", exc)
                    txt, _ = await self._run_cognition_loop(
                        sub_task, self._agents.get(agent_name, self._agents["planning"]))
                return f"- {sub}\n  {txt}"

        logger.info("parallel fan-out: %d subtasks, concurrency limit %d",
                    len(subtasks), limit)
        # spec 52/58: bound the fan-out. Each subtask may now run a tool, and a
        # tool like python_executor spawns `pytest`, which imports the whole MOON
        # app (including the 88k-vector knowledge base). Running all subtasks at
        # once peaked at 311 MB and got the unit OOM-killed on a 3.7 GB host.
        # A semaphore keeps the peak bounded without serialising the fan-out.
        sem = asyncio.Semaphore(max(1, min(limit, 2)))

        async def _bounded(s: str) -> str:
            async with sem:
                return await _one(s)

        results = await asyncio.gather(*[_bounded(s) for s in subtasks])

        # Spec 26/27: aggregate the subtask answers instead of raw concatenation.
        merged_body = "\n\n".join(results)
        try:
            from app.brain.aggregator import AgentEnvelope, ResultAggregator

            envs = [
                AgentEnvelope(agent_id=f"{agent_name}#{i}", objective=sub,
                              result=res, confidence=0.6)
                for i, (sub, res) in enumerate(zip(subtasks, results))
            ]
            agg = ResultAggregator().aggregate(envs)
            if agg.has_conflict:
                logger.warning("parallel fan-out conflicts: %s",
                               [c.to_dict() for c in agg.conflicts])
                merged_body += (
                    "\n\n[conflicts detected between subtask results — "
                    f"{len(agg.conflicts)}; status={agg.status.value}]")
        except Exception as exc:  # noqa: BLE001
            logger.info("parallel aggregation skipped: %s", exc)

        return "Complex goal decomposed and executed in parallel:\n\n" + merged_body

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
            # spec 7: Data/File + Automation agents
            "data": "data_file", "data_file": "data_file", "file": "data_file",
            "automation": "automation", "workflow": "automation",
        }
        agent = mapping.get(intent, "coordinator")
        # --- spec 5: MainBrain decomposition decision ---
        # A multi-step goal ("inspect, find the bug, fix it, test it, explain")
        # must be decomposed and delegated, not answered by a single specialist.
        # Route composite goals to the coordinator, which fans out via
        # _run_parallel. Explicit single-domain requests are left alone.
        try:
            if (self._is_composite_goal(task.prompt)
                    and "coordinator" in self._agents
                    and intent not in ("cyber", "red_team", "blue_team", "security")):
                agent = "coordinator"
                task.data["_decomposed"] = self._split_subtasks(task.prompt)
                logger.info("composite goal -> coordinator (%d subtasks)",
                            len(task.data["_decomposed"]))
        except Exception:  # noqa: BLE001
            pass
        if agent not in self._agents:
            agent = "coordinator"
        task.agent_name = agent
        logger.info("intent='%s' (conf=%.2f) -> agent='%s'", intent, conf, agent)

    async def run_task(self, task: Task, on_event=None) -> Task:
        if self._llm is None or self._tools is None or self._context is None:
            raise RuntimeError("Orchestrator.setup() must be called first")

        # MOON is always unlocked (lock mode removed) — no gate, proceed directly.
        task.mark_running()
        self._history.clear()
        self._route_intent(task)
        # --- spec 31: begin supervision of this task's agent ---
        if self._supervisor is not None:
            try:
                self._supervisor.start(task.agent_name or "auto", task.id)
            except Exception:  # noqa: BLE001
                pass
        # --- spec 10/12/41 augmentation (additive; degrades cleanly) ---
        try:
            from app.agents.registry import get_registry
            emit("TASK_CREATED", execution_id=task.id, agent_id=task.agent_name, detail=task.prompt[:120])
            _spec = analyze_task(task.prompt)
            task._goal_spec = _spec  # structured analysis (spec 10)
            known = list(self._agents.keys())
            refined = route_agent(_spec, known, task.agent_name)
            # --- spec 5 vs spec 12 precedence ---
            # The decomposition decision wins. A composite goal was routed to
            # the coordinator on purpose; letting capability refinement replace
            # it would silently drop the fan-out and answer a 4-step request in
            # a single specialist pass. Refinement still applies to
            # non-composite goals.
            if task.data.get("_decomposed"):
                refined = "coordinator"
            # Registry-driven capability selection (spec 12 / MOON 40-agent spec):
            # if the runtime router did not refine, ask the Agent Registry for a
            # capability match so the structured roster actually drives routing.
            if (not refined or refined not in self._agents) and not task.data.get("_decomposed"):
                try:
                    cands = get_registry().select(capability=task.prompt)
                    if cands and cands[0].id in self._agents:
                        refined = cands[0].id
                except Exception:  # noqa: BLE001
                    pass
            if refined and refined in self._agents:
                task.agent_name = refined  # capability-based refinement (spec 12)
                emit("AGENT_SELECTED", execution_id=task.id, agent_id=refined,
                     detail=f"selected {refined} by capability")
            try:
                setattr(task, "_selected_agents",
                        [c.id for c in get_registry().select(capability=task.prompt)][:5])
            except Exception:  # noqa: BLE001
                pass
            emit("TASK_STARTED", execution_id=task.id, agent_id=task.agent_name,
                 detail=task.prompt[:120])
        except Exception:  # noqa: BLE001
            pass
        if on_event:
            try:
                await on_event({"stage": "routing", "detail": f"intent -> {task.agent_name}"})
            except Exception:
                pass
        agent = self._agents.get(task.agent_name, self._agents["planning"])
        agent_brain = self._agent_brains.get(agent.name)
        # spec 31: record a RUNNING execution job for this task.id
        self._exec_transition(task.id, "RUNNING", agent_id=agent.name, task=task.prompt)

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
                # spec 31: finalize execution state for the parallel path
                self._exec_transition(task.id, "SUCCESS", agent_id=agent.name,
                                      task=task.prompt, result={"status": "done", "parallel": True})
                return task
            except Exception as exc:  # noqa: BLE001
                logger.info("parallel fan-out fell back to standard loop: %s", exc)

        # --- Advanced: fast-path for simple queries (speed) ---
        # NOTE: the fast path is reserved for EXPLICIT single-domain requests.
        # It previously fired whenever the caller passed any agent name, which
        # meant the coordinator fan-out (spec 5) and intent routing were bypassed
        # and the reported agent did not match the routing decision.
        if (self._settings.enable_fast_path and self._is_simple_query(task.prompt)
                and task.agent_name not in ("auto", "coordinator")
                and not self._is_composite_goal(task.prompt)):
            try:
                text, tokens = await self._fast_answer(task, agent)
                # spec 6/17: if the prompt explicitly requested a known tool,
                # execute it so the answer is grounded in a REAL result.
                try:
                    invoked = await self._try_explicit_tool(task, text, agent)
                    if invoked is not None:
                        text, _ = invoked
                except Exception:  # noqa: BLE001
                    pass
                task.complete(text, data={"agent": agent.name, "fast_path": True, "tokens": tokens})
                task.mark_done()
                # spec 31: finalize execution state for the fast path
                self._exec_transition(task.id, "SUCCESS", agent_id=agent.name,
                                      task=task.prompt, result={"status": "done", "fast_path": True})
                return task
            except Exception as exc:  # noqa: BLE001
                logger.info("fast-path fell back to full loop: %s", exc)
        # --- Advanced memory: proactive context injection ---
        proactive_context: list = []
        if self._advanced_memory is not None:
            try:
                proactive_context = await self._advanced_memory.before_task(task.prompt)
            except Exception:  # noqa: BLE001
                pass

        lesson = ""
        # --- spec 31: supervise the run and ACT if the agent stalls ---
        # Detection alone was useless (nothing consulted it). Wrap the cognition
        # loop in a watchdog that, on timeout, records a stuck event, applies the
        # bounded recovery decision, and cancels the task instead of hanging the
        # caller forever (spec 31 steps 2-4, spec 51 no-infinite-loops).
        #
        # A DECOMPOSED goal (spec 5) legitimately needs more wall clock than a
        # single query, so the budget scales with the subtask count (bounded by
        # max_parallel_agents) rather than being a flat cap that would kill a
        # valid multi-step run on a slow host.
        _base = float(getattr(self._settings, "task_timeout", 180.0) or 180.0)
        try:
            _n_sub = max(1, len(self._split_subtasks(task.prompt)))
        except Exception:  # noqa: BLE001
            _n_sub = 1
        _task_timeout = _base * (1 if _n_sub <= 1 else min(_n_sub, 4))
        logger.info("task %s budget: %.0fs (%d subtask unit(s))", task.id, _task_timeout, _n_sub)

        # Live progress: poll the task's own status so the supervisor watch
        # reflects real activity instead of staying at "starting" for the whole
        # run (which made idle-time reporting meaningless).
        async def _progress_poller(tid: str, tsk) -> None:
            while True:
                await asyncio.sleep(5.0)
                if self._supervisor is None:
                    return
                note = "running"
                try:
                    for it in ("iteration", "tool_calls", "stage"):
                        v = tsk.data.get(it)
                        if v is not None:
                            note = f"{it}={v}"
                            break
                except Exception:  # noqa: BLE001
                    pass
                self._supervisor.beat(tid, note=note)

        _poller = asyncio.create_task(_progress_poller(task.id, task))
        try:
            final_text, tokens = await asyncio.wait_for(
                self._run_cognition_loop(task, agent, on_event=on_event,
                                         proactive_context=proactive_context),
                timeout=_task_timeout,
            )
            if self._supervisor is not None:
                self._supervisor.beat(task.id, note="cognition loop complete")
        except asyncio.CancelledError:
            # Client disconnected / request aborted: release the slot instead of
            # leaving an orphaned watch occupying a concurrency unit.
            if self._supervisor is not None:
                try:
                    self._supervisor.abandon(task.id)
                except Exception:  # noqa: BLE001
                    pass
            raise
        except asyncio.TimeoutError:
            # 1. detect  2. stop/cancel if safe  3. decide  4. update plan
            logger.warning("task %s exceeded task_timeout (%.0fs) -- supervising",
                           task.id, _task_timeout)
            # spec 5: a COMPOSITE goal whose agent loop timed out can still be
            # satisfied by decomposing it -- fan the subtasks out (each a single
            # grounded pass) rather than failing the whole request.
            try:
                _subs = self._split_subtasks(task.prompt)
                if len(_subs) > 1:
                    logger.info("timeout on composite goal -> fan-out fallback "
                                "(%d subtasks)", len(_subs))
                    _merged = await self._run_parallel(_subs, agent.name)
                    task.complete(_merged, data={"agent": agent.name, "parallel": True,
                                                 "decomposed_fallback": True})
                    self._exec_transition(task.id, "SUCCESS", agent_id=agent.name,
                                          task=task.prompt,
                                          result={"status": "done", "parallel": True})
                    if self._supervisor is not None:
                        self._supervisor.finish(task.id, detail="decomposed fallback")
                    _poller.cancel()
                    return task
            except Exception as _exc:  # noqa: BLE001
                logger.info("decomposed fallback failed: %s", _exc)
            if self._supervisor is not None:
                try:
                    self._supervisor.cancel(task.id)
                    _dec = self._supervisor.decide(task.id)
                    task.data["_supervision"] = _dec
                    logger.warning("supervisor decision: %s (%s)",
                                   _dec.get("action"), _dec.get("reason"))
                    emit("AGENT_STUCK", execution_id=task.id, agent_id=agent.name,
                         detail=f"{_dec.get('action')}: {_dec.get('reason')}")
                except Exception:  # noqa: BLE001
                    pass
            task.fail(f"timed out after {_task_timeout:.0f}s (agent supervised and cancelled)")
            self._exec_transition(task.id, "FAILED", agent_id=agent.name,
                                  task=task.prompt,
                                  result={"error": "task_timeout", "supervised": True})
            if self._recovery_policy is not None:
                try:
                    from app.brain.recovery_policy import FailureContext

                    task.data["_recovery_decision"] = self._recovery_policy.decide(
                        FailureContext(agent=agent.name, task=task.prompt,
                                       error="timeout", attempt=1,
                                       other_agents=[a for a in self._agents
                                                     if a != agent.name])
                    ).to_dict()
                except Exception:  # noqa: BLE001
                    pass
            _poller.cancel()
            return task
        finally:
            _poller.cancel()
        try:
            # --- spec 27/41: verification events (additive; degrades cleanly) ---
            try:
                _emit("VERIFICATION_STARTED", execution_id=task.id, agent_id=agent.name)
            except Exception:  # noqa: BLE001
                pass
            validation = await self._validator.validate(task.prompt, final_text)
            try:
                _emit("VERIFICATION_PASSED" if validation.valid else "VERIFICATION_FAILED",
                      execution_id=task.id, agent_id=agent.name,
                      detail="; ".join(validation.issues) if validation.issues else "ok")
            except Exception:  # noqa: BLE001
                pass
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
                try:
                    _emit("MEMORY_UPDATED", execution_id=task.id, agent_id=agent.name,
                          detail="episodic stored")
                except Exception:  # noqa: BLE001
                    pass
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
            # --- spec 26/27/28/39/40: aggregate + conflict-check + SYNTHESIZE ---
            # The Main Brain must never report a single agent's raw text as if it
            # were the verified combined result. Aggregate, detect contradictions,
            # and when there IS a conflict emit the spec-40 response contract
            # (what succeeded / what failed / evidence / next action) instead of
            # the unqualified answer. Additive + degrades cleanly.
            try:
                from app.brain.aggregator import AgentEnvelope, ResultAggregator

                _env = AgentEnvelope(
                    task_id=task.id, agent_id=agent.name,
                    status="completed" if reflection.satisfactory else "failed",
                    objective=task.prompt, result=clean,
                    evidence=list(validation.issues) if validation.issues else [],
                    errors=[] if reflection.satisfactory else list(reflection.improvements or []),
                    confidence=0.85 if validation.valid else 0.4,
                    next_action="verification",
                )
                _envelopes = [getattr(task, "_agent_envelopes", []), _env]
                _flat = [e for sub in _envelopes for e in (sub if isinstance(sub, list) else [sub])]
                _agg = ResultAggregator().aggregate(_flat)
                task._aggregated = _agg.to_dict()
                if _agg.has_conflict:
                    logger.warning(
                        "Result conflict on task %s: %s",
                        task.id, [c.to_dict() for c in _agg.conflicts])
                    emit("CONFLICT_DETECTED", execution_id=task.id, agent_id=agent.name,
                         detail=f"{len(_agg.conflicts)} conflict(s), status={_agg.status.value}")
                    # spec 39/40: synthesize ONE coherent response that does not
                    # claim success over a detected contradiction.
                    _synth = self._formatter.synthesize(_agg, user_request=task.prompt)
                    if _synth:
                        clean = _synth
                        task.data["synthesized"] = True
            except Exception as exc:  # noqa: BLE001
                logger.info("result aggregation skipped: %s", exc)
            task.complete(clean, data={"tokens_used": tokens, "issues": validation.issues, "agent": agent.name}, tokens_used=tokens)
            await self._memory.remember(clean, long_term=False)
            # --- Cognitive memory: store task result (spec 61/62) ---
            if self._cognitive_memory is not None:
                try:
                    self._cognitive_memory.store(
                        f"Task: {task.prompt[:200]}\nResult: {clean[:500]}",
                        source_type=SourceType.AGENT,
                        scope=Scope.TASK,
                        type_=MemoryType.EPISODIC,
                        agent_id=agent.name,
                        task_id=task.id,
                        explicit=False,
                    )
                    # spec 32/57: sync after each task (resource-conscious: on_write)
                    if self._sync_engine is not None:
                        try:
                            self._sync_engine.sync()
                        except Exception:  # noqa: BLE001
                            pass
                except Exception:  # noqa: BLE001
                    pass
            # --- Advanced memory: store task result ---
            if self._advanced_memory is not None:
                try:
                    await self._advanced_memory.after_task(
                        task.prompt, clean, success=reflection.satisfactory,
                        lesson=lesson,
                    )
                except Exception:  # noqa: BLE001
                    pass
            # --- Advanced agents: record performance + share context + learn ---
            if self._advanced_agents is not None:
                try:
                    await self._advanced_agents._performance.record(
                        TaskExecution(
                            task_id=task.id,
                            agent_id=agent.name,
                            start_time=0,
                            end_time=0,
                            success=reflection.satisfactory,
                            tokens_used=tokens,
                            quality_score=1.0 if reflection.satisfactory else 0.5,
                        )
                    )
                    await self._advanced_agents.share_context(
                        task_id=task.id,
                        agent_id=agent.name,
                        content=clean[:500],
                        context_type="result",
                    )
                    await self._advanced_agents._learning.record_outcome(
                        agent_id=agent.name,
                        task_prompt=task.prompt,
                        outcome=clean[:500],
                        success=reflection.satisfactory,
                        lesson=lesson,
                    )
                except Exception:  # noqa: BLE001
                    pass
            # --- Professional agent workflow: lifecycle + coordination + state ---
            if self._agent_workflow is not None:
                try:
                    workflow_result = await self._agent_workflow.execute(
                        task=task.prompt,
                        context={
                            "output": clean,
                            "tool_calls": [
                                {"name": t, "success": True, "duration": 0}
                                for t in (self._last_tool_outputs or [])
                            ],
                        },
                        requirements=[],
                        priority=5,
                    )
                    task.data["agent_workflow"] = {
                        "stages_completed": workflow_result.stages_completed,
                        "execution_time": workflow_result.execution_time,
                        "errors": workflow_result.errors,
                    }
                except Exception:  # noqa: BLE001
                    pass
            # --- Advanced brain: metacognition + uncertainty + reflection ---
            if self._advanced_brain is not None:
                try:
                    # Deep reflection on the task execution
                    from app.brain.advanced.reflection import ReflectionLevel
                    reflection_result = await self._advanced_brain._reflection.reflect(
                        task=task.prompt,
                        approach=f"agent:{agent.name}",
                        outcome=clean[:500],
                        success=reflection.satisfactory,
                        iterations=tokens // 100 if tokens else 1,
                        errors=validation.issues,
                        level=ReflectionLevel.TASK,
                    )
                    # Uncertainty estimation
                    uncertainty_result = await self._advanced_brain._uncertainty.estimate(
                        model_confidence=0.8 if reflection.satisfactory else 0.3,
                        task_complexity=0.5,
                        task_type="general",
                    )
                    # Metacognitive update
                    await self._advanced_brain._meta.update(
                        confidence=uncertainty_result.confidence,
                        uncertainty=uncertainty_result.uncertainty,
                        latency=tokens / 100 if tokens else 0.1,
                        error=not reflection.satisfactory,
                        success=reflection.satisfactory,
                    )
                    # Store reflection in task data
                    task.data["advanced_brain"] = {
                        "reflection": {
                            "critique": reflection_result.critique,
                            "lessons": reflection_result.lessons_learned,
                            "improvements": reflection_result.improvements,
                        },
                        "uncertainty": {
                            "confidence": uncertainty_result.confidence,
                            "uncertainty": uncertainty_result.uncertainty,
                        },
                        "metacognition": self._advanced_brain._meta.get_summary(),
                    }
                except Exception:  # noqa: BLE001
                    pass
            # --- Advanced skill system: record skill performance ---
            if self._skill_orchestrator is not None:
                try:
                    matched = task.data.get("skills_matched", [])
                    for skill_info in matched:
                        self._skill_orchestrator.record_skill_usage(
                            skill_name=skill_info["name"],
                            task=task.prompt,
                            success=reflection.satisfactory,
                            execution_time=0.0,  # tracked at skill level, not task level
                        )
                    # Store skill performance summary in task data
                    task.data["skill_system"] = {
                        "matched_skills": [s["name"] for s in matched],
                        "performance_summary": self._skill_orchestrator.get_performance_summary(),
                    }
                except Exception:  # noqa: BLE001
                    pass
            # --- Advanced context self-function: record context analytics ---
            if self._context_orchestrator is not None:
                try:
                    ctx_state = self._context_orchestrator.assess()
                    if ctx_state:
                        task.data["context_system"] = {
                            "health": ctx_state.health.value,
                            "utilization": ctx_state.utilization,
                            "total_items": ctx_state.total_items,
                            "sources": ctx_state.sources,
                            "recommendations": ctx_state.recommendations,
                        }
                except Exception:  # noqa: BLE001
                    pass
            # --- Professional agent system: quality gate + analytics + proactive ---
            if self._professional_orchestrator is not None:
                try:
                    # Quality gate: validate output before returning
                    quality_result = await self._professional_orchestrator._quality_gate.validate(
                        output=clean,
                        task=task.prompt,
                        context="",
                    )
                    task.data["professional_quality"] = {
                        "score": quality_result.overall_score,
                        "passed": quality_result.passed,
                        "level": quality_result.level.value,
                        "checks": [
                            {
                                "stage": c.stage.value,
                                "passed": c.passed,
                                "score": c.score,
                                "issues": c.issues,
                            }
                            for c in quality_result.checks
                        ],
                    }
                    # Record execution analytics
                    from app.agents.professional.execution_analytics import ExecutionRecord
                    await self._professional_orchestrator._analytics.record_execution(
                        ExecutionRecord(
                            execution_id=task.id,
                            task_type="general",
                            agent_name=agent.name,
                            start_time=time.time(),
                            end_time=time.time(),
                            success=reflection.satisfactory,
                            tokens_used=tokens,
                            metadata={
                                "quality_score": quality_result.overall_score,
                                "quality_passed": quality_result.passed,
                            },
                        )
                    )
                    # Self-healing: check for issues
                    if self._professional_orchestrator._self_healing is not None:
                        health = self._professional_orchestrator._self_healing.get_health()
                        if isinstance(health, dict):
                            unhealthy = [
                                name for name, check in health.items()
                                if check.status.value in ("unhealthy", "degraded")
                            ]
                            if unhealthy:
                                task.data["professional_health"] = {
                                    "unhealthy_components": unhealthy,
                                    "total_components": len(health),
                                }
                    # Proactive suggestions
                    if self._professional_orchestrator._proactive is not None:
                        suggestions = await self._professional_orchestrator._proactive.analyze(
                            conversation=[{"role": "user", "content": task.prompt}],
                            current_task=task.prompt,
                        )
                        if suggestions:
                            task.data["professional_suggestions"] = [
                                {
                                    "type": s.suggestion_type.value,
                                    "priority": s.priority.value,
                                    "text": s.text,
                                    "confidence": s.confidence,
                                }
                                for s in suggestions
                            ]
                except Exception:  # noqa: BLE001
                    pass
            # spec 31: mark the execution job SUCCESS
            self._exec_transition(task.id, "SUCCESS", agent_id=agent.name, task=task.prompt,
                                  result={"status": "done", "agent": agent.name})
        except Exception as exc:
            logger.exception("Task %s failed", task.id)
            task.fail(str(exc))
            # spec 31: mark the execution job FAILED
            self._exec_transition(task.id, "FAILED", agent_id=agent.name, task=task.prompt,
                                  result={"error": str(exc)})
            # --- spec 31/36: supervise the failure and DECIDE (never loop) ---
            try:
                if self._supervisor is not None:
                    self._supervisor.finish(task.id, failed=True, detail=str(exc)[:160])
                if self._recovery_policy is not None:
                    from app.brain.recovery_policy import FailureContext

                    _brain_ok = True
                    if self._brain_router is not None:
                        try:
                            _h = self._brain_router.health("default")
                            _brain_ok = True if _h is None else bool(_h.available)
                        except Exception:  # noqa: BLE001
                            _brain_ok = False
                    ctx = FailureContext(
                        agent=agent.name, task=task.prompt, error=str(exc),
                        attempt=int(task.data.get("_recovery_attempts", 0)),
                        max_attempts=3,
                        brain_healthy=_brain_ok,
                        other_agents=[a for a in self._agents if a != agent.name],
                        task_is_composite=len(self._split_subtasks(task.prompt)) > 1,
                        high_risk=bool(getattr(self._settings, "enable_dangerous_tools", False)),
                    )
                    decision = self._recovery_policy.decide(ctx)
                    task.data["_recovery_decision"] = decision.to_dict()
                    logger.warning("Recovery decision for task %s: %s (%s)",
                                   task.id, decision.action.value, decision.reason)
                    emit("RECOVERY_DECISION", execution_id=task.id, agent_id=agent.name,
                         detail=f"{decision.action.value}: {decision.reason}")
            except Exception:  # noqa: BLE001
                pass
            # spec 25/26/29: classify failure + emit a PROPOSAL-ONLY improvement
            # (never auto-applied; requires autonomy level 5 + explicit authorization).
            try:
                from app.learning import FailureClassifier
                kind = FailureClassifier.classify(str(exc))
                alt = FailureClassifier.safe_alternative(kind)
                emit("IMPROVEMENT_PROPOSED", agent_id=agent.name,
                     detail=f"failure={kind}; suggestion={alt}")
                SelfImprovement().submit(
                    observation=f"task {task.id} failed: {str(exc)[:200]}",
                    problem=kind, target_file="app/brain/orchestrator.py",
                    patch_text="",  # no auto-patch; human/operator supplies the fix
                )
            except Exception:  # noqa: BLE001
                pass
        return task

    def _make_tool_executor(self):
        """Create a simple async tool executor for the CognitiveLoop.

        Wraps self._tools.run() into a callable that the CognitiveLoop can use.
        """
        async def _execute(tool_name: str, tool_args: dict[str, Any]) -> str:
            if self._tools is None:
                return f"[no tool manager for {tool_name}]"
            try:
                result = await self._tools.run(tool_name, tool_args)
                return str(result.output)
            except Exception as exc:
                return f"Error executing {tool_name}: {exc}"
        return _execute

    async def _run_cognition_loop(
        self,
        task: Task,
        agent: AgentCard,
        on_event=None,
        *,
        system_override: str | None = None,
        proactive_context: list | None = None,
    ) -> tuple[str, int]:
        assert self._llm is not None and self._tools is not None and self._context is not None
        retrieved = await self._memory.semantic_recall(task.prompt) if self._memory else []
        # Cognitive memory retrieval (spec 20/21/22/24)
        cog_hit_count = 0
        if self._cognitive_memory is not None:
            try:
                cog_hits = self._cognitive_memory.search(
                    task.prompt, top_k=8, agent_id=agent.name,
                )
                cog_hit_count = len(cog_hits)
                # spec 24/25: use ContextEngine to build a budgeted context block
                if self._context_engine is not None and cog_hits:
                    try:
                        ctx_result = self._context_engine.build(
                            memories=cog_hits,
                            system_prompt=system_override or "",
                            user_input=task.prompt,
                            task_state="",
                            tool_results="",
                        )
                        if ctx_result.text:
                            retrieved.append({
                                "content": ctx_result.text,
                                "score": 0.9,
                                "source": "cognitive_memory",
                                "scope": "budgeted",
                                "type": "context",
                                "confidence": 0.9,
                            })
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("ContextEngine build failed (skipped): %s", exc)
                        # Fallback: add hits directly
                        for h in cog_hits:
                            retrieved.append({
                                "content": h.record.content,
                                "score": h.score,
                                "source": "cognitive_memory",
                                "scope": h.record.scope.value,
                                "type": h.record.type.value,
                                "confidence": h.record.confidence,
                            })
                else:
                    for h in cog_hits:
                        retrieved.append({
                            "content": h.record.content,
                            "score": h.score,
                            "source": "cognitive_memory",
                            "scope": h.record.scope.value,
                            "type": h.record.type.value,
                            "confidence": h.record.confidence,
                        })
            except Exception as exc:  # noqa: BLE001
                logger.debug("Cognitive memory search failed (skipped): %s", exc)
        # Inject proactive memory context from advanced memory system
        if proactive_context:
            for ctx in proactive_context:
                if hasattr(ctx, 'content') and ctx.content:
                    retrieved.append({
                        "content": f"[proactive] {ctx.content}",
                        "score": getattr(ctx, 'relevance', 0.5),
                        "source": getattr(ctx, 'source', 'proactive'),
                    })
        if self._memory is not None:
            try:
                for ep in self._memory.episodic.recall(task.prompt, k=3):
                    if ep.lesson:
                        retrieved.append({"content": f"[past lesson] goal: {ep.goal} | lesson: {ep.lesson}", "score": 0.6})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Episodic recall failed (skipped): %s", exc)
        # --- Advanced skill system: match + inject skill context ---
        skill_context_str = ""
        matched_skills: list[str] = []
        if self._skill_orchestrator is not None:
            try:
                matches = self._skill_orchestrator.match_skills(task.prompt, top_k=3)
                if matches:
                    matched_skills = [m.skill_name for m in matches if m.score > 0.1]
                    if matched_skills:
                        skill_context_str = self._skill_orchestrator.inject_multiple_skills(
                            matched_skills, task.prompt
                        )
                        # Add skill context to retrieved for semantic recall
                        retrieved.append({
                            "content": f"[skill context] {skill_context_str[:500]}",
                            "score": 0.8,
                            "source": "skill_system",
                        })
                        # Store in task data
                        task.data["skills_matched"] = [
                            {"name": m.skill_name, "score": m.score, "reason": m.reason}
                            for m in matches
                        ]
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skill matching failed (skipped): %s", exc)
        # --- Advanced context self-function: inject context into retrieved ---
        if self._context_orchestrator is not None:
            try:
                # Add retrieved items to context window
                for r in retrieved:
                    content = r.get("content", "") if isinstance(r, dict) else getattr(r, "content", "")
                    if content:
                        self._context_orchestrator.add(
                            content,
                            source=r.get("source", "retrieval") if isinstance(r, dict) else getattr(r, "source", "retrieval"),
                            relevance=r.get("score", 0.5) if isinstance(r, dict) else getattr(r, "relevance", 0.5),
                            importance=0.6,
                        )
                # Assess context health
                ctx_state = self._context_orchestrator.assess()
                if ctx_state and ctx_state.health.value in ("warning", "critical", "overflow"):
                    # Compress if needed
                    self._context_orchestrator.compress()
                    logger.info("Context compressed due to %s health", ctx_state.health.value)
                # Inject context into prompt
                ctx_result = self._context_orchestrator.inject(
                    base_prompt=task.prompt,
                    system_prefix=system_override,
                )
                if ctx_result.injected_tokens > 0:
                    # Add injected context to retrieved for the context builder
                    retrieved.append({
                        "content": f"[context window] {ctx_result.prompt[:500]}",
                        "score": 0.9,
                        "source": "context_window",
                    })
            except Exception as exc:  # noqa: BLE001
                logger.debug("Context self-function failed (skipped): %s", exc)
        messages = await self._context.build(
            task=task, history=self._history, retrieved=retrieved, agent=agent,
            system_override=system_override,
        )
        # --- spec 49: enforce the context budget BEFORE inference ---
        # system tokens + task tokens + memory + tool results + output reserve
        # must fit the model window; if not, evict low-priority items, then
        # summarize, then retry. Never blindly exceed the model context.
        try:
            messages, _budget = self._enforce_context_budget(messages, task)
        except Exception as exc:  # noqa: BLE001
            logger.info("context budget enforcement skipped: %s", exc)
        tool_specs = self._tools.available_specs()
        total_tokens = 0
        final_text = ""
        tool_outputs: list[str] = []
        # --- spec 30 augmentation: ModelRouter recommends a model for this step ---
        try:
            _coding = any(k in (task.prompt or "").lower() for k in ("code", "python", "function", "debug", "script"))
            _reasoning = any(k in (task.prompt or "").lower() for k in ("why", "reason", "prove", "analyze", "design"))
            _model_rec = choose_model(complexity="high" if (_coding or _reasoning) else "low",
                                      coding=_coding, reasoning=_reasoning)
            task._model_recommendation = _model_rec
            emit("MODEL_SELECTED", execution_id=task.id, agent_id=agent.name,
                 detail=str(_model_rec.get("model")))
        except Exception:  # noqa: BLE001
            pass
        if on_event:
            try:
                await on_event({"stage": "thinking", "detail": f"recalled {len(retrieved)} memories; building context"})
            except Exception:
                pass

        # --- Professional cognitive loop: ReAct reasoning with working memory ---
        if self._cognitive_loop is not None:
            try:
                # Build context string from retrieved memories
                ctx_parts = []
                for r in retrieved[:5]:
                    if isinstance(r, dict):
                        ctx_parts.append(r.get("content", ""))
                    elif hasattr(r, 'content'):
                        ctx_parts.append(r.content)
                cognitive_context = "\n".join(ctx_parts) if ctx_parts else None

                # Run the cognitive loop for initial reasoning
                cog_result = await self._cognitive_loop.run(
                    task=task.prompt,
                    context=cognitive_context,
                    available_tools=tool_specs,
                    system_prompt=system_override,
                )

                # If the cognitive loop produced a confident answer, use it
                if cog_result.success and cog_result.confidence > 0.7:
                    if on_event:
                        try:
                            await on_event({"stage": "cognitive_loop", "detail": f"ReAct answer (confidence={cog_result.confidence:.2f})"})
                        except Exception:
                            pass
                    # Store cognitive loop metadata in task
                    task.data["cognitive_loop"] = {
                        "strategy": cog_result.strategy_used,
                        "confidence": cog_result.confidence,
                        "uncertainty": cog_result.uncertainty,
                        "iterations": cog_result.iterations,
                        "tool_calls": cog_result.tool_calls,
                        "execution_time": cog_result.execution_time,
                    }
                    return cog_result.answer, cog_result.iterations

                # Otherwise, inject working memory context into messages
                if cog_result.working_memory_context:
                    messages.append(ChatMessage(
                        role="system",
                        content=f"[Working memory]\n{cog_result.working_memory_context}",
                    ))

                # Store cognitive loop metadata even if not confident
                task.data["cognitive_loop"] = {
                    "strategy": cog_result.strategy_used,
                    "confidence": cog_result.confidence,
                    "uncertainty": cog_result.uncertainty,
                    "iterations": cog_result.iterations,
                    "tool_calls": cog_result.tool_calls,
                    "execution_time": cog_result.execution_time,
                    "used_as_context": True,
                }
            except Exception as exc:
                logger.debug("Cognitive loop failed (continuing with standard loop): %s", exc)

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
            # GUARD: a per-agent reasoning model (e.g. deepseek-r1:1.5b) can
            # "think" for 100+ seconds on CPU and stall the whole task, leaving
            # the terminal with no reply. Bound every completion to a hard timeout
            # and, on stall, retry on the fast shared model (qwen2.5:1.5b) so MOON
            # always answers promptly instead of hanging. 30s: a 1.5b/3b call
            # finishes in 1-3s; anything past 30s is a stuck reasoning model.
            try:
                resp = await asyncio.wait_for(
                    llm.complete(messages, tools=tool_specs if tool_specs else None, max_tokens=4096),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning("llm.complete timed out (%s); falling back to shared model",
                               getattr(llm, "_model", "?"))
                resp = await self._llm.complete(
                    messages, tools=tool_specs if tool_specs else None, max_tokens=4096)
            total_tokens += 1
            if resp.has_tool_calls:
                for call in resp.tool_calls:
                    args = self._parse_args(call.get("arguments", "{}"))
                    try:
                        _emit("TOOL_SELECTED", execution_id=task.id, agent_id=agent.name,
                              detail=call.get("name", "tool"))
                        _emit("TOOL_STARTED", execution_id=task.id, agent_id=agent.name,
                              detail=call.get("name", "tool"))
                    except Exception:  # noqa: BLE001
                        pass
                    if on_event:
                        try:
                            await on_event({"stage": "tool_call", "detail": call.get("name", "tool")})
                        except Exception:  # noqa: BLE001
                            pass
                    result = await self._tools.run(call["name"], args, agent=agent)
                    try:
                        _emit("TOOL_COMPLETED", execution_id=task.id, agent_id=agent.name,
                              detail=call.get("name", "tool"))
                    except Exception:  # noqa: BLE001
                        pass
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
            # --- spec 6/17 tool-intent fallback (additive; degrades cleanly) ---
            # Small local models often do not emit OpenAI-style tool_calls. When
            # the prompt explicitly requests a known tool, parse the intent and
            # execute the tool directly so the agent still produces a REAL result
            # (spec 6: "every tool invocation must pass ... AUDIT LOG" and return
            # a real result, not a description of how to call it).
            if not resp.has_tool_calls:
                try:
                    invoked = await self._try_explicit_tool(task, final_text, agent)
                    if invoked is not None:
                        final_text, _out = invoked
                except Exception as exc:  # noqa: BLE001
                    logger.info("explicit tool fallback skipped: %s", exc)
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
            if llm is None or getattr(llm, "_disabled", False):
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
        # --- Advanced memory: proactive context injection ---
        proactive_msgs: list = []
        if self._advanced_memory is not None:
            try:
                proactive_ctx = await self._advanced_memory.before_task(prompt)
                for ctx in proactive_ctx:
                    if hasattr(ctx, 'content') and ctx.content:
                        proactive_msgs.append(ChatMessage(role="system", content=f"[memory] {ctx.content}"))
            except Exception:  # noqa: BLE001
                pass
        messages = [ChatMessage(role="system", content=persona), *proactive_msgs, ChatMessage(role="user", content=prompt)]
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
        # --- Advanced memory: store result ---
        if self._advanced_memory is not None and text and "could not form a reply" not in text:
            try:
                await self._advanced_memory.after_task(prompt, text, success=True)
            except Exception:  # noqa: BLE001
                pass
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

    # --- spec 31 execution subsystem (additive; degrades cleanly) -------
    def _exec_manager(self):
        """Lazily create the persistent ExecutionManager (spec 31)."""
        if self._exec_mgr is None:
            try:
                from app.execution import ExecutionManager
                self._exec_mgr = ExecutionManager()
            except Exception:  # noqa: BLE001
                self._exec_mgr = None
        return self._exec_mgr

    def _exec_transition(self, exec_id: str, to: str, *, agent_id: str = "", task: str = "",
                         result: dict | None = None) -> None:
        em = self._exec_manager()
        if em is None:
            return
        try:
            from app.execution import ExecState
            if em.get(exec_id) is None:
                em.create(exec_id, agent_id=agent_id, task=task)
            target = ExecState(to)
            # Honor the validated state machine (spec 31): RUNNING must pass
            # through VERIFYING before SUCCESS.
            if target is ExecState.SUCCESS and em.get(exec_id).state is ExecState.RUNNING:
                em.transition(exec_id, ExecState.VERIFYING)
            em.transition(exec_id, target, result=result)
        except Exception:  # noqa: BLE001
            pass

    # --- spec 6/17 explicit tool-intent fallback (additive) ----------------
    async def _try_explicit_tool(self, task, final_text: str, agent):
        """If the prompt explicitly asks for a known tool and the model did not
        call it, invoke the tool deterministically and fold the real result into
        the response. Returns (new_text, tool_output) or None when not applicable.
        """
        prompt = (task.prompt or "").lower()
        registry = getattr(self._tools, "_registry", None)
        if registry is None:
            return None
        tool_names = list(getattr(registry, "tool_names", []))
        # Map common request phrases to a registered tool (kept for the
        # special-case arg builders below).
        aliases = {
            "python_executor": ["python_executor", "run code", "execute code", "run python", "execute python", "compute"],
            "file_manager": ["file_manager", "write a file", "read the file", "list files", "create file"],
            "web_search": ["web_search", "search the web", "search for"],
            "terminal": ["terminal", "run command", "shell command"],
            "git_tool": ["git_tool", "git "],
        }
        chosen = None
        _intent_args: dict | None = None
        # 1) Direct mention of any registered tool name in the prompt.
        for tname in tool_names:
            if tname.lower() in prompt:
                chosen = tname
                break
        # 2) Alias phrase match (the 5 special cases above).
        if chosen is None:
            for tname in tool_names:
                for kw in aliases.get(tname, []):
                    if kw in prompt:
                        chosen = tname
                        break
                if chosen:
                    break
        # 3) Keyword match against the registry's real tool descriptions so the
        #    brain can deterministically run ANY of the 43 tools when the small
        #    local model narrates instead of emitting OpenAI-style tool_calls.
        if chosen is None:
            # 2b) INTENT mapping for verbs that name no tool but clearly require
            #     one. "inspect the project", "run the tests" and "verify the
            #     result" are the spec-56 workflow, and without this the subtask
            #     answers from the model alone ("I cannot access the project").
            _intent = (
                (("inspect", "examine", "survey", "audit the project",
                  "understand the project", "look at the project",
                  "project structure"), "file_manager",
                 {"action": "list", "path": "."}),
                (("run the tests", "run tests", "test suite", "pytest",
                  "regression test"), "python_executor",
                 {"code": "import subprocess,sys;sys.exit(subprocess.call(['python','-m','pytest','-q','--no-header','-x'],cwd='.'))"}),
                (("verify the result", "verify the fix", "confirm the fix",
                  "check the result"), "git", {"action": "status"}),
                (("git status", "repository status", "repo status",
                  "current branch"), "git", {"action": "status"}),
            )
            for _phrases, _tname, _targs in _intent:
                if _tname in tool_names and any(ph in prompt for ph in _phrases):
                    chosen = _tname
                    _intent_args = dict(_targs)
                    break
        else:
            _intent_args = None
        if chosen is None:
            import re as _re
            # tokenise the prompt into words (drop very short/trivial tokens)
            words = set(_re.findall(r"[a-z0-9_]+", prompt))
            best, best_score = None, 0
            for tname in tool_names:
                card = registry.tool_meta.get(tname) if hasattr(registry, "tool_meta") else None
                desc = (getattr(card, "description", "") or "").lower()
                score = 0
                # match on tool name tokens
                for tok in _re.findall(r"[a-z0-9_]+", tname.lower()):
                    if len(tok) >= 4 and tok in words:
                        score += 2
                # match on description keywords present in the prompt
                for kw in _re.findall(r"[a-z0-9_]{4,}", desc):
                    if kw in words:
                        score += 1
                if score > best_score:
                    best, best_score = tname, score
            if best_score >= 2:
                chosen = best
        if chosen is None:
            return None
        # Build minimal args from the prompt (best-effort, safe).
        # An intent-mapped call already carries its args.
        args: dict = {}
        if _intent_args:
            args = _intent_args
        try:
            if args:
                pass
            elif chosen == "python_executor":
                import re
                # Only auto-run when the user explicitly provides a code snippet
                # (clear intent to execute). Do NOT guess arithmetic from prose —
                # a brittle regex would produce wrong results. The model answers
                # such prompts correctly from knowledge; we only step in when a
                # real snippet is present.
                m = re.search(r"print\(([^)]*)\)", task.prompt)
                if not m:
                    m = re.search(r"exec\(([^)]*)\)", task.prompt)
                if not m and "```" in task.prompt:
                    m = re.search(r"```(?:python)?\s*(.*?)```", task.prompt, re.S)
                if not m:
                    return None
                # Pass the FULL snippet (group 0) so the executor prints/runs it
                # and produces real output. Stripping to the inner expression
                # would evaluate silently and yield an empty result.
                code = m.group(0).strip()
                args = {"code": code}
            elif chosen == "file_manager":
                args = {"action": "list", "path": "."}
            elif chosen == "terminal":
                import re as _re
                p = task.prompt or ""
                cmd = ""
                # 1) fenced code block (bash/sh/shell)
                m = _re.search(r"```(?:bash|sh|shell)?\s*(.*?)```", p, _re.S | _re.I)
                if m:
                    cmd = m.group(1).strip()
                else:
                    # 2) explicit "command:" / "terminal tool:" marker
                    m = _re.search(r"(?:command|terminal tool)\s*[:\-]\s*(.+)", p, _re.I)
                    if m:
                        cmd = m.group(1).strip()
                    else:
                        # 3) inline 'echo ...' / 'run: ...'
                        m = _re.search(r"\b(?:echo|run|sh|bash|ls|cat|pwd|whoami|date|uname|python|curl|wget|git|pip|apt|systemctl|cat)\b[^\n]*", p, _re.I)
                        if m:
                            cmd = m.group(0).strip()
                # Trim trailing prose (" and report ...", sentence end) so only the
                # command is executed. The terminal tool itself refuses dangerous input.
                if cmd:
                    cmd = _re.split(r"\s+and (?:report|tell|show|print)|\.\s|[\n]", cmd, 1)[0].strip().rstrip(".")
                    args = {"command": cmd}
        except Exception:  # noqa: BLE001
            args = {}
        try:
            _emit("TOOL_SELECTED", execution_id=task.id, agent_id=agent.name, detail=chosen)
            _emit("TOOL_STARTED", execution_id=task.id, agent_id=agent.name, detail=chosen)
        except Exception:  # noqa: BLE001
            pass
        result = await self._tools.run(chosen, args, agent=agent)
        out = str(result.output)
        try:
            _emit("TOOL_COMPLETED", execution_id=task.id, agent_id=agent.name, detail=chosen)
        except Exception:  # noqa: BLE001
            pass
        if out:
            self._last_tool_outputs = [out]
            return (f"{final_text.strip()}\n\n[tool:{chosen}] -> {out}", out)
        return None
