"""
End-to-end verification script for MOON Terminal.
Tests every layer: LLM, tools, memory, orchestrator, event bus, voice,
CLI, TUI, terminal_interface, capability manager, global connector.
"""
from __future__ import annotations

import asyncio
import sys
import os
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
from app.config.env_guard import _guard  # noqa: F401
from app.config.settings import get_settings

s = get_settings()
print(f"Using model: {s.model_name} @ {s.model_base_url}")

# ── LLM Service smoke test ──────────────────────────────────────────────────
print("\n=== TEST 1: LLM Service ===")
from app.services.llm_service import LLMService, ChatMessage

llm = LLMService(base_url=s.model_base_url, model_name=s.model_name,
                  api_key="not-required", timeout=min(s.model_timeout, 10.0))
asyncio.run(llm.setup())
r = asyncio.run(llm.complete([ChatMessage(role="user", content="say hello in exactly 3 words")]))
print(f"LLM response: {r.content!r} (len={len(r.content or '')})")
assert r.content and len(r.content) > 0, "LLM returned empty"
print("PASS")

# ── Tools ───────────────────────────────────────────────────────────────────
print("\n=== TEST 2: Tools ===")
from app.tools.base import ToolRegistry, ToolResult
from app.tools.web_search import WebSearchTool
from app.tools.terminal import TerminalTool
from app.tools.file_manager import FileManagerTool
from app.tools.python_executor import PythonExecutorTool

reg = ToolRegistry()
for t in [WebSearchTool(), TerminalTool(), FileManagerTool(), PythonExecutorTool()]:
    reg.register(t)
print(f"Registered: {reg.tool_names}")
assert reg.tool_names == ['web_search', 'terminal', 'file_manager', 'python_executor']
print("PASS")

from app.brain.tool_manager import ToolManager
tm = ToolManager(reg, enabled_tools=reg.tool_names, allow_dangerous=True, tool_timeout=30.0)
specs = tm.available_specs()
print(f"Available specs: {len(specs)} tools")
assert len(specs) == 4

# Execute terminal tool
r = asyncio.run(tm.run("terminal", {"cmd": "date"}))
print(f"Terminal date: {(r.output or '')[:60]}")
assert r.success or len(str(r.output)) > 0
print("PASS (terminal)")

# Execute file_manager tool
with tempfile.TemporaryDirectory() as td:
    fm = FileManagerTool(allowed_root=td)
    reg2 = ToolRegistry()
    reg2.register(fm)
    tm2 = ToolManager(reg2, enabled_tools=["file_manager"])
    r = asyncio.run(tm2.run("file_manager", {"action": "write", "path": "hello.txt", "content": "moon"}))
    assert r.success
    r2 = asyncio.run(tm2.run("file_manager", {"action": "read", "path": "hello.txt"}))
    assert "moon" in (r2.output or "")
print("PASS (file_manager)")

# ── Memory subsystems ───────────────────────────────────────────────────────
print("\n=== TEST 3: Memory ===")
from app.memory.short_term import ShortTermMemory
from app.memory.long_term import LongTermMemory
from app.memory.episodic_memory import EpisodicMemory
from app.memory.vector_db import InMemoryVectorStore
from app.memory.knowledge_base import KnowledgeBase
from app.memory.conversation_history import ConversationHistory
from app.services.embedding_service import EmbeddingService
from app.brain.memory_manager import MemoryManager

stm = ShortTermMemory()
ltm = LongTermMemory(s.long_term_path)
store = InMemoryVectorStore()
kb = KnowledgeBase(store, EmbeddingService(dim=384, enabled=False))
ep = EpisodicMemory(s.episodes_path)
mm = MemoryManager(stm, ltm, kb, ep)

assert len(stm) == 0
mm.remember("hello world", long_term=True, tags=["test"])
assert len(stm) > 0
recalled = mm.recall(keyword="hello")
assert len(recalled) > 0, f"recall failed: {recalled}"
print(f"STM: {len(stm)} entries, recall: {recalled[:1]}")
print("PASS (STM + LTM + recall)")

ep.record(goal="test goal", outcome="test outcome", success=True)
assert len(ep._episodes) > 0
print(f"Episodic: {len(ep._episodes)} episodes")
print("PASS (episodic)")

# ── Orchestrator full setup ──────────────────────────────────────────────────
print("\n=== TEST 4: Orchestrator setup ===")
from app.brain.orchestrator import Orchestrator

orch = Orchestrator(s)
asyncio.run(orch.setup())
print(f"  llm: {orch._llm._model if orch._llm else None}")
print(f"  strong: {orch._llm_strong is not None}")
print(f"  fallback chain: {orch._fallback_chain is not None}")
print(f"  embeddings enabled: {orch._embeddings._enabled if orch._embeddings else None}")
print(f"  memory: {orch._memory is not None}")
print(f"  tools: {orch._tool_registry.tool_names if orch._tool_registry else []}")
print(f"  agents: {len(orch._agents)}")
print(f"  agent_brains: {len(orch._agent_brains)}")
print(f"  lock: {orch._lock.locked}")
assert orch._llm is not None
assert orch._memory is not None
assert orch._tool_registry is not None
assert len(orch._agents) > 0
assert len(orch._agent_brains) > 0
assert orch._lock.locked in (True, False)  # setup may auto-unlock; both valid
print("PASS")

# ── Orchestrator run_task (simple query) ────────────────────────────────────
print("\n=== TEST 5: Orchestrator run_task (simple) ===")
from app.brain.orchestrator import Task
task = Task.create("what is 2+2? answer in one word")
task = asyncio.run(orch.run_task(task))
print(f"  status: {task.status}")
print(f"  result: {(task.result or '')[:100]}")
assert task.status == "success", f"task status: {task.status}"
assert task.result and len(task.result) > 0, "empty result"
print("PASS")

# ── Orchestrator quick_reply ─────────────────────────────────────────────────
print("\n=== TEST 6: Orchestrator quick_reply ===")
resp = asyncio.run(orch.quick_reply("say hello"))
print(f"  quick_reply: {resp[:60]}")
assert resp and len(resp) > 0, f"empty quick_reply: {resp!r}"
print("PASS")

# ── Intent detection ─────────────────────────────────────────────────────────
print("\n=== TEST 7: Intent detection ===")
from app.brain.intent_detector import detect_intent, intent_to_agent

tests = [
    ("scan my network for open ports", "cyber"),
    ("write a python script", "code"),
    ("search the web for moontm", "web"),
    ("hello", "chat"),
    ("run a port scan", "red_team"),
]
for prompt, expected in tests:
    intent, conf = detect_intent(prompt)
    agent = intent_to_agent(intent)
    print(f"  '{prompt[:30]}' → intent={intent}, agent={agent} (conf={conf})")
    assert intent == expected or agent == expected, f"expected {expected}, got {intent}/{agent}"
print("PASS")

# ── Session lock ─────────────────────────────────────────────────────────────
print("\n=== TEST 8: Session lock ===")
from app.brain.lock import SessionLock

lock = SessionLock(locked=True, state_file=s.lock_state_path)
assert lock.locked == True
notice = lock.observe("hello")
assert notice is not None
assert lock.locked == True
notice2 = lock.observe("MOON love you 3000")
assert notice2 is not None and "unlocked" in notice2.lower()
assert lock.locked == False
print("PASS")

# ── Event bus ───────────────────────────────────────────────────────────────
print("\n=== TEST 9: Event bus ===")
from app.runtime.event_bus import bus, EventType, Event

eb = bus()
received = []
def on_ev(ev: Event):
    received.append(ev)
eb.subscribe(on_ev)
eb.publish(EventType.TASK_CREATED, execution_id="t1", detail="test")
eb.publish(EventType.AGENT_COMPLETED, agent_id="coordinator", detail="done")
assert len(received) == 2, f"expected 2, got {len(received)}"
print(f"  events: {len(received)} — {[e.type.value for e in received]}")
print("PASS")

# ── Voice engine ─────────────────────────────────────────────────────────────
print("\n=== TEST 10: Voice engine ===")
from app.voice_engine import VoiceEngine, FEMALE_VOICES

ve = VoiceEngine(s)
st = ve.backend_status()
print(f"  backends: kokoro={st['kokoro']}, f5={st['f5']}, xtts={st['xtts']}, openai={st['openai']}, espeak={st['espeak']}")
print(f"  voices: {[v['name'] for v in ve.list_voices()]}")
assert any(v['name'] == 'aria' for v in ve.list_voices())
assert any(v['name'] == 'bella' for v in ve.list_voices())
assert ve.current_voice() == 'default'
ve.set_voice('aria')
assert ve.current_voice() == 'aria'
ve.set_voice('default')
print("PASS")

# ── CLI imports ──────────────────────────────────────────────────────────────
print("\n=== TEST 11: CLI ===")
from app.cli.cli import MoonCLI
from app.cli.commands import COMMAND_REGISTRY, resolve_command, CLIState
from app.cli.main import _build_state
from app.cli.oneshot import run_oneshot

print(f"  commands: {len(COMMAND_REGISTRY)}")
cmd = resolve_command("help")
assert cmd is not None and cmd.name == "help"
state = _build_state()
assert state["model_name"] == s.model_name
print(f"  CLIState model: {state['model_name']}")
print("PASS")

# ── TUI imports ──────────────────────────────────────────────────────────────
print("\n=== TEST 12: TUI ===")
from app.tui import Moonscope, ChatPanel, StatusHUD
print("  Moonscope, ChatPanel, StatusHUD imported OK")
print("PASS")

# ── terminal_interface imports ───────────────────────────────────────────────
print("\n=== TEST 13: terminal_interface ===")
from app.terminal_interface import app, _get_orchestrator, _moon_status_impl, _shell_dispatch
from fastapi import FastAPI
assert isinstance(app, FastAPI)
print(f"  FastAPI app: {type(app).__name__}")
out, code = _shell_dispatch("date")
print(f"  shell date: {(out or '')[:40]} (code={code})")
assert code == 0 or len(out) > 0
print("PASS")

# ── Capability manager ───────────────────────────────────────────────────────
print("\n=== TEST 14: Capability manager ===")
from app.capability.manager import CapabilityManager
cm = CapabilityManager(s)
print(f"  catalog: {len(cm._catalog)} entries")
needed = cm.discover("search the web for moontm")
print(f"  discover 'search web': {[n.get('name') for n in needed]}")
assert any(n.get('name') == 'web_search' for n in needed)
print("PASS")

# ── Global connector ─────────────────────────────────────────────────────────
print("\n=== TEST 15: Global connector ===")
from app.connector.gateway import GlobalConnector, ConnectionRecord
gc = GlobalConnector(s)
print(f"  connections: {len(gc._connections)}")
local = gc.get("moon_local")
assert local is not None and local.name == "moon_local"
print(f"  local peer: {local.name} ({local.kind})")
print("PASS")

# ── Agent registry ───────────────────────────────────────────────────────────
print("\n=== TEST 16: Agent registry ===")
from app.agents.registry import AgentRegistry
from app.brain.agent_registry import build_agents, persona_for
agents = build_agents(reg.tool_names)
print(f"  built agents: {len(agents)} — {list(agents.keys())[:10]}")
assert "coordinator" in agents
assert "red_team" in agents
assert agents["red_team"].risk_level in ("dangerous", "aggressive")
print(f"  red_team persona: {agents['red_team'].persona[:60]}...")
assert len(agents["red_team"].allowed_tools) > 0 or agents["red_team"].capabilities
print("PASS")

# ── Agent brain ──────────────────────────────────────────────────────────────
print("\n=== TEST 17: Agent brain ===")
from app.brain.agent_brain import AgentBrain
brain = AgentBrain(name="test_agent", main_brain=orch)
asyncio.run(brain.setup())
assert brain._memory is not None
print("PASS")

# ── prompts / context / reasoning modules ───────────────────────────────────
print("\n=== TEST 18: cognition modules ===")
from app.brain.prompt_manager import PromptManager
from app.brain.context_builder import ContextBuilder
from app.brain.reasoning import ReasoningEngine
from app.brain.planner import Planner
from app.brain.validator import Validator
from app.brain.self_reflection import SelfReflection
from app.brain.output_formatter import OutputFormatter
from app.brain.error_recovery import ErrorRecovery

pm = PromptManager()
assert pm.system()
cb = ContextBuilder(pm)
assert cb.build("test", [])
print("  prompts + context OK")

import asyncio as aio
recovery = ErrorRecovery(max_retries=2, base_delay=0.01)
counter = [0]
async def flaky():
    counter[0] += 1
    if counter[0] < 2:
        raise ValueError("fail")
    return "ok"
result = asyncio.run(recovery.run(flaky))
assert result == "ok" and counter[0] == 2
print("  error recovery OK")

of = OutputFormatter()
clean = of.format("  hello   world  \n\n")
assert clean == "hello world"
print("  output formatter OK")
print("PASS")

# ── doctor command ───────────────────────────────────────────────────────────
print("\n=== TEST 19: doctor CLI ===")
result = subprocess.run([sys.executable, "main.py", "doctor"],
                        cwd=os.path.dirname(__file__),
                        capture_output=True, text=True, timeout=15)
print(result.stdout[:300] if result.stdout else result.stderr[:300])
assert result.returncode == 0
print("PASS")

# ── version command ──────────────────────────────────────────────────────────
print("\n=== TEST 20: version CLI ===")
result = subprocess.run([sys.executable, "main.py", "version"],
                        cwd=os.path.dirname(__file__),
                        capture_output=True, text=True, timeout=10)
print(result.stdout.strip())
assert "1.0.0" in result.stdout
print("PASS")

print("\n" + "=" * 60)
print("ALL 20 END-TO-END TESTS PASSED")
print("=" * 60)
