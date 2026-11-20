"""The agent's tools: plain Python functions over a maintenance work-order history.

They hold all of the logic and none of the model, so they can be tested without Google Cloud (see tests/).
The data is made up: 50 work orders for 6 assets on a fictional production line, Nov 2025 to Oct 2026.

Where the rows come from:
  DATA_SOURCE=csv       (default) data/work_orders.csv next to this file
  DATA_SOURCE=bigquery  the table named in BQ_TABLE, in the project GOOGLE_CLOUD_PROJECT
"""
from __future__ import annotations

import csv
import os
from collections import Counter
from datetime import date
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "work_orders.csv"
ORDER_TYPES = ("breakdown", "planned")


def load_orders() -> list[dict]:
    """All work orders as dicts of strings, from the CSV file or from BigQuery."""
    if os.getenv("DATA_SOURCE", "csv").lower() == "bigquery":
        from google.cloud import bigquery  # imported only when used

        table = os.getenv("BQ_TABLE", "workorders.work_orders")
        client = bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
        # The table name comes from configuration, not from the user or the model.
        rows = client.query(f"SELECT * FROM `{table}` ORDER BY date").result()
        return [{k: str(v) for k, v in dict(r).items()} for r in rows]
    with open(DATA_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _match(asset: str, orders: list[dict]) -> list[dict]:
    key = " ".join(asset.split()).lower()
    if not key:
        return []
    exact = [o for o in orders if o["asset"].lower() == key]
    return exact or [o for o in orders if key in o["asset"].lower()]


def list_assets() -> dict:
    """Lists every asset that has work orders, with how many orders each has.

    Returns:
        dict: {"assets": [{"asset": name, "orders": count}, ...]}, most orders first.
    """
    counts = Counter(o["asset"] for o in load_orders())
    return {"assets": [{"asset": a, "orders": n} for a, n in counts.most_common()]}


def find_work_orders(asset: str, order_type: str = "any") -> dict:
    """Finds the work orders for one asset, newest first.

    Args:
        asset: The asset name, for example "Crimper 1" or "Extruder 2". Case is ignored and a partial name works
            when it matches exactly one asset.
        order_type: "breakdown", "planned" or "any".

    Returns:
        dict: {"status": "ok", "asset": ..., "orders": [...]}, {"status": "not_found", "message": ...} or
        {"status": "ambiguous", "candidates": [...]} when a partial name matches several assets.
    """
    if order_type not in ORDER_TYPES + ("any",):
        return {"status": "error", "message": f"order_type must be breakdown, planned or any, not '{order_type}'."}
    hits = _match(asset, load_orders())
    names = sorted({o["asset"] for o in hits})
    if len(names) > 1:
        return {"status": "ambiguous", "message": f"'{asset}' matches several assets; ask which one.",
                "candidates": names}
    if order_type != "any":
        hits = [o for o in hits if o["type"] == order_type]
    if not hits:
        return {"status": "not_found",
                "message": f"No {'' if order_type == 'any' else order_type + ' '}work orders found for '{asset}'. "
                           "Use list_assets to see the names."}
    hits.sort(key=lambda o: o["date"], reverse=True)
    return {"status": "ok", "asset": hits[0]["asset"], "orders": hits}


def failure_summary(asset: str) -> dict:
    """Summarizes breakdowns on one asset: which component fails most, how often, labor hours and cost.

    Args:
        asset: The asset name, for example "Cooling Pump P3".

    Returns:
        dict: {"status": "ok", "asset": ..., "breakdowns": n, "by_component": [...]} or the find_work_orders status.
    """
    found = find_work_orders(asset, "breakdown")
    if found["status"] != "ok":
        return found
    by: dict[str, dict] = {}
    for o in found["orders"]:
        c = by.setdefault(o["component"], {"component": o["component"], "count": 0, "labor_hours": 0.0,
                                           "cost_usd": 0.0, "orders": []})
        c["count"] += 1
        c["labor_hours"] += float(o["labor_hours"])
        c["cost_usd"] += float(o["cost_usd"])
        c["orders"].append(o["order_id"])
    ranked = sorted(by.values(), key=lambda c: (-c["count"], -c["cost_usd"]))
    for c in ranked:
        c["labor_hours"] = round(c["labor_hours"], 1)
        c["cost_usd"] = round(c["cost_usd"], 2)
    return {"status": "ok", "asset": found["asset"], "breakdowns": len(found["orders"]), "by_component": ranked}


def breakdown_intervals(asset: str) -> dict:
    """Days between consecutive breakdowns on one asset, and their average.

    A rough mean time between failures from the order dates only. It is not a reliability model: it ignores
    run hours, censoring and which component failed. Use it to say "about every N days", not to plan PMs.

    Args:
        asset: The asset name.

    Returns:
        dict: {"status": "ok", "asset": ..., "breakdowns": n, "intervals_days": [...], "mean_days": x,
        "last_breakdown": date} or the find_work_orders status. mean_days is None with fewer than two breakdowns.
    """
    found = find_work_orders(asset, "breakdown")
    if found["status"] != "ok":
        return found
    days = sorted(date.fromisoformat(o["date"]) for o in found["orders"])
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    return {"status": "ok", "asset": found["asset"], "breakdowns": len(days), "intervals_days": gaps,
            "mean_days": round(sum(gaps) / len(gaps), 1) if gaps else None, "last_breakdown": days[-1].isoformat(),
            "note": "Calendar days between breakdown orders; not adjusted for run time."}


TOOLS = [list_assets, find_work_orders, failure_summary, breakdown_intervals]
