"""Launch dbt with any Python, including the portable one (no dbt.exe on the PATH needed)."""
import sys

from dbt.cli.main import cli

if __name__ == "__main__":
    sys.exit(cli())
