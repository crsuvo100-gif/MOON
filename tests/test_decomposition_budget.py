"""Tests for spec 5 (MainBrain decomposition) and spec 49 (context budget)."""

from __future__ import annotations

from app.brain.orchestrator import Orchestrator
from app.config.settings import get_settings
from app.models.task import Task


def _orch() -> Orchestrator:
    return Orchestrator(get_settings())


# ------------------------------------------------------------------- spec 5
def test_decomposes_spec_worked_example() -> None:
    """The spec's own example must decompose into its distinct steps."""
    o = _orch()
    subs = o._split_subtasks(
        "Inspect my project, find the bug, fix it, test it, and explain the changes.")
    assert len(subs) >= 3
    joined = " ".join(subs).lower()
    for verb in ("inspect", "find", "fix", "test"):
        assert verb in joined


def test_explicit_separators_still_work() -> None:
    o = _orch()
    assert len(o._split_subtasks("do a and also do b")) == 2
    assert len(o._split_subtasks("first thing; second thing")) == 2
    assert len(o._split_subtasks("1. alpha\n2. beta\n3. gamma")) == 3


def test_single_domain_request_is_not_decomposed() -> None:
    """A plain question must NOT be chopped into subtasks."""
    o = _orch()
    assert o._split_subtasks("What is 2+2?") == ["What is 2+2?"]
    assert o._split_subtasks("Explain quantum entanglement") == \
        ["Explain quantum entanglement"]
    assert o._is_composite_goal("What is the capital of France?") is False


def test_composite_goal_detected() -> None:
    o = _orch()
    assert o._is_composite_goal("Inspect the repo, find the bug, fix it and test it")
    assert o._is_composite_goal("analyze the logs; summarize the findings")


def test_subtasks_capped_by_max_parallel_agents() -> None:
    o = _orch()
    many = ", ".join(f"test item {i}" for i in range(30))
    assert len(o._split_subtasks(many)) <= o._settings.max_parallel_agents


# ------------------------------------------------------------------ spec 49
class _Msg:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def test_token_estimate_is_sane() -> None:
    o = _orch()
    assert o._estimate_tokens("") == 0
    assert o._estimate_tokens("abcd") == 1
    assert o._estimate_tokens("x" * 400) == 100


def test_budget_no_eviction_when_within_window() -> None:
    o = _orch()
    msgs = [_Msg("system", "sys"), _Msg("user", "hi")]
    out, rep = o._enforce_context_budget(msgs, Task(prompt="hi"))
    assert out == msgs
    assert rep["evicted"] == 0 and rep["summarized"] is False


def test_budget_evicts_and_summarizes_when_over() -> None:
    """A prompt far over the window must be evicted + summarized, not passed on."""
    o = _orch()
    o._settings.context_max_tokens = 800
    o._settings.model_max_tokens = 200
    big = "word " * 5000          # ~6250 estimated tokens
    msgs = [
        _Msg("system", "you are moon"),
        _Msg("user", "old context 1 " + big),
        _Msg("user", "old context 2 " + big),
        _Msg("user", "recent " + big),
        _Msg("user", "the actual question"),
    ]
    task = Task(prompt="the actual question")
    out, rep = o._enforce_context_budget(msgs, task)
    assert rep["evicted"] >= 1
    assert rep["after"] <= rep["budget"] or rep["after"] < rep["before"]
    assert rep["summarized"] is True
    # the system prompt and the final user turn must survive
    assert out[0].content == "you are moon"
    assert out[-1].content == "the actual question"
    # and the report is attached to the task for observability
    assert task.data["_context_budget"]["evicted"] == rep["evicted"]


def test_budget_report_attached_even_when_fits() -> None:
    o = _orch()
    task = Task(prompt="q")
    o._enforce_context_budget([_Msg("system", "s"), _Msg("user", "q")], task)
    assert "_context_budget" in task.data
