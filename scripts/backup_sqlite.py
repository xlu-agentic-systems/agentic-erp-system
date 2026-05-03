#!/usr/bin/env python3
"""Create a SQLite backup for the ERP state database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import erp_state  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up the ERP SQLite database.")
    parser.add_argument("backup_path", help="Destination .sqlite3 backup path")
    parser.add_argument("--db", dest="db_path", help="Source SQLite DB path; defaults to ERP_DB_PATH or data/erp.sqlite3")
    args = parser.parse_args(argv)

    backup_path = erp_state.backup_sqlite(args.backup_path, args.db_path)
    print(backup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
