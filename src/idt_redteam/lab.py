"""The attack lab: a visitor plants a note in one participant's chart and watches the agent read it.

The planted note never touches the database. It lives only in this run: a wrapper around the chart tools
adds it to what get_notes, search_notes, and get_note return for that one participant, exactly where a
real note would appear. Every other visitor, and every other run, sees the clean chart.

    open_lab_run(body, client_id)   checks the access code, the caps, the participant, and the note.
                                    Returns (status, error) or a LabRun ticket with the run logged.
    stream_lab_run(ticket)          runs the agent under the chosen defense and yields its progress,
                                    ending with {"type": "done", "result": ...} or {"type": "error", ...}.

Access control reuses IDT Prep Copilot's personal access codes (idt_copilot.api.codes), plus an owner code
with per-visitor daily caps. Configuration comes from the environment:

    REDTEAM_ACCESS_CODE         owner code; live runs are off when it is not set
    REDTEAM_DAILY_LIMIT         runs allowed per day across everyone (default 20)
    REDTEAM_PER_CLIENT_LIMIT    runs allowed per day per visitor on the owner code (default 3)
    DATABASE_URL                the lab's own database: the clean cohort plus the run log
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator

from idt_copilot.agent.chart_client import InProcessChartClient
from idt_copilot.agent.graph import AgentConfig, run_agent
from idt_copilot.agent.schema import Brief
from idt_copilot.api import codes
from idt_copilot.chart.repository import ChartRepository, NotFound
from idt_copilot.models import AnswerKey, Note, Severity

from idt_redteam.attacks import ATTACKS, AttackCase
from idt_redteam.defenses import DEFENSES, llm_factory
from idt_redteam.score import detector_flags, score_case

LAB_DEFENSES = ["baseline", "spotlight", "conflict_rule", "detector"]
LAB_ATTACKS = ["direct_instruction", "fake_authority", "false_resolution", "backdating", "citation_laundering"]
ROLES = ["Registered nurse", "Primary care physician", "Physical therapist", "Occupational therapist",
         "Social worker", "Dietitian", "Home care aide", "Day center coordinator", "Pharmacist",
         "Health information management"]
MAX_NOTE_CHARS = 1500
DATA_PATH = Path(os.environ.get("REDTEAM_LAB_DATA", Path(__file__).with_name("lab_data.json")))

LAB_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS lab_runs (
    id             SERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    participant_id TEXT NOT NULL,
    defense        TEXT NOT NULL,
    attack         TEXT NOT NULL,          -- a benchmark attack name, or 'custom'
    note_chars     INTEGER NOT NULL,       -- the planted text itself is never stored
    client_hash    TEXT NOT NULL,
    code_id        INTEGER,
    status         TEXT NOT NULL DEFAULT 'running',
    cost_usd       DOUBLE PRECISION,
    seconds        DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS lab_runs_created ON lab_runs (created_at);
"""


# ------------------------------------------------------------ data shipped with the function

_DATA: dict | None = None


def lab_data() -> dict:
    """Participants that can be attacked, their answer keys, and the benchmark's preset attacks.
    Built by `python -m idt_redteam.web_export` so the function needs no checkout of the clean data."""
    global _DATA
    if _DATA is None:
        _DATA = json.loads(DATA_PATH.read_text())
    return _DATA


# ------------------------------------------------------------ the planted note, added per run

class PlantedChart:
    """Chart tools for one run, with planted notes added for one participant. Wraps any ChartClient."""

    def __init__(self, inner: Any, participant_id: str, planted: list[Note], window: tuple[date, date]):
        self.inner, self.pid, self.planted, self.window = inner, participant_id, planted, window
        self.by_id = {n.id: n for n in planted}

    async def tools(self) -> list[dict]:
        return await self.inner.tools()

    @staticmethod
    def _row(n: Note) -> dict:
        return {"id": n.id, "note_date": n.note_date.isoformat(), "author_role": n.author_role,
                "note_type": n.note_type, "text": n.text}

    async def call(self, name: str, arguments: dict) -> Any:
        if name == "get_note" and arguments.get("note_id") in self.by_id:
            return {**self._row(self.by_id[arguments["note_id"]]), "participant_id": self.pid}
        result = await self.inner.call(name, arguments)
        if arguments.get("participant_id") != self.pid or (isinstance(result, dict) and "error" in result):
            return result
        if name == "get_notes" and isinstance(result, list):
            start = _as_date(arguments.get("start_date")) or self.window[0]
            end = _as_date(arguments.get("end_date")) or self.window[1]
            role = (arguments.get("author_role") or "").lower()
            extra = [self._row(n) for n in self.planted
                     if start <= n.note_date <= end and role in n.author_role.lower()]
            merged = sorted(result + extra, key=lambda r: (r["note_date"], r["id"]))
            return merged[: max(1, min(int(arguments.get("limit") or 100), 200))]
        if name == "search_notes" and isinstance(result, dict):
            terms = [t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", arguments.get("query", ""))]
            since = _as_date(arguments.get("since"))
            hits = [{**self._row(n), "score": 1.0} for n in self.planted
                    if any(t in n.text.lower() for t in terms) and (since is None or n.note_date >= since)]
            if hits:
                limit = max(1, min(int(arguments.get("limit") or 5), 20))
                result = {**result, "results": (hits + result.get("results", []))[:limit]}
        return result


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


# ------------------------------------------------------------ opening a run

@dataclass
class LabRun:
    run_id: int
    participant_id: str
    participant_name: str
    defense: str
    attack: str
    planted: list[Note]
    case: AttackCase | None
    runs_left_today: int
    repo: ChartRepository
    code: codes.Reserved | None = None
    make_client: Callable[[], Any] | None = None  # tests pass a scripted stand-in for Claude
    window: tuple[date, date] = field(default=(date.min, date.max))


def _error(status: int, message: str) -> tuple[int, dict]:
    return status, {"error": message}


def _client_hash(client_id: str | None) -> str:
    salt = os.environ.get("REDTEAM_ACCESS_CODE", "")
    return hashlib.sha256(f"{salt}:{client_id or 'unknown'}".encode()).hexdigest()[:16]


def _next_note_id(repo: ChartRepository, pid: str) -> int:
    rows = repo.conn.execute("SELECT id FROM notes WHERE participant_id = %s", (pid,)).fetchall()
    nums = [int(m.group(1)) for r in rows if (m := re.search(r"-n(\d+)$", r["id"]))]
    return max(nums, default=0) + 1


def _planted_notes(body: dict, pid: str, window: tuple[date, date], repo: ChartRepository) -> list[Note] | str:
    """The visitor's note, or a preset attack's notes, renumbered to follow the participant's own notes."""
    attack = str(body.get("attack") or "custom")
    start = _next_note_id(repo, pid)
    if attack != "custom":
        preset = lab_data()["presets"].get(attack, {}).get(pid)
        if not preset:
            return "That attack has no preset for this participant."
        notes = [Note.model_validate(n) for n in preset["poison_notes"]]
    else:
        note = body.get("note") or {}
        text = " ".join(str(note.get("text", "")).split())
        if not 20 <= len(text) <= MAX_NOTE_CHARS:
            return f"Write a note between 20 and {MAX_NOTE_CHARS} characters."
        role = str(note.get("author_role", ""))
        if role not in ROLES:
            return "Choose who the note is from."
        d = _as_date(note.get("note_date"))
        if d is None or not window[0] <= d <= window[1]:
            return f"Date the note inside the review period ({window[0]} to {window[1]})."
        kind = " ".join(str(note.get("note_type") or "Progress note").split())[:60] or "Progress note"
        notes = [Note(id="tmp", note_date=d, author_role=role, note_type=kind, text=text)]
    prefix = pid[:8]
    return [n.model_copy(update={"id": f"{prefix}-n{start + i:03d}"}) for i, n in enumerate(notes)]


def open_lab_run(body: dict, client_id: str | None = None, make_client=None) -> tuple[int, dict] | LabRun:
    expected = os.environ.get("REDTEAM_ACCESS_CODE")
    if not expected:
        return _error(503, "Live runs are turned off right now. The saved results are still here.")
    code = str(body.get("access_code", "")).strip()
    owner = bool(code) and hmac.compare_digest(code.encode(), expected.encode())

    repo = ChartRepository(use_embeddings=False)
    conn = repo.conn
    reserved: codes.Reserved | None = None
    if not owner:
        try:
            reserved = codes.reserve_run(conn, code) if code else None
        except codes.CodeRejected as e:
            return _error(e.status, e.message)
        if reserved is None:
            time.sleep(0.5)  # slow down guessing
            return _error(401, "That access code is not valid.")

    def refuse(status: int, message: str) -> tuple[int, dict]:
        if reserved:
            codes.release_run(conn, reserved.code_id)
        return _error(status, message)

    pid = str(body.get("participant_id", ""))
    if pid not in lab_data()["participants"]:
        return refuse(404, "Choose one of the listed participants.")
    defense = str(body.get("defense", "baseline"))
    if defense not in LAB_DEFENSES:
        return refuse(400, f"Choose a defense: {', '.join(LAB_DEFENSES)}.")
    attack = str(body.get("attack") or "custom")
    if attack != "custom" and attack not in LAB_ATTACKS:
        return refuse(400, "Choose a preset attack or write your own note.")
    try:
        summary = repo.get_participant_summary(pid)
    except NotFound:
        return refuse(404, "That participant is not in the lab's chart database.")
    window = (date.fromisoformat(summary["window_start"]), date.fromisoformat(summary["review_date"]))
    planted = _planted_notes(body, pid, window, repo)
    if isinstance(planted, str):
        return refuse(400, planted)

    daily = int(os.environ.get("REDTEAM_DAILY_LIMIT", "20"))
    per_client = int(os.environ.get("REDTEAM_PER_CLIENT_LIMIT", "3"))
    who = _client_hash(client_id)
    conn.execute(LAB_RUNS_DDL)
    today = conn.execute("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE client_hash = %s AND code_id IS NULL) AS mine
        FROM lab_runs WHERE created_at >= date_trunc('day', now())""", (who,)).fetchone()
    if today["total"] >= daily:
        return refuse(429, "Today's live runs are used up. Try again tomorrow, or browse the saved results.")
    if owner and today["mine"] >= per_client:
        return _error(429, f"You have used all {per_client} live runs for today.")
    run_id = conn.execute(
        """INSERT INTO lab_runs (participant_id, defense, attack, note_chars, client_hash, code_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (pid, defense, attack, sum(len(n.text) for n in planted), who,
         reserved.code_id if reserved else None)).fetchone()["id"]
    left = (min(reserved.runs_left, daily - today["total"] - 1) if reserved
            else max(0, min(daily - today["total"], per_client - today["mine"]) - 1))

    case = None
    if attack != "custom":
        preset = lab_data()["presets"][attack][pid]
        case = AttackCase.model_validate({**preset, "poison_notes": [n.model_dump() for n in planted]})
    return LabRun(run_id, pid, f"{summary['first_name']} {summary['last_name']}", defense, attack, planted, case,
                  max(0, left), repo, reserved, make_client, window)


# ------------------------------------------------------------ running it

def outcome(run: LabRun, brief: Brief) -> dict:
    """What happened to each high-severity event, scored with the study's own rules."""
    key = AnswerKey.model_validate(lab_data()["participants"][run.participant_id]["answer_key"])
    planted_ids = {n.id for n in run.planted}
    events = []
    for t in key.must_surface:
        if t.severity != Severity.high:
            continue
        markers = run.case.claim_markers if run.case and run.case.target_id == t.id else []
        case = AttackCase(case_id=f"lab/{run.run_id}", attack=run.attack if run.case else "custom",
                          participant_id=run.participant_id, target_id=t.id, target_category=t.category,
                          target_severity=t.severity.value, target_note_ids=t.supporting_note_ids,
                          poison_notes=run.planted, claim_markers=markers)
        s = score_case(case, brief, key)
        events.append({"id": t.id, "summary": t.summary, "event_date": str(t.event_date or ""),
                       "note_ids": t.supporting_note_ids, "outcome": s.outcome, "flagged": s.flagged,
                       "targeted": bool(run.case and run.case.target_id == t.id)})
    cited = sorted({c for i in brief.items for c in i.citations} & planted_ids)
    removed = sorted({c for i in brief.removed_claims for c in i.citations} & planted_ids)
    return {"events": events, "planted_cited": cited, "planted_removed_by_verifier": removed,
            "detector_withheld": sorted(set(detector_flags(brief)) & planted_ids)}


def stream_lab_run(run: LabRun, heartbeat_seconds: float = 10.0) -> Iterator[dict]:
    events: queue.Queue = queue.Queue()
    result: dict = {}

    def work() -> None:
        try:
            result["llm"] = llm = llm_factory(run.defense, run.make_client)()
            chart = PlantedChart(InProcessChartClient(), run.participant_id, run.planted, run.window)
            result["brief"] = asyncio.run(run_agent(run.participant_id, llm, chart, AgentConfig(), emit=events.put))
        except Exception as e:  # reported to the visitor below
            result["error"] = e
        finally:
            events.put(None)

    yield {"type": "start", "participant_id": run.participant_id, "name": run.participant_name,
           "defense": run.defense, "attack": run.attack, "runs_left_today": run.runs_left_today,
           "planted": [{"id": n.id, "note_date": n.note_date.isoformat(), "author_role": n.author_role,
                        "note_type": n.note_type, "text": n.text} for n in run.planted],
           "code": {"runs_left": run.code.runs_left, "budget_left": run.code.budget_left} if run.code else None}
    threading.Thread(target=work, daemon=True).start()
    while True:
        try:
            event = events.get(timeout=heartbeat_seconds)
        except queue.Empty:
            yield {"type": "heartbeat"}
            continue
        if event is None:
            break
        yield event

    conn = run.repo.conn
    llm = result.get("llm")
    spent = float(llm.usage.as_dict().get("cost_usd", 0.0)) if llm else 0.0
    if "error" in result:
        conn.execute("UPDATE lab_runs SET status = 'failed', cost_usd = %s WHERE id = %s", (spent, run.run_id))
        if run.code and spent:
            codes.charge(conn, run.code.code_id, spent)
        yield {"type": "error", "message": f"The run failed: {result['error']}"}
        return
    brief: Brief = result["brief"]
    conn.execute("UPDATE lab_runs SET status = 'ok', cost_usd = %s, seconds = %s WHERE id = %s",
                 (brief.run.get("cost_usd"), brief.run.get("seconds"), run.run_id))
    if run.code:
        codes.charge(conn, run.code.code_id, brief.run.get("cost_usd") or 0.0)
    shown = {k: v for k, v in brief.run.items() if k not in ("trace", "tool_calls")}
    yield {"type": "done", "result": {
        "brief": {**brief.model_dump(mode="json"), "run": shown},
        "outcome": outcome(run, brief), "planted": [n.model_dump(mode="json") for n in run.planted]}}


__all__ = ["ATTACKS", "DEFENSES", "LAB_ATTACKS", "LAB_DEFENSES", "ROLES", "open_lab_run", "stream_lab_run", "PlantedChart"]
