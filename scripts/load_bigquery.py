"""Loads workorder_agent/data/work_orders.csv into BigQuery so the agent can read it with DATA_SOURCE=bigquery.

Creates the dataset if it is missing and replaces the table each run (the CSV is the source of truth).
Usage:  python3 scripts/load_bigquery.py                  uses BQ_TABLE from workorder_agent/.env
        python3 scripts/load_bigquery.py dataset.table    or name the table yourself
Needs:  gcloud auth application-default login, and the BigQuery API enabled in the project.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "workorder_agent" / "data" / "work_orders.csv"
ENV = ROOT / "workorder_agent" / ".env"
LOCATION = os.getenv("BQ_LOCATION", "US")

# Typed columns, so dates and numbers are real DATE and FLOAT64 values in the table.
SCHEMA = [
    ("order_id", "STRING"), ("asset", "STRING"), ("component", "STRING"), ("date", "DATE"),
    ("type", "STRING"), ("description", "STRING"), ("labor_hours", "FLOAT64"), ("cost_usd", "FLOAT64"),
]


def setting(key: str, default: str = "") -> str:
    value = os.getenv(key, "")
    if not value and ENV.exists():
        m = re.search(rf"^{key}=(.+)$", ENV.read_text(), re.M)
        value = m.group(1).strip() if m else ""
    return value or default


def main() -> int:
    from google.cloud import bigquery

    project = setting("GOOGLE_CLOUD_PROJECT")
    if not project or project == "your-project-id":
        project = subprocess.run(["gcloud", "config", "get-value", "project"],
                                 capture_output=True, text=True).stdout.strip()
    if not project:
        print("No project set. Run: gcloud config set project YOUR_PROJECT_ID")
        return 1
    table = sys.argv[1] if len(sys.argv) > 1 else setting("BQ_TABLE", "workorders.work_orders")
    if table.count(".") != 1:
        print(f"Give the table as dataset.table, not '{table}'.")
        return 1
    dataset = table.split(".")[0]

    client = bigquery.Client(project=project)
    ds = bigquery.Dataset(f"{project}.{dataset}")
    ds.location = LOCATION
    client.create_dataset(ds, exists_ok=True)

    job_config = bigquery.LoadJobConfig(
        schema=[bigquery.SchemaField(name, kind) for name, kind in SCHEMA],
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with open(CSV, "rb") as f:
        job = client.load_table_from_file(f, f"{project}.{table}", job_config=job_config)
    job.result()
    loaded = client.get_table(f"{project}.{table}")
    print(f"Loaded {loaded.num_rows} rows into {project}.{table} ({LOCATION}).")
    print("Now set DATA_SOURCE=bigquery in workorder_agent/.env and restart adk web.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
