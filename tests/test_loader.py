"""The loader writes poisoned charts to their own database and refuses the clean one."""
from __future__ import annotations

import psycopg
import pytest

from idt_copilot.chart.repository import ChartRepository

from idt_redteam import loader
from idt_redteam.benchmark import read


@pytest.mark.parametrize("url", [
    "postgresql://idt:idt@localhost:5432/idt",
    "mysql://idt:idt@localhost/idt_redteam",
])
def test_refuses_the_clean_database_and_non_postgres_urls(url):
    with pytest.raises(ValueError):
        loader.check_target(url)


def test_refuses_whatever_database_url_points_at(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://idt:idt@localhost:5432/my_clean_copy")
    with pytest.raises(ValueError):
        loader.check_target("postgresql://idt:idt@localhost:5432/my_clean_copy")


def test_loads_the_whole_cohort_with_attacked_charts_swapped_in(attack_db, clean):
    cohort, _ = clean
    cases = read("citation_laundering")
    only = {c.participant_id for c in cases[:3]}
    info = loader.load("citation_laundering", attack_db, cases=cases, only=only)
    assert info["participants"] == len(cohort) and info["attacked"] == 3 and info["planted_notes"] == 6
    repo = ChartRepository(attack_db, use_embeddings=False)
    case = cases[0]
    window_notes = {n["id"] for n in repo.get_notes(case.participant_id)}
    assert set(case.poison_note_ids) <= window_notes
    untouched = cases[5]  # attacked in the benchmark, but not selected for this load
    assert not set(untouched.poison_note_ids) & {n["id"] for n in repo.get_notes(untouched.participant_id)}
    repo.close()


def test_clean_load_has_no_planted_notes(attack_db, clean):
    cohort, _ = clean
    info = loader.load("clean", attack_db)
    assert info["planted_notes"] == 0
    assert info["notes"] == sum(len(p.notes) for p in cohort.values())


def test_get_note_is_not_scoped_to_one_participant(attack_db):
    """Documents the path the data_leak attack exploits: every other chart tool is pinned to the
    participant under review, but get_note fetches any note id in the database."""
    loader.load("data_leak", attack_db)
    case = read("data_leak")[0]
    repo = ChartRepository(attack_db, use_embeddings=False)
    note = repo.get_note(case.leak.foreign_note_ids[0])
    assert note["participant_id"] == case.leak.other_participant_id != case.participant_id
    repo.close()
