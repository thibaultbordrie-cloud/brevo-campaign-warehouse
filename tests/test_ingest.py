from datetime import date

from brevo_warehouse.ingest import connect, load_campaigns
from conftest import fixture


def campaigns():
    return fixture("campaigns_page1.json")["campaigns"] + fixture("campaigns_page2.json")["campaigns"]


def test_load_creates_dimensions_and_facts():
    con = connect(":memory:")
    assert load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19)) == 3
    assert con.execute("SELECT COUNT(*) FROM dim_campaign").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM fact_campaign_stats").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0] == 2


def test_same_day_reload_is_idempotent():
    con = connect(":memory:")
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19))
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19))
    assert con.execute("SELECT COUNT(*) FROM fact_campaign_stats").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM dim_campaign").fetchone()[0] == 3


def test_new_day_keeps_history():
    con = connect(":memory:")
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19))
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 20))
    assert con.execute("SELECT COUNT(*) FROM fact_campaign_stats").fetchone()[0] == 6


def test_kpis_follow_the_dictionary():
    con = connect(":memory:")
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19))
    row = con.execute("SELECT open_rate_pct, click_rate_pct, ctor_pct, unsub_rate_pct "
                  "FROM v_campaign_kpis WHERE campaign_id = 901").fetchone()
    assert row == (round(100 * 180 / 980, 2), round(100 * 11 / 980, 2),
                   round(100 * 11 / 180, 2), round(100 * 1 / 980, 3))


def test_campaign_without_stats_gives_no_division_by_zero():
    con = connect(":memory:")
    load_campaigns(con, campaigns(), snapshot=date(2026, 10, 19))
    row = con.execute("SELECT delivered, open_rate_pct FROM v_campaign_kpis WHERE campaign_id = 903").fetchone()
    assert row == (0, None)


def test_scope_rule_is_defined_once_in_the_view():
    con = connect(":memory:")
    sample = [
        {"id": 1, "name": "LOCAL_EVENT_STORE"},
        {"id": 2, "name": "2026_11_04_STORE_A"},
        {"id": 3, "name": "Fermeture magasin B"},
        {"id": 4, "name": "Newsletter mercredi"},
    ]
    load_campaigns(con, sample, snapshot=date(2026, 10, 19))
    rows = dict(con.execute("SELECT campaign_id, scope FROM v_campaign_kpis").fetchall())
    assert rows == {1: "LOCAL", 2: "LOCAL", 3: "LOCAL", 4: "NATIONAL"}
