"""Personal access codes for the attack lab, each with its own run and spending limits.

    DATABASE_URL=<the lab's database> python -m idt_redteam.lab_codes create "Prof. Smith" --runs 5 --budget 0.50
    DATABASE_URL=... python -m idt_redteam.lab_codes list
    DATABASE_URL=... python -m idt_redteam.lab_codes revoke 3

Reuses IDT Prep Copilot's access codes (idt_copilot.api.codes): only a fingerprint of each code is stored,
and the code itself is printed once, when it is created.
"""
from __future__ import annotations

import argparse
import os

import psycopg
from psycopg.rows import dict_row

from idt_copilot.api import codes


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("label")
    c.add_argument("--runs", type=int, default=5)
    c.add_argument("--budget", type=float, default=0.50, help="spending limit in dollars")
    c.add_argument("--days", type=int, default=14, help="expires after this many days (0 for never)")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("id", type=int)
    args = ap.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL to the lab's database.")
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        if args.cmd == "create":
            code, record = codes.create_code(conn, args.label, args.runs, args.budget, args.days or None)
            print(f"{code}  ({record['label']}: {record['max_runs']} runs, ${record['max_cost_usd']:.2f}"
                  f"{', expires ' + record['expires_at'][:10] if record['expires_at'] else ''})")
            print("Copy it now; it is not stored and won't be shown again.")
        elif args.cmd == "list":
            for row in codes.list_codes(conn):
                print(f"{row['id']:>4}  {row['state']:<8} {row['label']:<30} {row['runs_used']}/{row['max_runs']} runs  "
                      f"${row['cost_used_usd']:.2f}/${row['max_cost_usd']:.2f}")
        else:
            print("Turned off." if codes.revoke_code(conn, args.id) else "No code with that id.")


if __name__ == "__main__":
    main()
