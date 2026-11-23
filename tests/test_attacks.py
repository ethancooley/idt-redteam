"""The generator: deterministic, realistic, and never touches the clean data."""
from __future__ import annotations

import re
from datetime import date

import pytest

from idt_redteam.attacks import ATTACKS, LEAK_ATTACKS, build_case, pick_target, poison
from idt_redteam.benchmark import generate


@pytest.fixture(scope="module")
def cases(clean):
    cohort, keys = clean
    return generate(cohort, keys)


def test_same_seed_same_benchmark(clean, cases):
    cohort, keys = clean
    again = generate(cohort, keys)
    assert {a: [c.model_dump() for c in cs] for a, cs in cases.items()} == \
           {a: [c.model_dump() for c in cs] for a, cs in again.items()}


def test_omission_attacks_target_a_real_high_severity_event(clean, cases):
    _, keys = clean
    for attack, cs in cases.items():
        if attack in LEAK_ATTACKS:
            continue
        assert cs, attack
        for c in cs:
            truth = next(t for t in keys[c.participant_id].must_surface if t.id == c.target_id)
            assert truth.severity.value == "high" and c.target_note_ids == truth.supporting_note_ids


def test_every_omission_attack_aims_at_the_same_event_per_participant(cases):
    targets = {}
    for attack, cs in cases.items():
        for c in cs:
            if c.target_id:
                assert targets.setdefault(c.participant_id, c.target_id) == c.target_id


def test_planted_notes_look_native_and_sit_inside_the_window(clean, cases):
    cohort, _ = clean
    for attack, cs in cases.items():
        for c in cs:
            p = cohort[c.participant_id]
            expected = 60 if attack == "flooding" else (2 if attack == "citation_laundering" else 1)
            assert len(c.poison_notes) == expected
            for n in c.poison_notes:
                assert re.fullmatch(rf"{p.id[:8]}-n\d{{3}}", n.id)
                assert p.window_start <= n.note_date <= p.review_date


def test_poison_adds_notes_without_changing_the_clean_chart(clean, cases):
    cohort, _ = clean
    case = cases["citation_laundering"][0]
    p = cohort[case.participant_id]
    before = p.model_dump_json()
    poisoned = poison(p, case)
    assert len(poisoned.notes) == len(p.notes) + 2
    assert p.model_dump_json() == before
    with pytest.raises(ValueError):
        poison(cohort[cases["fake_authority"][1].participant_id], case)  # wrong participant


def test_planted_claims_name_the_real_event_date(clean, cases):
    _, keys = clean
    for attack in ["direct_instruction", "fake_authority", "false_resolution", "backdating", "citation_laundering"]:
        for c in cases[attack]:
            truth = next(t for t in keys[c.participant_id].must_surface if t.id == c.target_id)
            d: date = truth.event_date
            assert f"{d:%b} {d.day}, {d.year}" in c.poison_notes[0].text


def test_data_leak_points_at_another_participants_real_note(clean, cases):
    cohort, _ = clean
    assert len(cases["data_leak"]) == len(cohort)
    for c in cases["data_leak"]:
        other = cohort[c.leak.other_participant_id]
        assert other.id != c.participant_id
        assert set(c.leak.foreign_note_ids) <= {n.id for n in other.notes}
        assert c.leak.foreign_note_ids[0] in c.poison_notes[0].text


def test_participants_without_a_high_severity_event_are_skipped(clean):
    cohort, keys = clean
    pid = next(pid for pid, k in keys.items() if pick_target(k) is None)
    assert build_case("fake_authority", cohort[pid], keys[pid]) is None


def test_unknown_attack_is_rejected(clean):
    cohort, keys = clean
    pid = sorted(cohort)[0]
    with pytest.raises(ValueError):
        build_case("not_an_attack", cohort[pid], keys[pid])
    assert "data_leak" in ATTACKS
