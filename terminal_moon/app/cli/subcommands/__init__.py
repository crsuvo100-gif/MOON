"""
MOON Terminal CLI subcommands — model, status, doctor, setup.
"""
from __future__ import annotations

import argparse

from app.config.settings import get_settings


def build(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("model", help="Show model configuration")
    p.set_defaults(func=cmd_model)

    p = subparsers.add_parser("status", help="Show runtime status")
    p.set_defaults(func=cmd_status)

    p = subparsers.add_parser("doctor", help="Run health diagnostics")
    p.set_defaults(func=cmd_doctor)

    p = subparsers.add_parser("setup", help="First-run setup wizard")
    p.set_defaults(func=cmd_setup)


def cmd_model(args: argparse.Namespace) -> None:
    s = get_settings()
    print(f"model_name:      {s.model_name}")
    print(f"model_base_url:  {s.model_base_url}")
    print(f"model_temperature: {s.model_temperature}")
    print(f"model_max_tokens:  {s.model_max_tokens}")
    print(f"model_timeout:     {s.model_timeout}s")
    print()
    print(f"strong_model:   {s.strong_model_name or '(none)'}")
    print(f"openai:         {s.openai_model if s.openai_api_key else '(no key)'}")
    print(f"openrouter:     {s.openrouter_model if s.openrouter_api_key else '(no key)'}")
    print(f"huggingface:    {s.huggingface_model if s.huggingface_api_key else '(no key)'}")


def cmd_status(args: argparse.Namespace) -> None:
    s = get_settings()
    print(f"model:        {s.model_name}")
    print(f"agent:        coordinator")
    print(f"session:      main")
    print(f"base URL:     {s.model_base_url}")
    print(f"timeout:      {s.model_timeout}s")
    print(f"voice:        {'on' if s.voice_enabled else 'off'}")
    print(f"fast_path:    {s.enable_fast_path}")
    print(f"self_cons:    {s.enable_self_consistency} (n={s.self_consistency_samples})")
    print(f"agent_val:    {s.enable_agent_validation}")


def cmd_doctor(args: argparse.Namespace) -> None:
    s = get_settings()
    print("╔══════════════════════════════════════╗")
    print("║  MOON TERMINAL — DOCTOR             ║")
    print("╠══════════════════════════════════════╣")

    checks = []

    # config
    try:
        _ = s.model_name
        checks.append(("config", "PASS", "settings loaded"))
    except Exception as e:
        checks.append(("config", "FAIL", str(e)))

    # llm client
    try:
        from app.services.llm_service import LLMService, ChatMessage
        llm = LLMService(base_url=s.model_base_url, model_name=s.model_name,
                          api_key="not-required" if "127.0.0.1" in s.model_base_url else "",
                          timeout=min(s.model_timeout, 5.0))
        checks.append(("llm_client", "PASS", f"{s.model_name} @ {s.model_base_url}"))
    except Exception as e:
        checks.append(("llm_client", "WARN", str(e)))

    # tools registry
    try:
        from app.tools.registry import registry
        n = len(registry.tool_names)
        checks.append(("tools", "PASS", f"{n} tools registered"))
    except Exception as e:
        checks.append(("tools", "FAIL", str(e)))

    # memory
    try:
        from app.memory.short_term import ShortTermMemory
        from app.memory.long_term import LongTermMemory
        from app.memory.episodic_memory import EpisodicMemory
        from app.memory.vector_db import InMemoryVectorStore
        _ = ShortTermMemory()
        _ = LongTermMemory(s.long_term_path)
        _ = EpisodicMemory(s.episodes_path)
        _ = InMemoryVectorStore()
        checks.append(("memory", "PASS", "all subsystems instantiable"))
    except Exception as e:
        checks.append(("memory", "FAIL", str(e)))

    # voice engine
    try:
        from app.voice_engine import VoiceEngine
        ve = VoiceEngine(s)
        st = ve.backend_status()
        available = [k for k, v in st.items() if v and k in ("kokoro", "f5", "xtts", "openai", "espeak")]
        checks.append(("voice", "PASS", f"backends: {', '.join(available) or 'none'}"))
    except Exception as e:
        checks.append(("voice", "WARN", str(e)))

    # orchestrator
    try:
        from app.brain.orchestrator import Orchestrator
        checks.append(("orchestrator", "PASS", "class importable"))
    except Exception as e:
        checks.append(("orchestrator", "FAIL", str(e)))

    # lock
    try:
        from app.brain.lock import SessionLock
        _ = SessionLock()
        checks.append(("session_lock", "PASS", "locked-at-start"))
    except Exception as e:
        checks.append(("session_lock", "FAIL", str(e)))

    for name, state, detail in checks:
        icon = "✓" if state == "PASS" else "✗" if state == "FAIL" else "⚠"
        print(f"║  {icon} {name:<14} {state:<8} {detail:<22} ║")
    print("╚══════════════════════════════════════╝")


def cmd_setup(args: argparse.Namespace) -> None:
    print("""
╔══════════════════════════════════════╗
║  MOON TERMINAL — SETUP              ║
╠══════════════════════════════════════╣
║  First-run setup wizard.            ║
║  Edit .env manually for now.        ║
║                                     ║
║  Required:                           ║
║    - Ollama running on :11434       ║
║    - At least one model pulled      ║
║                                     ║
║  Optional:                           ║
║    - OpenAI/OpenRouter/HF keys      ║
║    - espeak-ng (TTS fallback)       ║
║    - Kokoro-ONNX (premium voice)    ║
╚══════════════════════════════════════╝
""")
