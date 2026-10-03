"""test_enhanced_memory.py -- Tests for the enhanced memory system."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.memory.enhanced_long_term import EnhancedLongTermMemory
from app.memory.enhanced_short_term import EnhancedShortTermMemory
from app.memory.memory_graph import MemoryGraph
from app.memory.memory_stats import MemoryStatsCollector
from app.memory.memory_maintenance import MemoryMaintenance
from app.brain.memory_manager import MemoryManager


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def ltm(temp_dir):
    return EnhancedLongTermMemory(path=str(temp_dir / "ltm.jsonl"))


@pytest.fixture
def stm():
    return EnhancedShortTermMemory(max_items=10, auto_promote_threshold=0.7)


@pytest.fixture
def graph(temp_dir):
    return MemoryGraph(persist_path=str(temp_dir / "graph.json"))


@pytest.fixture
def stats():
    return MemoryStatsCollector()


@pytest.fixture
def maintenance(ltm, stm, graph, stats):
    return MemoryMaintenance(
        ltm=ltm,
        stm=stm,
        graph=graph,
        stats_collector=stats,
        decay_interval=9999,
        promotion_interval=9999,
        expiry_interval=9999,
        stats_interval=9999,
    )


@pytest.fixture
def manager(ltm, stm, graph, stats, maintenance):
    return MemoryManager(
        short_term=stm,
        long_term=ltm,
        memory_graph=graph,
        stats_collector=stats,
        maintenance=maintenance,
    )


# === Enhanced LTM Tests ===

class TestEnhancedLTM:
    @pytest.mark.asyncio
    async def test_store_and_query(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "MOON is a cyber agent", "tags": ["agent"]}, importance=0.9)
        await ltm.store({"content": "Python is great", "tags": ["lang"]}, importance=0.5)
        results = await ltm.query("MOON")
        assert len(results) == 1
        assert results[0].content == "MOON is a cyber agent"

    @pytest.mark.asyncio
    async def test_importance_scoring(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "critical fact"}, importance=1.0)
        await ltm.store({"content": "trivial fact"}, importance=0.1)
        results = await ltm.query("fact", limit=2)
        assert results[0].importance >= results[1].importance

    @pytest.mark.asyncio
    async def test_decay(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "old fact"}, importance=0.5)
        # Manually set last_accessed to 2 days ago to trigger decay
        for e in ltm._entries.values():
            import time
            e.last_accessed = time.time() - 2 * 86400
        decayed = await ltm.decay()
        assert decayed == 1
        results = await ltm.query("old fact")
        assert results[0].importance < 0.5

    @pytest.mark.asyncio
    async def test_persistence(self, temp_dir):
        path = str(temp_dir / "ltm.jsonl")
        ltm1 = EnhancedLongTermMemory(path=path)
        await ltm1.setup()
        await ltm1.store({"content": "persistent fact"}, importance=0.8)
        del ltm1

        ltm2 = EnhancedLongTermMemory(path=path)
        await ltm2.setup()
        results = await ltm2.query("persistent")
        assert len(results) == 1
        assert results[0].content == "persistent fact"

    @pytest.mark.asyncio
    async def test_stats(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "fact one"}, importance=0.8)
        await ltm.store({"content": "fact two"}, importance=0.4)
        s = ltm.stats()
        assert s["total"] == 2
        assert "avg_importance" in s

    @pytest.mark.asyncio
    async def test_tag_filtering(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "cyber fact"}, importance=0.8, tags=["security"])
        await ltm.store({"content": "python fact"}, importance=0.8, tags=["programming"])
        results = await ltm.query("fact", tags=["security"])
        assert len(results) == 1
        assert "cyber" in results[0].content

    @pytest.mark.asyncio
    async def test_access_tracking(self, ltm):
        await ltm.setup()
        await ltm.store({"content": "tracked fact"}, importance=0.5)
        # Query multiple times to increase access count
        await ltm.query("tracked")
        await ltm.query("tracked")
        await ltm.query("tracked")
        results = await ltm.query("tracked")
        assert results[0].access_count >= 3


# === Enhanced STM Tests ===

class TestEnhancedSTM:
    @pytest.mark.asyncio
    async def test_add_and_search(self, stm):
        stm.add("hello world")
        stm.add("goodbye world")
        results = stm.search("world")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_relevance_boost(self, stm):
        stm.add("test item", relevance=0.5)
        # Access it multiple times to boost relevance
        stm.search("test")
        stm.search("test")
        s = stm.stats()
        assert s["total"] == 1

    @pytest.mark.asyncio
    async def test_max_items(self):
        stm = EnhancedShortTermMemory(max_items=3)
        stm.add("one")
        stm.add("two")
        stm.add("three")
        stm.add("four")
        assert len(stm) == 3
        recent = stm.recent(n=10)
        assert "one" not in recent

    @pytest.mark.asyncio
    async def test_promote_callback(self):
        promoted = []
        def on_promote(content, relevance):
            promoted.append((content, relevance))
        stm = EnhancedShortTermMemory(max_items=10, auto_promote_threshold=0.7, promote_callback=on_promote)
        stm.add("important fact", relevance=0.9)
        assert len(promoted) == 1
        assert promoted[0][0] == "important fact"

    @pytest.mark.asyncio
    async def test_stats(self, stm):
        stm.add("fact one", relevance=0.8)
        stm.add("fact two", relevance=0.4)
        s = stm.stats()
        assert s["total"] == 2
        assert "avg_relevance" in s


# === Memory Graph Tests ===

class TestMemoryGraph:
    @pytest.mark.asyncio
    async def test_add_and_link(self, graph):
        await graph.setup()
        node1 = await graph.add_memory("MOON is an agent", memory_type="ltm")
        node2 = await graph.add_memory("MOON uses Python", memory_type="ltm")
        await graph.link_co_occurring(node1.id, node2.id)
        # Verify both nodes exist
        s = graph.stats()
        assert s["nodes"] == 2

    @pytest.mark.asyncio
    async def test_search(self, graph):
        await graph.setup()
        await graph.add_memory("cyber security facts")
        await graph.add_memory("python programming")
        results = await graph.search("cyber")
        assert len(results) == 1
        assert "cyber" in results[0].lower()

    @pytest.mark.asyncio
    async def test_stats(self, graph):
        await graph.setup()
        await graph.add_memory("fact one")
        await graph.add_memory("fact two")
        s = graph.stats()
        assert s["nodes"] == 2
        assert "edges" in s

    @pytest.mark.asyncio
    async def test_persistence(self, temp_dir):
        path = str(temp_dir / "graph.json")
        g1 = MemoryGraph(persist_path=path)
        await g1.setup()
        await g1.add_memory("persistent node")
        del g1

        g2 = MemoryGraph(persist_path=path)
        await g2.setup()
        s = g2.stats()
        assert s["nodes"] == 1


# === Memory Stats Tests ===

class TestMemoryStats:
    @pytest.mark.asyncio
    async def test_record_and_get(self, stats):
        stats.record_store("ltm")
        stats.record_recall("test", 3)
        # Stats are collected on-demand via collect()
        s = stats.get_stats()
        # Empty before collect() is called
        assert s == {}

    @pytest.mark.asyncio
    async def test_collect(self, ltm, stm, graph, stats):
        await ltm.setup()
        await ltm.store({"content": "fact"}, importance=0.7)
        stm.add("recent fact")
        await graph.add_memory("graph fact")
        snapshot = await stats.collect(ltm=ltm, stm=stm, graph=graph)
        d = snapshot.to_dict()
        assert d["ltm"]["total"] == 1
        assert d["stm"]["total"] == 1
        assert d["graph"]["nodes"] == 1

    @pytest.mark.asyncio
    async def test_get_stats_after_collect(self, ltm, stm, graph, stats):
        await ltm.setup()
        await ltm.store({"content": "fact"}, importance=0.7)
        await stats.collect(ltm=ltm, stm=stm, graph=graph)
        s = stats.get_stats()
        assert s["ltm"]["total"] == 1


# === Memory Maintenance Tests ===

class TestMemoryMaintenance:
    @pytest.mark.asyncio
    async def test_run_once(self, maintenance, ltm, stm):
        await ltm.setup()
        await ltm.store({"content": "decaying fact"}, importance=0.5)
        stm.add("promoting fact", relevance=0.9)
        results = await maintenance.run_once()
        assert "ltm_decayed" in results
        assert "stm_promoted" in results

    @pytest.mark.asyncio
    async def test_start_stop(self, maintenance):
        await maintenance.start()
        assert maintenance._running
        await maintenance.stop()
        assert not maintenance._running


# === Memory Manager Integration Tests ===

class TestMemoryManager:
    @pytest.mark.asyncio
    async def test_remember_and_recall(self, manager):
        await manager.setup()
        await manager.remember("MOON is a cyber agent", long_term=True, importance=0.9)
        results = await manager.recall("MOON")
        assert len(results) >= 1
        assert any("MOON" in r for r in results)

    @pytest.mark.asyncio
    async def test_learn(self, manager):
        await manager.setup()
        await manager.learn("Python is a programming language", importance=0.8)
        results = await manager.recall("Python")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_unified_search(self, manager):
        await manager.setup()
        await manager.remember("cyber security is important", long_term=True)
        await manager.remember("python is versatile", long_term=True)
        results = await manager.unified_search("cyber")
        assert "long_term" in results
        assert len(results["long_term"]) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        await manager.setup()
        await manager.remember("fact one", long_term=True)
        await manager.remember("fact two", long_term=True)
        s = await manager.get_stats()
        assert "long_term" in s
        assert "short_term" in s
        assert "episodic" in s
        assert "graph" in s

    @pytest.mark.asyncio
    async def test_run_maintenance(self, manager):
        await manager.setup()
        await manager.remember("decaying fact", long_term=True, importance=0.5)
        results = await manager.run_maintenance()
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_backward_compat(self, temp_dir):
        """Test that MemoryManager works with base classes too."""
        from app.memory.short_term import ShortTermMemory
        from app.memory.long_term import LongTermMemory

        ltm = LongTermMemory(path=str(temp_dir / "ltm.jsonl"))
        stm = ShortTermMemory()
        mgr = MemoryManager(short_term=stm, long_term=ltm)
        await mgr.setup()
        await mgr.remember("base class fact", long_term=True)
        results = await mgr.recall("base")
        assert len(results) >= 1
