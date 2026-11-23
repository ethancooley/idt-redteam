"""Build the open benchmark: one JSONL file of poisoned-chart overlays per attack.

    python -m idt_redteam.benchmark                 # writes benchmark/*.jsonl and benchmark/manifest.json
    python -m idt_redteam.benchmark --flood-notes 90

The clean cohort and answer keys are read from the pinned IDT Prep Copilot checkout (see scripts/setup.sh)
and are never modified. Each line of benchmark/<attack>.jsonl is an AttackCase: the notes to add to one
participant's chart, and the label that says what the attack targets and how to recognize success.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

from idt_copilot.db.load import load_cohort
from idt_copilot.models import AnswerKey, Participant

from idt_redteam.attacks import (
    ATTACKS, DEFAULT_FLOOD_NOTES, DEFAULT_SEED, OMISSION_ATTACKS, AttackCase, build_case,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = ROOT / "benchmark"


def upstream_dir() -> Path:
    """Where the IDT Prep Copilot checkout lives (its data/cohort and data/golden are the clean data)."""
    return Path(os.environ.get("IDT_UPSTREAM_DIR", ROOT / "vendor" / "idt-prep-copilot"))


def load_clean(upstream: Path | None = None) -> tuple[dict[str, Participant], dict[str, AnswerKey]]:
    up = upstream or upstream_dir()
    cohort_dir, golden_dir = up / "data" / "cohort", up / "data" / "golden"
    if not cohort_dir.is_dir():
        raise FileNotFoundError(f"No clean cohort at {cohort_dir}. Run scripts/setup.sh or set IDT_UPSTREAM_DIR.")
    cohort = {p.id: p for p in load_cohort(cohort_dir)}
    keys = {k.participant_id: k for k in
            (AnswerKey.model_validate_json(f.read_text()) for f in sorted(golden_dir.glob("*.json")))}
    if set(cohort) != set(keys):
        raise ValueError("cohort and answer keys do not cover the same participants")
    return cohort, keys


def generate(cohort: dict[str, Participant], keys: dict[str, AnswerKey], attacks: list[str] | None = None,
             seed: int = DEFAULT_SEED, flood_notes: int = DEFAULT_FLOOD_NOTES) -> dict[str, list[AttackCase]]:
    out: dict[str, list[AttackCase]] = {}
    for attack in attacks or ATTACKS:
        cases = []
        for pid in sorted(cohort):
            case = build_case(attack, cohort[pid], keys[pid], keys=keys, cohort=cohort, seed=seed,
                              flood_notes=flood_notes)
            if case is not None:
                cases.append(case)
        out[attack] = cases
    return out


def write(cases: dict[str, list[AttackCase]], out_dir: Path, manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for attack, items in cases.items():
        (out_dir / f"{attack}.jsonl").write_text("".join(c.model_dump_json() + "\n" for c in items))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def read(attack: str, bench_dir: Path = BENCHMARK_DIR) -> list[AttackCase]:
    path = bench_dir / f"{attack}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Build it with: python -m idt_redteam.benchmark")
    return [AttackCase.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def _upstream_commit(up: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=BENCHMARK_DIR)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--flood-notes", type=int, default=DEFAULT_FLOOD_NOTES)
    ap.add_argument("--attacks", nargs="+", choices=ATTACKS)
    args = ap.parse_args(argv)

    up = upstream_dir()
    cohort, keys = load_clean(up)
    cases = generate(cohort, keys, args.attacks, args.seed, args.flood_notes)
    omission = next((c for a, c in cases.items() if a in OMISSION_ATTACKS), [])
    targets = Counter(c.target_id for c in omission)
    manifest = {
        "description": "Poisoned-chart overlays for red-teaming IDT Prep Copilot. All data is synthetic.",
        "upstream": "https://github.com/ethancooley/idt-prep-copilot",
        "upstream_commit": _upstream_commit(up),
        "seed": args.seed,
        "flood_notes": args.flood_notes,
        "participants": len(cohort),
        "cases": {a: len(c) for a, c in cases.items()},
        "omission_targets": dict(sorted(targets.items())),
    }
    write(cases, args.out_dir, manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
