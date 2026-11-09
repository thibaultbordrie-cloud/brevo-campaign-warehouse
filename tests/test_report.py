from datetime import date

from brevo_warehouse.ingest import connect, load_campaigns
from brevo_warehouse.report import build_report
from test_ingest import campaigns


def test_report_contains_every_query_and_survives_a_broken_one(tmp_path):
    (tmp_path / "01_ok.sql").write_text("-- Count campaigns\nSELECT COUNT(*) AS n FROM dim_campaign;", encoding="utf-8")
    (tmp_path / "02_broken.sql").write_text("-- Broken on purpose\nSELECT * FROM missing_table;", encoding="utf-8")
    con = connect(":memory:")
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 21))
    text = build_report(con, tmp_path)
    assert "=== 01_ok.sql ===" in text and "Count campaigns" in text
    assert "=== 02_broken.sql ===" in text and "[ERROR]" in text
