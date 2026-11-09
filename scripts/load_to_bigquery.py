"""Copy the FICTIONAL demo warehouse into BigQuery (bloc 5, cloud).

Only fictional data leaves the company: this script always builds its own demo warehouse
and has no option to read the real one. It is meant to run in GitHub Actions, which signs
in to Google without any stored key (Workload Identity Federation, see docs/CLOUD.md).

    GCP_PROJECT_ID=my-project python scripts/load_to_bigquery.py

Load jobs are free in BigQuery (only queries and storage count), and the sandbox has no
billing account at all: nothing here can create a bill.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["dim_campaign", "fact_campaign_stats", "dim_list", "fact_list_size"]
RAW_DATASET = "brevo_raw"
LOCATION = "EU"


def build_demo(path: Path) -> None:
    spec = importlib.util.spec_from_file_location("make_demo_db", ROOT / "scripts" / "make_demo_db.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    demo.main(str(path))


def export_parquet(db_path: Path, out_dir: Path) -> dict[str, Path]:
    """One Parquet file per table: keeps the column types (INT64, DATE, TIMESTAMP)."""
    con = duckdb.connect(str(db_path), read_only=True)
    files = {}
    try:
        for table in TABLES:
            target = out_dir / f"{table}.parquet"
            con.execute(f"COPY (SELECT * FROM {table}) TO '{target.as_posix()}' (FORMAT parquet)")
            files[table] = target
    finally:
        con.close()
    return files


def load(client, project: str, files: dict[str, Path]) -> dict[str, int]:
    """Create the raw dataset if needed and replace each table with its Parquet file."""
    from google.cloud import bigquery
    dataset = bigquery.Dataset(f"{project}.{RAW_DATASET}")
    dataset.location = LOCATION
    dataset.description = "brevo-warehouse: FICTIONAL demo data loaded by CI"
    client.create_dataset(dataset, exists_ok=True)
    config = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,
                                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    counts = {}
    for table, path in files.items():
        with open(path, "rb") as f:
            job = client.load_table_from_file(f, f"{project}.{RAW_DATASET}.{table}",
                                              job_config=config, location=LOCATION)
        job.result()
        counts[table] = client.get_table(f"{project}.{RAW_DATASET}.{table}").num_rows
        print(f"{RAW_DATASET}.{table}: {counts[table]} rows")
    return counts


def main() -> int:
    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        print("GCP_PROJECT_ID is not set.", file=sys.stderr)
        return 2
    from google.cloud import bigquery
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        build_demo(tmp / "demo.duckdb")
        files = export_parquet(tmp / "demo.duckdb", tmp)
        load(bigquery.Client(project=project, location=LOCATION), project, files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
