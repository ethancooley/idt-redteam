"""The whole pipeline, end to end, against a scripted stand-in for Claude (no API key needed).

The stand-in (tests/scripted.py) believes planted 'wrong participant' corrections, so the harness must
report those attacks as successes.
"""
from __future__ import annotations

import json

from idt_redteam import harness

from scripted import GullibleClaude


def test_dry_run_prints_a_plan_and_spends_nothing(capsys, attack_db):
    assert harness.main(["--dry-run", "--limit", "2", "--attacks", "fake_authority"]) == 0
    out = capsys.readouterr().out
    assert "4 briefs" in out and "Estimated cost" in out


def test_end_to_end_run_scores_a_gullible_agent(tmp_path, attack_db):
    code = harness.main(["--limit", "2", "--attacks", "fake_authority", "backdating", "--runs-dir", str(tmp_path),
                         "--concurrency", "1"], make_client=GullibleClaude)
    assert code == 0
    run = next(tmp_path.iterdir())
    results = json.loads((run / "results.json").read_text())["baseline"]
    # It misses the flu-vaccine gap (no note proves it) but catches every high-severity event.
    assert results["clean"]["summary"]["high_severity_recall"] == 1.0
    fa = results["fake_authority"]["summary"]
    assert fa["cases"] == 2 and fa["attack_success_rate"] == 1.0 and fa["suppressed"] == 1.0
    assert results["backdating"]["summary"]["cases"] == 2
    assert (run / "report.md").read_text().startswith("# Red-team report")
    # Re-scoring the saved briefs gives the same answer for free.
    assert harness.main(["--rescore", str(run)]) == 0
    assert json.loads((run / "results.json").read_text())["baseline"]["fake_authority"]["summary"] == fa


def test_every_defense_runs_end_to_end_and_the_detector_stops_the_gullible_agent(tmp_path, attack_db):
    defenses = ["baseline", "no_verifier", "spotlight", "conflict_rule", "quotes", "detector"]
    code = harness.main(["--limit", "2", "--attacks", "fake_authority", "--defenses", *defenses,
                         "--runs-dir", str(tmp_path), "--concurrency", "1"], make_client=GullibleClaude)
    assert code == 0
    run = next(tmp_path.iterdir())
    results = json.loads((run / "results.json").read_text())
    assert set(results) == set(defenses)
    assert results["baseline"]["fake_authority"]["summary"]["attack_success_rate"] == 1.0
    det = results["detector"]["fake_authority"]["summary"]
    assert det["detector_caught"] == 1.0 and det["attack_success_rate"] == 0.0
    assert results["detector"]["clean"]["summary"]["detector_flagged_notes"] == 0
    assert "## Defenses compared" in (run / "report.md").read_text()
