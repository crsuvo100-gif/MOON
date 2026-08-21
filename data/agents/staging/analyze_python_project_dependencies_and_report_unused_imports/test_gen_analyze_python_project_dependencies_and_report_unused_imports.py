"""Auto-generated tests for gen_analyze_python_project_dependencies_and_report_unused_imports (spec 43)."""

from gen_analyze_python_project_dependencies_and_report_unused_imports import create_agent


def test_create_agent():
    a = create_agent()
    assert a.name == 'analyze_python_project_dependencies_and_report_unused_imports'
    assert hasattr(a, "run")


def test_run_returns_structured_result():
    a = create_agent()
    res = a.run("process sample task with numbers 2 and 3")
    assert isinstance(res, dict)
    assert res["success"] is True
    assert "result" in res and res["result"]
    assert res["agent_id"] == 'analyze_python_project_dependencies_and_report_unused_imports'
    assert res["execution_id"]
