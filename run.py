"""Launcher that works with any Python, including an embedded/portable one.

Portable Python builds ignore the PYTHONPATH variable, so this file adds
the src folder to the import path itself, then runs the command line.
Usage: python run.py ingest | kpis | init | query FILE.sql
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    import duckdb  # noqa: F401
except ImportError:
    sys.exit("DuckDB is not installed for this Python. Run:\n"
             f'  "{sys.executable}" -m pip install duckdb')

from brevo_warehouse.__main__ import main  # noqa: E402

sys.exit(main())
