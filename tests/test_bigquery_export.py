"""The cloud export: fictional data only, one Parquet file per table, types kept."""
import importlib.util
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("load_to_bigquery", ROOT / "scripts" / "load_to_bigquery.py")
lbq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lbq)


def test_export_writes_one_parquet_per_table_with_types(tmp_path):
    lbq.build_demo(tmp_path / "demo.duckdb")
    files = lbq.export_parquet(tmp_path / "demo.duckdb", tmp_path)
    assert sorted(files) == sorted(lbq.TABLES)
    con = duckdb.connect()
    types = dict(con.execute(
        f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM '{files['fact_campaign_stats'].as_posix()}')"
    ).fetchall())
    assert types["campaign_id"] == "BIGINT" and types["snapshot_date"] == "DATE"
    rows = con.execute(f"SELECT COUNT(*) FROM '{files['dim_campaign'].as_posix()}'").fetchone()[0]
    assert rows == 60


def test_only_fictional_data_can_leave():
    """No argument, no path to the real warehouse: the script builds its own demo."""
    source = (ROOT / "scripts" / "load_to_bigquery.py").read_text(encoding="utf-8")
    assert "warehouse.duckdb" not in source and "sys.argv" not in source
    assert "load_settings" not in source and "BREVO_API_KEY" not in source


def test_main_needs_a_project(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    assert lbq.main() == 2
