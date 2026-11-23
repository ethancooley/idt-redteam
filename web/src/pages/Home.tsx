import { Link } from "react-router-dom";
import { Matrix } from "../components/Matrix";
import { Legend } from "../components/Outcome";
import { isCell, type Run, type Summary } from "../data";
import { useData } from "../hooks";

function totals(run: Run, defense: string) {
  let success = 0, suppressed = 0, cases = 0;
  for (const a of run.attacks) {
    const c = run.grid[defense]?.[a];
    if (isCell(c)) { success += c.success; suppressed += c.suppressed; cases += c.cases.length; }
  }
  return { success, suppressed, cases };
}

function cell(run: Run, d: string, a: string) {
  const c = run.grid[d]?.[a];
  return isCell(c) ? c : null;
}

export function Home() {
  const { data, error } = useData<Summary>("summary.json");
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="loading">Loading results…</p>;
  const run = data.runs[data.runs.length - 1];
  const base = totals(run, "baseline");
  const direct = cell(run, "baseline", "direct_instruction");
  const fake = cell(run, "baseline", "fake_authority");
  const others = run.defenses.filter((d) => d !== "baseline").map((d) => ({ d, ...totals(run, d) }));

  return (
    <>
      <section className="hero">
        <h1>Can a planted chart note make a clinical AI agent forget a fall?</h1>
        <p className="lede">
          IDT Prep Copilot reads a participant's chart and writes the brief a PACE care team reviews before its
          meeting. Every line cites its source, and a second model checks every line. Here, someone who can
          write into the chart plants a note, and we watch what reaches the team.
        </p>
        <p className="lede-small">
          In {base.success} of {base.cases} briefs, the deployed agent let a planted note push a real
          high-severity event out of its place. All participants and notes are synthetic.
        </p>
      </section>

      <section aria-labelledby="grid-h">
        <h2 id="grid-h">Every brief, by defense and attack</h2>
        <Matrix run={run} summary={data} />
        <Legend errors={run.defenses.some((d) => run.attacks.some((a) => {
          const c = run.grid[d]?.[a]; return isCell(c) && c.errors > 0; }))} />
      </section>

      <section className="findings" aria-labelledby="find-h">
        <h2 id="find-h">What the briefs show</h2>
        <dl>
          <dt>Paperwork works where instructions fail</dt>
          <dd>
            The deployed agent ignored {direct ? direct.cases.length - direct.success : 0} of {direct?.cases.length}{" "}
            notes that told it outright to leave an event out, and pointed them out to the team. A fake chart
            correction, attributed to a physician, got through in {fake?.success} of {fake?.cases.length}.
          </dd>
          <dt>Some events vanished without a trace</dt>
          <dd>
            In {base.suppressed} briefs the attacked event was gone entirely: no line, no question, no mention of
            the planted note. A reader would have no reason to look for it.
          </dd>
          <dt>The verifier never caught a planted claim</dt>
          <dd>
            It checks each line against the notes that line cites. A line that faithfully repeats a planted note
            passes.
          </dd>
          <dt>Events with a structured record held up</dt>
          <dd>
            The one attacked weight loss also shows in the vitals, which an attacker writing notes cannot touch,
            and the deployed agent reported it in every brief. Falls and new confusion exist only in notes, and
            those were the events that slipped.
          </dd>
          <dt>The conflict rule and the detector stopped nearly everything</dt>
          <dd>
            Attacks that got through:{" "}
            {others.map((o, i) => (
              <span key={o.d}>
                {data.defense_info[o.d]?.title.toLowerCase()} {o.success} of {o.cases}
                {i < others.length - 1 ? ", " : "."}
              </span>
            ))}{" "}
            None of them lowered recall on clean charts. The conflict rule and the detector were written after
            reading these failures and tested on the same participants, so they are fitted to these attacks.{" "}
            <Link to="/method#limits">Read the limitations</Link>.
          </dd>
        </dl>
      </section>

      <section className="cta">
        <h2>Try to fool it yourself</h2>
        <p>
          Plant your own note, or one of the study's, and watch the agent read the chart, draft the brief, and
          check it. Live runs need an access code.
        </p>
        <Link className="button" to="/lab">Open the attack lab</Link>
      </section>
    </>
  );
}
