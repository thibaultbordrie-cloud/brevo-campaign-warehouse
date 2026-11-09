from datetime import date

from brevo_warehouse.ingest import connect, load_lists
from conftest import fixture
from test_client import FakeResponse, make


def lists():
    return fixture("lists_page1.json")["lists"] + fixture("lists_page2.json")["lists"]


def test_list_pagination_reads_every_page():
    client, s = make([FakeResponse(200, fixture("lists_page1.json")),
                      FakeResponse(200, fixture("lists_page2.json"))])
    assert [item["id"] for item in client.iter_contact_lists(page_size=2)] == [11, 12, 13]
    assert [c["offset"] for c in s.calls] == [0, 2]


def test_load_lists_and_missing_counts_become_zero():
    con = connect(":memory:")
    assert load_lists(con, lists(), snapshot=date(2026, 10, 21)) == 3
    assert con.execute("SELECT COUNT(*) FROM dim_list").fetchone()[0] == 3
    row = con.execute("SELECT total_subscribers, total_blacklisted FROM fact_list_size WHERE list_id = 13").fetchone()
    assert row == (0, 0)


def test_same_day_reload_is_idempotent():
    con = connect(":memory:")
    load_lists(con, lists(), snapshot=date(2026, 10, 21))
    load_lists(con, lists(), snapshot=date(2026, 10, 21))
    assert con.execute("SELECT COUNT(*) FROM fact_list_size").fetchone()[0] == 3


def test_growth_is_computed_between_two_days():
    con = connect(":memory:")
    load_lists(con, lists(), snapshot=date(2026, 10, 21))
    next_day = [dict(item) for item in lists()]
    next_day[0]["totalSubscribers"] = 1180      # lost 20 contacts
    next_day[0]["totalBlacklisted"] = 55        # 15 more blacklisted
    load_lists(con, next_day, snapshot=date(2026, 10, 22))
    rows = con.execute("SELECT snapshot_date, change_subscribers, change_blacklisted FROM v_list_growth "
                   "WHERE list_id = 11 ORDER BY snapshot_date").fetchall()
    assert rows == [(date(2026, 10, 21), None, None), (date(2026, 10, 22), -20, 15)]


def test_subscribers_fall_back_to_unique_when_brevo_total_is_zero():
    """Seen with the Brevo API: totalSubscribers can be 0 on every list while uniqueSubscribers is filled."""
    from brevo_warehouse.alerts import check_list_drops
    con = connect(":memory:")
    day1 = [{"id": 1, "name": "Newsletter", "folderId": 1, "totalSubscribers": 0,
             "uniqueSubscribers": 10_000, "totalBlacklisted": 5}]
    day2 = [dict(day1[0], uniqueSubscribers=9_500)]               # -5 %: must alert
    load_lists(con, day1, snapshot=date(2026, 10, 21))
    load_lists(con, day2, snapshot=date(2026, 10, 22))
    assert con.execute("SELECT subscribers FROM v_list_size ORDER BY snapshot_date").fetchall() == [(10_000,), (9_500,)]
    assert con.execute("SELECT change_subscribers FROM v_list_growth WHERE snapshot_date = DATE '2026-10-22'"
                       ).fetchone() == (-500,)
    assert len(check_list_drops(con, date(2026, 10, 22))) == 1
