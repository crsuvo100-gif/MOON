"""orchestrator.py -- the agent's "brain" coordinator.

Wires together every cognitive module, the model service, the memory manager,
the tool manager, and the per-agent brains. ``run_task`` executes the full
cognition loop; ``quick_reply`` is the fast single-call path (chat/WS/voice).
Autonomous self-learning consolidates every interaction into the durable brain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.brain.agent_brain import AgentBrain
from app.brain.context_builder import ContextBuilder
from app.brain.error_recovery import ErrorRecovery
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
from app.services.llm_service import ChatMessage, LLMService
from app.tools.api_requests import ApiRequestsTool
from app.tools.browser import BrowserTool
from app.tools.database import DatabaseTool
from app.tools.file_manager import FileManagerTool
from app.tools.image_processing import ImageProcessingTool
from app.tools.ocr import OcrTool
from app.tools.pdf_reader import PdfReaderTool
from app.tools.python_executor import PythonExecutorTool
from app.tools.registry import ToolRegistry
from app.tools.system_command_tool import SystemCommandTool
from app.tools.terminal import TerminalTool
from app.tools.web_search import WebSearchTool

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
        ):
            registry.register(tool)

        try:
            from app.plugins.loader import load_plugins

            plugin_summary = load_plugins(registry)
            if any(plugin_summary.values()):
                logger.info("Loaded plugins: %s", plugin_summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plugin loading skipped: %s", exc)

        allow_dangerous = True
        enabled_names = {t.name for t in registry.all()}
        self._tools = ToolManager(registry, enabled_tools=enabled_names, allow_dangerous=allow_dangerous)

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
                brain = AgentBrain(name, main_brain=self)
                await brain.setup()
                self._agent_brains[name] = brain
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent brain '%s' init skipped: %s", name, exc)
        logger.info("Connected %d agent brains", len(self._agent_brains))
        logger.info("Orchestrator setup complete (model=%s)", cfg.model_name)

    def _register_agents(self, registry: ToolRegistry) -> None:
        all_tools = [t.name for t in registry.all()]
        self._agents = {
            "coding": AgentCard("coding", "Write and refactor code", allowed_tools=all_tools),
            "research": AgentCard("research", "Gather and synthesize facts", allowed_tools=["web_search", "browser", "api_requests", "file_manager"]),
            "browser": AgentCard("browser", "Navigate and read web pages", allowed_tools=["browser", "web_search"]),
            "writing": AgentCard("writing", "Produce written content", allowed_tools=["file_manager"]),
            "vision": AgentCard("vision", "Process images", allowed_tools=["image_processing", "ocr", "file_manager"]),
            "planning": AgentCard("planning", "Coordinate sub-tasks", allowed_tools=all_tools),
            "memory": AgentCard("memory", "Index and recall knowledge", allowed_tools=["file_manager", "pdf_reader"]),
            "review": AgentCard("review", "Critique outputs", allowed_tools=[]),
            "debug": AgentCard("debug", "Diagnose and fix failures", allowed_tools=all_tools),
            "coordinator": AgentCard("coordinator", "Route a complex goal to specialist agents", allowed_tools=all_tools),
            "manager": AgentCard("manager", "Supervise and quality-gate multi-agent work", allowed_tools=all_tools),
        }

    async def teardown(self) -> None:
        if self._llm is not None:
            await self._llm.teardown()
        logger.info("Orchestrator torn down")

    async def run_task(self, task: Task) -> Task:
        if self._llm is None or self._tools is None or self._context is None:
            raise RuntimeError("Orchestrator.setup() must be called first")

        gate = self._lock.observe(task.prompt)
        if gate is not None:
            task.mark_running()
            task.complete(gate, data={"locked": self._lock.locked})
            return task

        task.mark_running()
        self._history.clear()
        agent = self._agents.get(task.agent_name, self._agents["planning"])
        agent_brain = self._agent_brains.get(agent.name)

        try:
            final_text, tokens = await self._run_cognition_loop(task, agent)
            validation = await self._validator.validate(task.prompt, final_text)
            if not validation.valid:
                logger.warning("Output invalid: %s", validation.issues)
            reflection = await self._reflection.reflect(task.prompt, final_text)
            if not reflection.satisfactory:
                logger.info("Reflection suggested improvements: %s", reflection.improvements)
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

    async def _run_cognition_loop(self, task: Task, agent: AgentCard) -> tuple[str, int]:
        assert self._llm is not None and self._tools is not None and self._context is not None
        retrieved = await self._memory.semantic_recall(task.prompt) if self._memory else []
        if self._memory is not None:
            try:
                for ep in self._memory.episodic.recall(task.prompt, k=3):
                    if ep.lesson:
                        retrieved.append({"content": f"[past lesson] goal: {ep.goal} | lesson: {ep.lesson}", "score": 0.6})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Episodic recall failed (skipped): %s", exc)
        messages = await self._context.build(task=task, history=self._history, retrieved=retrieved)
        tool_specs = self._tools.available_specs()
        total_tokens = 0
        final_text = ""
        tool_outputs: list[str] = []

        for _ in range(_MAX_TOOL_ITERATIONS):
            resp = await self._llm.complete(messages, tools=tool_specs if tool_specs else None)
            total_tokens += 1
            if resp.has_tool_calls:
                for call in resp.tool_calls:
                    args = self._parse_args(call.get("arguments", "{}"))
                    result = await self._tools.run(call["name"], args, agent=agent)
                    messages.append(ChatMessage(role="tool", content=json.dumps(result.to_dict(), default=str)))
                    self._history.append(Message.tool_result(str(result.output), tool=call["name"]))
                    out = str(result.output)
                    if 12 < len(out) < 600:
                        tool_outputs.append(out)
                continue
            final_text = resp.content
            self._history.append(Message.assistant(final_text))
            break
        else:
            final_text = "(model did not produce a final answer within iteration budget)"
        self._last_tool_outputs = tool_outputs
        return final_text, total_tokens

    async def quick_reply(self, prompt: str, *, max_tokens: int = 320, temperature: float = 0.7) -> str:
        if self._llm is None:
            await self.setup()
        if self._llm is None:
            return "MOON is not ready to reply yet."
        persona = self._system_persona()
        messages = [ChatMessage(role="system", content=persona), ChatMessage(role="user", content=prompt)]
        try:
            resp = await self._llm.complete(messages, max_tokens=max_tokens, temperature=temperature)
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

    async def refine(self, prompt: str) -> str:
        """Used by AgentBrain two-phase validation."""
        if self._llm is None:
            return ""
        try:
            resp = await self._llm.complete([ChatMessage(role="user", content=prompt)], max_tokens=400)
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
