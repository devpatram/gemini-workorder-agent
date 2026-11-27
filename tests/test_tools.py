"""The tools against the made-up history. No Google Cloud, no model: these run anywhere."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tools", ROOT / "workorder_agent" / "tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


@pytest.fixture(autouse=True)
def csv_source(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "csv")


def test_history_shape():
    orders = tools.load_orders()
    assert len(orders) == 50
    assert {o["type"] for o in orders} == {"breakdown", "planned"}
    assert len({o["order_id"] for o in orders}) == 50


def test_list_assets_counts_every_order():
    assets = tools.list_assets()["assets"]
    assert len(assets) == 6
    assert sum(a["orders"] for a in assets) == 50
    assert assets[0] == {"asset": "Crimper 1", "orders": 11}


def test_find_work_orders_newest_first_and_filtered():
    found = tools.find_work_orders("crimper 1", "breakdown")
    assert found["status"] == "ok" and found["asset"] == "Crimper 1"
    assert len(found["orders"]) == 7
    dates = [o["date"] for o in found["orders"]]
    assert dates == sorted(dates, reverse=True)


def test_failure_summary_ranks_the_repeat_component():
    summary = tools.failure_summary("Crimper 1")
    top = summary["by_component"][0]
    assert summary["breakdowns"] == 7
    assert top["component"] == "hydraulic hose"
    assert top["count"] == 6
    assert top["cost_usd"] == 2157.5
    assert top["labor_hours"] == 16.5
    assert len(top["orders"]) == 6


def test_unknown_asset_is_not_found_not_guessed():
    assert tools.find_work_orders("Boiler 7")["status"] == "not_found"
    assert tools.failure_summary("Boiler 7")["status"] == "not_found"


def test_partial_name_matching_two_assets_is_ambiguous():
    found = tools.find_work_orders("Extruder")
    assert found["status"] == "ambiguous"
    assert found["candidates"] == ["Extruder 1", "Extruder 2"]


def test_bad_order_type_is_an_error():
    assert tools.find_work_orders("Crimper 1", "emergency")["status"] == "error"


def test_breakdown_intervals():
    result = tools.breakdown_intervals("Crimper 1")
    assert result["status"] == "ok"
    assert len(result["intervals_days"]) == result["breakdowns"] - 1
    assert result["mean_days"] == round(sum(result["intervals_days"]) / len(result["intervals_days"]), 1)
    assert all(d >= 0 for d in result["intervals_days"])


def test_every_tool_has_a_docstring_the_model_can_read():
    for fn in tools.TOOLS:
        assert fn.__doc__ and "Returns:" in fn.__doc__, fn.__name__


def test_bigquery_rows_give_the_same_answers(monkeypatch):
    """BigQuery returns typed values (DATE, FLOAT64); the tools must read them the same as the CSV strings."""
    import csv
    import sys
    import types
    from datetime import date

    with open(tools.DATA_FILE, newline="", encoding="utf-8") as f:
        typed = [{**r, "date": date.fromisoformat(r["date"]), "labor_hours": float(r["labor_hours"]),
                  "cost_usd": float(r["cost_usd"])} for r in csv.DictReader(f)]
    queries = []

    class FakeClient:
        def __init__(self, project=None):
            self.project = project

        def query(self, sql):
            queries.append(sql)
            return types.SimpleNamespace(result=lambda: typed)

    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    bigquery = types.ModuleType("google.cloud.bigquery")
    bigquery.Client = FakeClient
    google.cloud, cloud.bigquery = cloud, bigquery
    for name, module in (("google", google), ("google.cloud", cloud), ("google.cloud.bigquery", bigquery)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("DATA_SOURCE", "bigquery")
    monkeypatch.setenv("BQ_TABLE", "demo.work_orders")

    top = tools.failure_summary("Crimper 1")["by_component"][0]
    assert (top["component"], top["count"], top["cost_usd"], top["labor_hours"]) == ("hydraulic hose", 6, 2157.5, 16.5)
    assert tools.breakdown_intervals("Crimper 1")["mean_days"] == 50.5
    assert "`demo.work_orders`" in queries[0]


def test_instruction_keeps_tool_names_out_of_answers():
    """A deployed test run told a planner to "use list_assets". The instruction must tell the model not to do that."""
    source = (ROOT / "workorder_agent" / "agent.py").read_text(encoding="utf-8")
    assert "Never mention tool or function names to the user" in source
