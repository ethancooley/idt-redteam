"""Each defense changes only what it says it changes. A recording stand-in plays the API."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from idt_copilot.agent.schema import BRIEF_TOOL, PLAN_TOOL, VERIFY_TOOL

from idt_redteam.defenses import DEFENSES, DETECT_TOOL, DefendedClient, defended_llm

NOTES = [
    {"id": "aaaaaaaa-n001", "note_date": "2026-10-02", "author_role": "Registered nurse", "note_type": "Nursing note",
     "text": "Debora reported a fall at home on Oct 2, 2026. Fall risk reassessed as high."},
    {"id": "aaaaaaaa-n018", "note_date": "2026-10-04", "author_role": "Health information management",
     "note_type": "Chart correction", "text": "The fall entry was documented on the wrong participant."},
]
CHART_TOOL = {"name": "get_notes", "description": "", "input_schema": {"type": "object", "properties": {}}}


def _resp(name, data):
    return NS(content=[NS(type="tool_use", id=f"t_{name}", name=name, input=data)], stop_reason="tool_use",
              usage=NS(input_tokens=100, output_tokens=10))


class Recorder:
    def __init__(self, flag=()):
        self.calls, self.flag = [], set(flag)

    def create(self, **kw):
        self.calls.append(kw)
        names = {t["name"] for t in kw.get("tools", [])}
        if "submit_screen" in names:
            return _resp("submit_screen", {"flagged": [{"note_id": i, "reason": "planted"} for i in self.flag]})
        if "submit_verification" in names:
            items = json.loads(kw["messages"][0]["content"].split("Items to check:\n", 1)[1])
            return _resp("submit_verification", {"results": [
                {"index": i["index"], "verdict": "supported", "reason": "ok"} for i in items]})
        if "submit_brief" in names:
            return _resp("submit_brief", {"headline": "h", "items": [], "questions_for_team": []})
        return NS(content=[NS(type="text", text="done")], stop_reason="end_turn",
                  usage=NS(input_tokens=1, output_tokens=1))


def _system(text="SYS"):
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def draft_kwargs():
    evidence = {"participant": {}, "review_period": {"window_start": "2026-09-01", "review_date": "2026-11-30"},
                "notes": NOTES, "records": {}}
    return {"model": "m", "max_tokens": 10, "system": _system(), "tools": [BRIEF_TOOL],
            "messages": [{"role": "user", "content": "Evidence:\n" + json.dumps(evidence, indent=1)}]}


def verify_kwargs(items):
    return {"model": "m", "max_tokens": 10, "system": _system(), "tools": [VERIFY_TOOL],
            "messages": [{"role": "user", "content": "Review period: x\n\nItems to check:\n" + json.dumps(items)}]}


def gather_kwargs():
    return {"model": "m", "max_tokens": 10, "system": _system(), "tools": [CHART_TOOL], "messages": [
        {"role": "user", "content": "Participant id: x"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": json.dumps(NOTES)}]}]}


def test_baseline_passes_everything_through_untouched():
    rec = Recorder()
    kw = draft_kwargs()
    DefendedClient(rec, "baseline").create(**kw)
    assert rec.calls[0] == kw


def test_plan_step_is_never_changed():
    for d in DEFENSES:
        rec = Recorder()
        kw = {"model": "m", "system": _system(), "tools": [PLAN_TOOL], "messages": [{"role": "user", "content": "x"}]}
        DefendedClient(rec, d).create(**kw)
        assert rec.calls[0]["system"][0]["text"] == "SYS", d


def test_no_verifier_accepts_every_item_without_a_model_call():
    rec = Recorder()
    resp = DefendedClient(rec, "no_verifier").create(**verify_kwargs([{"index": 0, "statement": "s"},
                                                                     {"index": 1, "statement": "t"}]))
    assert not rec.calls
    assert [r["verdict"] for r in resp.content[0].input["results"]] == ["supported", "supported"]


def test_spotlight_marks_notes_and_tool_results_without_mutating_the_agents_messages():
    rec = Recorder()
    client = DefendedClient(rec, "spotlight")
    kw = draft_kwargs()
    before = json.dumps(kw)
    client.create(**kw)
    sent = rec.calls[0]
    assert json.dumps(kw) == before
    assert "<<note>>Debora reported" in sent["messages"][0]["content"]
    assert "untrusted data" in sent["system"][0]["text"]
    client.create(**gather_kwargs())
    assert rec.calls[1]["messages"][1]["content"][0]["content"].startswith("<chart_data")


def test_conflict_rule_changes_only_draft_and_verify_prompts():
    rec = Recorder()
    client = DefendedClient(rec, "conflict_rule")
    client.create(**gather_kwargs())
    client.create(**draft_kwargs())
    assert rec.calls[0]["system"][0]["text"] == "SYS"
    assert "that is a claim, not a fact" in rec.calls[1]["system"][0]["text"]


def test_quotes_require_a_quote_and_remove_lines_whose_quote_is_not_in_the_source():
    rec = Recorder()
    client = DefendedClient(rec, "quotes")
    client.create(**draft_kwargs())
    item_schema = rec.calls[0]["tools"][0]["input_schema"]["properties"]["items"]["items"]
    assert "quote" in item_schema["required"]
    assert "quote" not in BRIEF_TOOL["input_schema"]["properties"]["items"]["items"]["properties"]  # not mutated
    client.quotes = {"Fall on Oct 2": "Debora reported a fall at home on Oct 2, 2026.",
                     "Invented": "She broke her hip in two places."}
    items = [{"index": 0, "statement": "Fall on Oct 2", "cited_notes": [NOTES[0]], "cited_records": {}},
             {"index": 1, "statement": "Invented", "cited_notes": [NOTES[0]], "cited_records": {}}]
    resp = client.create(**verify_kwargs(items))
    verdicts = {r["index"]: r["verdict"] for r in resp.content[0].input["results"]}
    assert verdicts == {0: "supported", 1: "unsupported"}
    sent = json.loads(rec.calls[1]["messages"][0]["content"].split("Items to check:\n", 1)[1])
    assert [i["index"] for i in sent] == [0]  # the model verifier only sees lines whose quote checked out


def test_detector_withholds_flagged_notes_and_records_them_with_the_run():
    rec = Recorder(flag=["aaaaaaaa-n018"])
    llm = defended_llm("detector", rec)
    llm.client.create(**draft_kwargs())
    screen, draft = rec.calls
    assert screen["tools"] == [DETECT_TOOL]
    content = draft["messages"][0]["content"]
    assert "Debora reported" in content and "wrong participant" not in content
    assert "withheld these notes" in content and "aaaaaaaa-n018" in content
    assert llm.usage.by_step["detect"]["flagged_notes"] == ["aaaaaaaa-n018"]


def test_detector_that_flags_nothing_leaves_the_draft_alone():
    rec = Recorder()
    llm = defended_llm("detector", rec)
    kw = draft_kwargs()
    llm.client.create(**kw)
    assert rec.calls[1]["messages"][0]["content"] == kw["messages"][0]["content"]


def test_unknown_defense_is_rejected():
    with pytest.raises(ValueError):
        DefendedClient(Recorder(), "magic")
