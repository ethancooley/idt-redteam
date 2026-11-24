"""Load a poisoned cohort into its own Postgres database, never the clean one.

    python -m idt_redteam.loader fake_authority          # whole cohort, attacked charts swapped in
    python -m idt_redteam.loader clean                   # the unpoisoned cohort, for the utility baseline
    python -m idt_redteam.loader fake_authority --embed  # also embed notes, so search_notes is semantic

The attack database holds the whole cohort, not just the attacked charts, as a real chart database
would. Loading replaces everything in the target database, so the loader refuses to touch the clean database.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg

from idt_copilot.db.load import create_schema, embed_notes, insert_participant
from idt_copilot.models import Participant

from idt_redteam.attacks import ATTACKS, AttackCase, poison
from idt_redteam.benchmark import BENCHMARK_DIR, load_clean, read

DEFAULT_ATTACK_DB = "postgresql://idt:idt@localhost:5432/idt_redteam"
CLEAN_DB_NAMES = {"idt"}  # the IDT Prep Copilot database: never overwritten from here


def attack_database_url() -> str:
    return os.environ.get("IDT_REDTEAM_DATABASE_URL", DEFAULT_ATTACK_DB)


def _db_name(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def check_target(url: str) -> None:
    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("The attack database URL must be a postgresql:// connection string.")
    name = _db_name(url)
    clean = os.environ.get("DATABASE_URL")
    if name in CLEAN_DB_NAMES or (clean and _db_name(clean) == name and urlparse(clean).hostname ==
                                  urlparse(url).hostname):
        raise ValueError(f"Refusing to load poisoned charts into {name!r}: that is the clean database. "
                         "Point IDT_REDTEAM_DATABASE_URL at a separate database (default: idt_redteam).")


def poisoned_cohort(cohort: dict[str, Participant], cases: list[AttackCase],
                    only: set[str] | None = None) -> list[Participant]:
    """The full cohort, with the given cases' charts poisoned (optionally only some participants)."""
    by_pid = {c.participant_id: c for c in cases if only is None or c.participant_id in only}
    return [poison(cohort[pid], by_pid.get(pid)) for pid in sorted(cohort)]


def load(attack: str, url: str | None = None, *, cases: list[AttackCase] | None = None,
         only: set[str] | None = None, embed: bool = False, bench_dir: Path = BENCHMARK_DIR,
         upstream: Path | None = None) -> dict:
    url = url or attack_database_url()
    check_target(url)
    cohort, _ = load_clean(upstream)
    if attack == "clean":
        cases = []
    elif cases is None:
        cases = read(attack, bench_dir)
    participants = poisoned_cohort(cohort, cases, only)
    with psycopg.connect(url) as conn:
        create_schema(conn)
        with conn.cursor() as cur:
            for p in participants:
                insert_participant(cur, p)
        conn.commit()
        embedded = embed_notes(conn) if embed else 0
    attacked = {c.participant_id for c in cases if only is None or c.participant_id in only}
    return {"attack": attack, "database": _db_name(url), "participants": len(participants),
            "attacked": len(attacked), "notes": sum(len(p.notes) for p in participants),
            "planted_notes": sum(len(c.poison_notes) for c in cases if c.participant_id in attacked),
            "embedded": embedded}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("attack", choices=[*ATTACKS, "clean"])
    ap.add_argument("--database-url", default=None, help="default: $IDT_REDTEAM_DATABASE_URL or idt_redteam")
    ap.add_argument("--embed", action="store_true", help="embed notes with the local model for semantic search")
    args = ap.parse_args(argv)
    info = load(args.attack, args.database_url, embed=args.embed)
    print(f"Loaded {info['participants']} participants into {info['database']}: {info['attacked']} attacked "
          f"with {args.attack}, {info['planted_notes']} planted notes, {info['notes']} notes in all.")


if __name__ == "__main__":
    main()
