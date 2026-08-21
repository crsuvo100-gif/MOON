"""Auto-generated tests for gen_convert_csv_to_json (spec 43)."""

from gen_convert_csv_to_json import create_agent


def test_create_agent():
    a = create_agent()
    assert a.name == 'convert_csv_to_json'
    assert hasattr(a, "run")


def test_run_returns_structured_result():
    a = create_agent()
    res = a.run("process sample task with numbers 2 and 3")
    assert isinstance(res, dict)
    assert res["success"] is True
    assert "result" in res and res["result"]
    assert res["agent_id"] == 'convert_csv_to_json'
    assert res["execution_id"]
