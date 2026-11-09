"""Load Brevo campaigns and contact lists into DuckDB. Idempotent: running twice the same day changes nothing."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

STAT_FIELDS = {
    "sent": "sent", "delivered": "delivered", "unique_views": "uniqueViews",
    "trackable_views": "trackableViews", "apple_mpp_opens": "appleMppOpens",
    "unique_clicks": "uniqueClicks", "clickers": "clickers",
    "unsubscriptions": "unsubscriptions", "hard_bounces": "hardBounces",
    "soft_bounces": "softBounces", "complaints": "complaints",
}


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    return con


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _date_key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _upsert_date(con: duckdb.DuckDBPyConnection, d: date) -> int:
    key = _date_key(d)
    iso = d.isocalendar()
    con.execute(
        "INSERT INTO dim_date VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (date_key) DO NOTHING",
        [key, d, d.year, d.month, d.day, iso[1], iso[2]],
    )
    return key


def load_campaigns(con: duckdb.DuckDBPyConnection, campaigns: Iterable[dict[str, Any]],
                   snapshot: date | None = None) -> int:
    """Write campaigns into raw, dim and fact tables. Returns the number of campaigns loaded."""
    snapshot = snapshot or datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    count = 0
    con.execute("BEGIN")
    try:
        for c in campaigns:
            cid = int(c["id"])
            created = _ts(c.get("createdAt"))
            sent_at = _ts(c.get("sentDate") or c.get("scheduledAt"))
            con.execute("INSERT INTO raw_email_campaigns VALUES (?, ?, ?)",
                        [cid, now, json.dumps(c, ensure_ascii=False)])
            con.execute(
                """INSERT INTO dim_campaign VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (campaign_id) DO UPDATE SET
                     name = excluded.name, subject = excluded.subject,
                     campaign_type = excluded.campaign_type, tag = excluded.tag,
                     status = excluded.status, created_at = excluded.created_at,
                     sent_at = excluded.sent_at""",
                [cid, c.get("name"), c.get("subject"), c.get("type"), c.get("tag"),
                 c.get("status"),
                 created.replace(tzinfo=None) if created else None,
                 sent_at.replace(tzinfo=None) if sent_at else None],
            )
            send_key = _upsert_date(con, sent_at.date()) if sent_at else None
            stats = ((c.get("statistics") or {}).get("globalStats")) or {}
            values = [int(stats.get(api, 0) or 0) for api in STAT_FIELDS.values()]
            cols = ", ".join(STAT_FIELDS)
            updates = ", ".join(f"{k} = excluded.{k}" for k in STAT_FIELDS)
            con.execute(
                f"""INSERT INTO fact_campaign_stats (campaign_id, snapshot_date, send_date_key, {cols})
                    VALUES (?, ?, ?, {', '.join('?' * len(STAT_FIELDS))})
                    ON CONFLICT (campaign_id, snapshot_date) DO UPDATE SET
                      send_date_key = excluded.send_date_key, {updates}""",
                [cid, snapshot, send_key, *values],
            )
            count += 1
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return count


def load_lists(con: duckdb.DuckDBPyConnection, lists: Iterable[dict[str, Any]],
               snapshot: date | None = None) -> int:
    """Write contact lists into dim_list and fact_list_size. Returns the number of lists loaded."""
    snapshot = snapshot or datetime.now(timezone.utc).date()
    count = 0
    con.execute("BEGIN")
    try:
        for item in lists:
            lid = int(item["id"])
            folder = item.get("folderId")
            con.execute(
                """INSERT INTO dim_list VALUES (?, ?, ?)
                   ON CONFLICT (list_id) DO UPDATE SET
                     name = excluded.name, folder_id = excluded.folder_id""",
                [lid, item.get("name"), int(folder) if folder is not None else None],
            )
            con.execute(
                """INSERT INTO fact_list_size VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (list_id, snapshot_date) DO UPDATE SET
                     total_subscribers = excluded.total_subscribers,
                     unique_subscribers = excluded.unique_subscribers,
                     total_blacklisted = excluded.total_blacklisted""",
                [lid, snapshot,
                 int(item.get("totalSubscribers") or 0),
                 int(item.get("uniqueSubscribers") or 0),
                 int(item.get("totalBlacklisted") or 0)],
            )
            count += 1
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return count
