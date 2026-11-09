"""Dagster orchestration of the warehouse: load, transform with dbt, check, alert.

Graph of assets (what Dagster shows in its interface):

    brevo/dim_campaign, brevo/fact_campaign_stats,      loaded from Brevo (or fictional data)
    brevo/dim_list, brevo/fact_list_size
            |
            v
    stg_* -> int_* -> mart_*                             dbt models, one asset each
                                                         dbt tests run with each model
    + freshness check: today's photo must be there
    + daily schedule 09:30 (Paris), + email and desktop file if a run fails

Modes (environment variable WAREHOUSE_SOURCE):
    demo   (default)  fictional data, no key needed: CI and home computer
    brevo             real Brevo API, key from the Windows Credential Manager

Run it:
    dagster dev -f orchestration/definitions.py            interface on http://localhost:3000
    dagster asset materialize -f orchestration/definitions.py --select "*"
"""

import os
import sys
from datetime import date
from pathlib import Path

import duckdb
from dagster import (AssetCheckResult, AssetCheckSeverity, AssetExecutionContext, AssetKey,
                     AssetSpec, DefaultScheduleStatus, Definitions, RunFailureSensorContext,
                     ScheduleDefinition, asset_check, define_asset_job, multi_asset,
                     run_failure_sensor)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SOURCE = os.environ.get("WAREHOUSE_SOURCE", "demo").strip().lower()
DEFAULT_DB = ROOT / "data" / ("demo.duckdb" if SOURCE == "demo" else "warehouse.duckdb")
DB_PATH = Path(os.environ.get("WAREHOUSE_DB", DEFAULT_DB)).resolve()
os.environ["WAREHOUSE_DB"] = str(DB_PATH)   # dbt reads the same file, whatever its working folder

RAW_TABLES = ["dim_campaign", "fact_campaign_stats", "dim_list", "fact_list_size"]


def reference_day() -> date:
    """'Today' for the freshness check. The fictional data stops on 21/10/2026 (CI sets it)."""
    forced = os.environ.get("WAREHOUSE_TODAY", "").strip()
    return date.fromisoformat(forced) if forced else date.today()


# ---------- 1. Load ----------------------------------------------------------------------
@multi_asset(
    specs=[AssetSpec(AssetKey(["brevo", t]), group_name="load",
                     description=f"Table {t}, loaded by the Python ingestion") for t in RAW_TABLES],
    name="load_brevo",
    description="Read Brevo (or build fictional data) and load the four ingestion tables.",
)
def load_brevo(context: AssetExecutionContext):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOURCE == "demo":
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_demo_db", ROOT / "scripts" / "make_demo_db.py")
        demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo)
        demo.main(str(DB_PATH))
        context.log.info(f"Fictional warehouse built: {DB_PATH}")
    else:
        from brevo_warehouse.client import BrevoClient
        from brevo_warehouse.config import load_settings
        from brevo_warehouse.ingest import connect, load_campaigns, load_lists
        settings = load_settings()
        client = BrevoClient(settings.api_key, settings.base_url, settings.verify_ssl, settings.timeout)
        con = connect(DB_PATH)
        n = load_campaigns(con, client.iter_email_campaigns())
        m = load_lists(con, client.iter_contact_lists())
        con.close()
        context.log.info(f"Loaded {n} campaigns and {m} lists into {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for t in RAW_TABLES:
            rows = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            context.log.info(f"{t}: {rows} rows")
    finally:
        con.close()
    return None


@asset_check(asset=AssetKey(["brevo", "fact_campaign_stats"]), blocking=True,
             description="Today's photo of the campaigns must be in the warehouse.")
def todays_photo_is_there() -> AssetCheckResult:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        last = con.execute("SELECT MAX(snapshot_date) FROM fact_campaign_stats").fetchone()[0]
    finally:
        con.close()
    today = reference_day()
    return AssetCheckResult(
        passed=last is not None and last >= today,
        severity=AssetCheckSeverity.ERROR,
        metadata={"last_photo": str(last), "expected": str(today)},
    )


# ---------- 2. Transform with dbt ---------------------------------------------------------
DBT = DbtProject(project_dir=ROOT / "transform", profiles_dir=ROOT / "transform")
DBT.prepare_if_dev()   # `dagster dev` parses the dbt project; in CI, `dbt parse` runs first


@dbt_assets(manifest=DBT.manifest_path)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    """Each dbt model becomes an asset; `dbt build` also runs its tests."""
    yield from dbt.cli(["build"], context=context).stream()


# ---------- 3. Schedule and alert ---------------------------------------------------------
daily_job = define_asset_job("daily_warehouse", selection="*")

daily_schedule = ScheduleDefinition(
    job=daily_job, cron_schedule="30 9 * * *", execution_timezone="Europe/Paris",
    default_status=DefaultScheduleStatus.STOPPED,   # switched on by hand in the interface
)


@run_failure_sensor(monitored_jobs=[daily_job], name="alert_on_failure")
def alert_on_failure(context: RunFailureSensorContext):
    """Same alert as the Windows task: email to the owner + file on the desktop."""
    from brevo_warehouse.__main__ import main as cli
    error = context.failure_event.message or "unknown error"
    cli(["alerts", "--failure", f"Run Dagster {context.dagster_run.run_id[:8]} en échec : {error[:300]}"])


defs = Definitions(
    assets=[load_brevo, dbt_models],
    asset_checks=[todays_photo_is_there],
    jobs=[daily_job],
    schedules=[daily_schedule],
    sensors=[alert_on_failure],
    resources={"dbt": DbtCliResource(project_dir=DBT)},
)
