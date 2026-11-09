"""Build a demo warehouse filled with FICTIONAL campaigns and lists (no real data).

Used by continuous integration to run dbt on GitHub's servers, and by anyone who wants to
try the project without a Brevo account.  Usage: python scripts/make_demo_db.py [path]
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brevo_warehouse.ingest import connect, load_campaigns, load_lists  # noqa: E402

NAMES = ["Newsletter Wednesday {n}", "Newsletter Friday {n}", "LOCAL_EVENT_STORE_{n}",
         "2026_{n:02d}_STORE_B", "Fermeture magasin C {n}", "Survey {n}"]


def fake_campaigns(rng: random.Random, day: int) -> list[dict]:
    campaigns = []
    for i in range(60):
        delivered = rng.randint(2_000, 600_000)
        opens = int(delivered * rng.uniform(0.05, 0.20))
        clickers = int(opens * rng.uniform(0.01, 0.12)) + day * 3  # clicks keep arriving
        campaigns.append({
            "id": 1000 + i,
            "name": NAMES[i % len(NAMES)].format(n=i),
            "subject": f"Fictional subject {i}" + (" -20%" if i % 4 == 0 else ""),
            "type": "classic",
            "tag": "NL",
            "status": "sent",
            "sentDate": f"2026-{1 + i % 10:02d}-{1 + i % 27:02d}T10:00:00.000+02:00",
            "statistics": {"globalStats": {
                "sent": delivered + rng.randint(10, 500), "delivered": delivered,
                "uniqueViews": opens, "trackableViews": opens, "appleMppOpens": opens * 2,
                "clickers": clickers, "uniqueClicks": clickers,
                "unsubscriptions": int(delivered * rng.uniform(0.0005, 0.004)),
                "hardBounces": rng.randint(0, 50), "softBounces": rng.randint(0, 500),
                "complaints": rng.randint(0, 20),
            }},
        })
    return campaigns


def fake_lists(day: int) -> list[dict]:
    return [{"id": 10 + i, "name": f"Fictional list {i}", "folderId": 1,
             "totalSubscribers": 50_000 * (i + 1) - day * 40 * (i + 1),
             "uniqueSubscribers": 49_000 * (i + 1), "totalBlacklisted": 900 * (i + 1) + day * 15}
            for i in range(5)]


def main(path: str = "data/demo.duckdb") -> None:
    Path(path).unlink(missing_ok=True)
    con = connect(path)
    first_day = date(2026, 10, 19)
    for day in range(3):  # three daily snapshots, so growth and history can be tested
        rng = random.Random(42)  # same campaigns every day, only some counters move
        snapshot = first_day + timedelta(days=day)
        load_campaigns(con, fake_campaigns(rng, day), snapshot=snapshot)
        load_lists(con, fake_lists(day), snapshot=snapshot)
    con.close()
    print(f"Demo warehouse with fictional data written to {path}")


if __name__ == "__main__":
    main(*sys.argv[1:])
