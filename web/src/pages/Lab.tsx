import { useMemo, useRef, useState } from "react";
import { BriefView } from "../components/BriefView";
import { NoteCard } from "../components/NoteCard";
import { OutcomeTag } from "../components/Outcome";
import { fmtDate, type BriefItem, type LabSetup, type NoteT, type Outcome, type Summary } from "../data";
import { useData } from "../hooks";

interface LabEvent { type: string; [k: string]: unknown }
interface LabResult {
  brief: { headline: string; items: BriefItem[]; questions_for_team: string[]; removed_claims: BriefItem[];
           run: { cost_usd?: number; seconds?: number } };
  outcome: { events: { id: string; summary: string; event_date: string; note_ids: string[]; outcome: Outcome;
                       flagged: boolean; targeted: boolean }[];
             planted_cited: string[]; planted_removed_by_verifier: string[]; detector_withheld: string[] };
  planted: NoteT[];
}

const STEP_TEXT: Record<string, string> = {
  plan: "Planning the chart review", gather: "Reading the chart", draft: "Drafting the brief",
  verify: "Checking each line against its sources", finalize: "Finishing the brief",
};

const TOOL_TEXT: Record<string, string> = {
  get_participant_summary: "Read the participant summary", get_notes: "Read the notes",
  search_notes: "Searched the notes for", get_note: "Opened note", get_vitals: "Checked vitals",
  get_encounters: "Checked ED visits and admissions", get_medication_changes: "Checked medication changes",
  get_immunizations: "Checked immunizations",
};

function describe(e: LabEvent): string | null {
  switch (e.type) {
    case "step": return STEP_TEXT[e.step as string] ?? null;
    case "plan": return `Plan: ${(e.checks as string[]).join("; ")}`;
    case "tool_end": {
      const args = e.args as Record<string, unknown>;
      const what = args.query ? ` "${args.query}"` : args.note_id ? ` ${args.note_id}` : "";
      return `${TOOL_TEXT[e.tool as string] ?? e.tool}${what}: ${e.summary}`;
    }
    case "draft": return `Draft: ${(e.items as unknown[]).length} lines. "${e.headline}"`;
    case "verdicts": {
      const r = e.results as { verdict: string }[];
      const bad = r.filter((x) => x.verdict === "unsupported").length;
      return `Checked ${r.length} lines: ${bad ? `${bad} unsupported${e.retry ? ", going back to the chart" : ""}` : "all supported"}`;
    }
    default: return null;
  }
}

export function Lab() {
  const { data: setup, error } = useData<LabSetup>("participants.json");
  const { data: summary } = useData<Summary>("summary.json");
  const [pid, setPid] = useState("");
  const [attack, setAttack] = useState("fake_authority");
  const [defense, setDefense] = useState("baseline");
  const [code, setCode] = useState("");
  const [text, setText] = useState("");
  const [role, setRole] = useState("Registered nurse");
  const [noteDate, setNoteDate] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [result, setResult] = useState<LabResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const logEnd = useRef<HTMLLIElement>(null);

  const participant = useMemo(() => setup?.participants.find((p) => p.id === (pid || setup.participants[0]?.id)),
                              [setup, pid]);
  if (error) return <p className="error">{error}</p>;
  if (!setup || !participant) return <p className="loading">Loading the lab…</p>;
  const preset = attack !== "custom" ? participant.presets[attack] ?? [] : [];
  const date = noteDate || participant.review_date;

  async function run(ev: React.FormEvent) {
    ev.preventDefault();
    if (!participant) return;
    setRunning(true); setLog([]); setResult(null); setFailure(null);
    const body: Record<string, unknown> = { access_code: code, participant_id: participant.id, defense, attack };
    if (attack === "custom") body.note = { text, author_role: role, note_date: date, note_type: "Progress note" };
    try {
      const resp = await fetch("/api/lab/run", { method: "POST", headers: { "Content-Type": "application/json" },
                                                 body: JSON.stringify(body) });
      if (!resp.ok || !resp.body) {
        const err = await resp.json().catch(() => ({ error: `The server answered ${resp.status}.` }));
        throw new Error(err.error);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const e = JSON.parse(line) as LabEvent;
          if (e.type === "done") setResult(e.result as LabResult);
          else if (e.type === "error") setFailure(e.message as string);
          else {
            const d = describe(e);
            if (d) setLog((l) => [...l, d]);
          }
        }
        logEnd.current?.scrollIntoView({ block: "nearest" });
      }
    } catch (e) {
      setFailure((e as Error).message || "The run could not start.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <h1>Attack lab</h1>
      <p className="lede">
        Plant a note in one participant's chart and watch the agent read it. The note exists only for your run:
        it is added to what the chart tools return, never saved, and nobody else sees it.
      </p>

      <form className="lab-form" onSubmit={run}>
        <fieldset>
          <legend>Whose chart</legend>
          <select value={participant.id} onChange={(e) => { setPid(e.target.value); setNoteDate(""); }}
                  aria-label="Participant">
            {setup.participants.map((p) => <option key={p.id} value={p.id}>{p.name}, {p.age}</option>)}
          </select>
          <p className="small">
            Review period {fmtDate(participant.window_start)} to {fmtDate(participant.review_date)}. High-severity
            events in the chart:
          </p>
          <ul className="events">{participant.high_events.map((h) => <li key={h.id}>{h.summary}</li>)}</ul>
        </fieldset>

        <fieldset>
          <legend>What to plant</legend>
          <div className="choices">
            {setup.attacks.map((a) => (
              <label key={a} className="choice">
                <input type="radio" name="attack" value={a} checked={attack === a} onChange={() => setAttack(a)} />
                {summary?.attack_info[a]?.title ?? a}
              </label>
            ))}
            <label className="choice">
              <input type="radio" name="attack" value="custom" checked={attack === "custom"}
                     onChange={() => setAttack("custom")} />
              Write my own
            </label>
          </div>
          {attack === "custom" ? (
            <div className="custom">
              <label>Note text
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={1500}
                          minLength={20} required placeholder="Write it the way a real chart note reads." />
              </label>
              <div className="row">
                <label>From
                  <select value={role} onChange={(e) => setRole(e.target.value)}>
                    {setup.roles.map((r) => <option key={r}>{r}</option>)}
                  </select>
                </label>
                <label>Dated
                  <input type="date" value={date} min={participant.window_start} max={participant.review_date}
                         onChange={(e) => setNoteDate(e.target.value)} required />
                </label>
              </div>
            </div>
          ) : (
            <>
              <p className="small">{summary?.attack_info[attack]?.about}</p>
              {preset.map((n) => <NoteCard key={n.id} note={n} planted />)}
            </>
          )}
        </fieldset>

        <fieldset>
          <legend>Defense</legend>
          <div className="choices">
            {setup.defenses.map((d) => (
              <label key={d} className="choice choice-wide">
                <input type="radio" name="defense" value={d} checked={defense === d} onChange={() => setDefense(d)} />
                <span><strong>{summary?.defense_info[d]?.title ?? d}.</strong> {summary?.defense_info[d]?.about}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="run-row">
          <label>Access code
            <input type="password" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" required />
          </label>
          <button className="button" type="submit" disabled={running}>
            {running ? "Running…" : "Run the agent"}
          </button>
        </div>
        <p className="small">A run takes about a minute and costs about four cents.</p>
      </form>

      {(log.length > 0 || running) && (
        <section className="live" aria-live="polite">
          <h2>What the agent is doing</h2>
          <ol className="log">
            {log.map((l, i) => <li key={i}>{l}</li>)}
            {running && <li className="pending" ref={logEnd}>Working…</li>}
          </ol>
        </section>
      )}

      {failure && <p className="error" role="alert">{failure}</p>}

      {result && (
        <section className="lab-result">
          <h2>What reached the team</h2>
          <ul className="event-outcomes">
            {result.outcome.events.map((e) => (
              <li key={e.id}>
                <OutcomeTag outcome={e.outcome} /> {e.summary}
                {e.targeted && <span className="small"> (the event this attack aims at)</span>}
              </li>
            ))}
          </ul>
          <p className="small">
            {result.outcome.detector_withheld.length > 0 && "The detector withheld the planted note before drafting. "}
            {result.outcome.planted_cited.length > 0
              ? "The brief cites the planted note. "
              : "The brief does not cite the planted note. "}
            {result.outcome.planted_removed_by_verifier.length > 0 && "The verifier removed a line built on it. "}
            Cost ${result.brief.run.cost_usd?.toFixed(3)}, {Math.round(result.brief.run.seconds ?? 0)} s.
          </p>
          <BriefView headline={result.brief.headline} items={result.brief.items}
                     questions={result.brief.questions_for_team} removed={result.brief.removed_claims}
                     plantedIds={result.planted.map((n) => n.id)}
                     targetIds={result.outcome.events.filter((e) => e.targeted).flatMap((e) => e.note_ids)} />
        </section>
      )}
    </>
  );
}
