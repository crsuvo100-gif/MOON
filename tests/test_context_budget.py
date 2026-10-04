"""Tests for Context Budget Enforcer (spec 49)."""
import pytest

from app.brain.context_budget import (
    ContextBudget,
    ContextBudgetEnforcer,
    get_enforcer,
)


class TestContextBudget:
    def test_within_budget(self):
        b = ContextBudget(
            model_context_limit=8192,
            system_tokens=1000,
            task_tokens=500,
            memory_tokens=500,
            tool_result_tokens=500,
            output_reserve=1024,
        )
        assert b.is_within_budget is True
        assert b.total_used == 3524
        assert b.remaining == 4668

    def test_exceeds_budget(self):
        b = ContextBudget(
            model_context_limit=2000,
            system_tokens=1000,
            task_tokens=500,
            memory_tokens=500,
            tool_result_tokens=500,
            output_reserve=1024,
        )
        assert b.is_within_budget is False
        assert b.remaining < 0

    def test_utilization(self):
        b = ContextBudget(
            model_context_limit=1000,
            system_tokens=250,
            task_tokens=250,
            output_reserve=0,
        )
        assert b.utilization == 0.5

    def test_to_dict(self):
        b = ContextBudget(model_context_limit=8192, system_tokens=100)
        d = b.to_dict()
        assert d["model_context_limit"] == 8192
        assert d["system_tokens"] == 100
        assert d["is_within_budget"] is True


class TestContextBudgetEnforcer:
    @pytest.fixture
    def enforcer(self):
        return ContextBudgetEnforcer()

    def test_estimate_tokens(self, enforcer):
        assert enforcer.estimate_tokens("") == 0
        assert enforcer.estimate_tokens("hello") >= 1
        # ~3.5 chars per token
        text = "a" * 350
        assert abs(enforcer.estimate_tokens(text) - 100) < 5

    def test_build_budget(self, enforcer):
        b = enforcer.build_budget(
            model_context_limit=8192,
            system_prompt="You are a helpful assistant",
            task="Fix the bug",
            memory_items=["memory1", "memory2"],
            tool_results=["result1"],
        )
        assert b.model_context_limit == 8192
        assert b.system_tokens > 0
        assert b.task_tokens > 0
        assert b.memory_tokens > 0
        assert b.tool_result_tokens > 0
        assert b.output_reserve == 1024

    def test_enforce_within_budget(self, enforcer):
        b = enforcer.build_budget(
            model_context_limit=8192,
            system_prompt="You are a helpful assistant",
            task="Fix the bug",
            memory_items=["m1"],
            tool_results=["r1"],
        )
        adjusted, mem, tools, actions = enforcer.enforce(
            b, memory_items=["m1"], tool_results=["r1"]
        )
        assert adjusted.is_within_budget
        assert len(actions) == 0

    def test_enforce_removes_tool_results(self, enforcer):
        # Create a budget that exceeds limits
        big_text = "x" * 10000
        b = enforcer.build_budget(
            model_context_limit=2000,
            system_prompt="sys",
            task="task",
            tool_results=[big_text],
        )
        adjusted, mem, tools, actions = enforcer.enforce(
            b, memory_items=[], tool_results=[big_text]
        )
        assert len(actions) > 0
        assert any("removed_tool_result" in a for a in actions)

    def test_enforce_removes_memory_items(self, enforcer):
        big_mem = "x" * 10000
        b = enforcer.build_budget(
            model_context_limit=2000,
            system_prompt="sys",
            task="task",
            memory_items=[big_mem],
        )
        adjusted, mem, tools, actions = enforcer.enforce(
            b, memory_items=[big_mem], tool_results=[]
        )
        assert len(actions) > 0
        assert any("removed_memory_item" in a for a in actions)

    def test_enforce_compresses_tool_results(self, enforcer):
        # 5 items of 2000 chars = ~571 tokens each = ~2857 total
        # utilization = 2857/3000 = 0.952 (over compression_threshold=0.9)
        # Below max_utilization=0.95? No, 0.952 > 0.95, so removal triggers
        # After removing 1: 2286/3000 = 0.762 (below 0.9, stop)
        # Need items that stay above 0.9 after removal
        # Use 5 items of 1800 chars = ~514 tokens each = ~2571 total
        # utilization = 2571/3000 = 0.857 (below 0.9, no compression)
        # Use 5 items of 1900 chars = ~542 tokens each = ~2714 total
        # utilization = 2714/3000 = 0.905 (over 0.9, compression triggers)
        text = "x" * 1900
        b = enforcer.build_budget(
            model_context_limit=3000,
            system_prompt="sys",
            task="task",
            tool_results=[text, text, text, text, text],
        )
        adjusted, mem, tools, actions = enforcer.enforce(
            b, memory_items=[], tool_results=[text, text, text, text, text]
        )
        # Should have compressed remaining tool results
        assert any("compressed" in a for a in actions)

    def test_can_fit(self, enforcer):
        assert enforcer.can_fit(
            model_context_limit=8192,
            system_prompt="sys",
            task="task",
        ) is True

    def test_cannot_fit(self, enforcer):
        big = "x" * 10000
        assert enforcer.can_fit(
            model_context_limit=1000,
            system_prompt=big,
            task=big,
        ) is False


class TestHelpers:
    def test_get_enforcer_singleton(self):
        e1 = get_enforcer()
        e2 = get_enforcer()
        assert e1 is e2
