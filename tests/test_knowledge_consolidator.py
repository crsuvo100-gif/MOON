"""Tests for the autonomous KnowledgeConsolidator (MOON self-learning loop)."""

import asyncio
import json
from pathlib import Path

import pytest

from app.brain.knowledge_consolidator import KnowledgeConsolidator
from app.brain.memory_manager import MemoryManager
from app.memory.long_term import LongTermMemory
from app.memory.short_term import ShortTermMemory
from app.memory.vector_db import InMemoryVectorStore
from app.memory.knowledge_base import KnowledgeBase
from app.services.embedding_service import EmbeddingService


def _build_mm(tmp_path):
    loop = asyncio.new_event_loop()
    try:
        ltm = LongTermMemory(path=str(tmp_path / "ltm.jsonl"))
        loop.run_until_complete(ltm.setup())
        store = InMemoryVectorStore(dim=4)
        emb = EmbeddingService(dim=4, enabled=False)
        loop.run_until_complete(emb.setup())
        kb = KnowledgeBase(store, emb)
        mm = MemoryManager(short_term=ShortTermMemory(), long_term=ltm, knowledge_base=kb)
        loop.run_until_complete(mm.setup())
        return mm, None
    finally:
        loop.close()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_offline_extraction_finds_factual_sentences(tmp_path):
    mm, _ = _build_mm(tmp_path)
    c = KnowledgeConsolidator(mm, use_llm=False)
    facts = _run(c._gather_facts(
        "What is the capital of France?",
        "The capital of France is Paris. The Eiffel Tower was completed in 1889.",
        None, "", True, None,
    ))
    texts = [f[0] for f in facts]
    assert any("Paris" in t for t in texts)
    assert any("1889" in t for t in texts)


def test_consolidate_persists_to_long_term_memory(tmp_path):
    mm, _ = _build_mm(tmp_path)
    c = KnowledgeConsolidator(mm, use_llm=False)
    n = _run(c.consolidate(
        prompt="Tell me about Neptune.",
        response="Neptune is the eighth planet from the Sun. It has 14 known moons.",
    ))
    assert n >= 1
    entries = _run(mm._ltm.all())
    assert any("Neptune" in e.content for e in entries)


def test_consolidate_dedups_repeated_facts(tmp_path):
    mm, _ = _build_mm(tmp_path)
    c = KnowledgeConsolidator(mm, use_llm=False)
    r1 = _run(c.consolidate(prompt="x", response="Water boils at 100 degrees Celsius at sea level."))
    r2 = _run(c.consolidate(prompt="x", response="Water boils at 100 degrees Celsius at sea level."))
    assert r1 >= 1 and r2 == 0


def test_consolidate_never_raises_on_bad_input(tmp_path):
    mm, _ = _build_mm(tmp_path)
    c = KnowledgeConsolidator(mm, use_llm=False)
    # empty / None should not throw
    assert _run(c.consolidate(prompt="", response="")) == 0
    assert _run(c.consolidate(prompt=None, response=None)) == 0
