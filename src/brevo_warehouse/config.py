"""Configuration read from environment variables or a local .env file.

No secret is ever stored in the code. Keys live in the Windows Credential Manager
(python run.py secret set BREVO_API_KEY); the .env file only holds non-secret settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    db_path: Path
    verify_ssl: bool | str  # True, False, or path to a CA bundle
    timeout: int = 60


def load_settings(env_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or PROJECT_ROOT / ".env")
    from .vault import fill_env
    fill_env()   # keys from the Windows Credential Manager, when not set elsewhere
    api_key = os.environ.get("BREVO_API_KEY", "")
    ca_bundle = os.environ.get("BREVO_CA_BUNDLE", "").strip()
    verify_flag = os.environ.get("BREVO_VERIFY_SSL", "true").strip().lower()
    verify: bool | str
    if ca_bundle:
        verify = ca_bundle
    else:
        verify = verify_flag not in ("0", "false", "no")
    db_path = Path(os.environ.get("WAREHOUSE_DB", PROJECT_ROOT / "data" / "warehouse.duckdb"))
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("BREVO_BASE_URL", "https://api.brevo.com/v3").rstrip("/"),
        db_path=db_path,
        verify_ssl=verify,
    )
