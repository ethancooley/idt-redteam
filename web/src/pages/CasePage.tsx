import { Link, useParams } from "react-router-dom";
import { BriefView } from "../components/BriefView";
import { NoteCard } from "../components/NoteCard";
import { OutcomeTag } from "../components/Outcome";
import { fmtDate, OUTCOME_TEXT, type CaseDetail, type Summary } from "../data";
import { useData } from "../hooks";

export function CasePage() {
  const { id } = useParams();
  const { data, error } = useData<CaseDetail>(id ? `cases/${id}.json` : null);
  const { data: summary } = useData<Summary>("summary.json");
  if (error) return <p className="error">That brief could not be found. <Link to="/">Back to the results</Link></p>;
  if (!data) return <p className="loading">Loading the brief…</p>;
  const attack = summary?.attack_info[data.attack];
  const defense = summary?.defense_info[data.defense];
  const plantedIds = data.planted.map((n) => n.id);
  return (
    <article className="case">
      <p className="crumbs"><Link to="/">Results</Link></p>
      <h1>{data.participant}: {attack?.title ?? data.attack} against the {defense?.title.toLowerCase() ?? data.defense}</h1>
      <div className={`verdict verdict-${data.outcome}`}>
        <OutcomeTag outcome={data.outcome} />
        <p>{OUTCOME_TEXT[data.outcome].meaning}</p>
        {data.hand_label && data.hand_label === data.outcome && <p className="small">Read by hand; the label agrees.</p>}
      </div>

      <div className="case-cols">
        <section>
          <h2>What was attacked</h2>
          {data.target && (
            <p className="target">
              <strong>{data.target.summary}</strong>{" "}
              <span className="small">({data.target.severity} severity, {fmtDate(data.target.event_date)}; proved by{" "}
              {data.target.note_ids.map((n) => <code key={n}>{n}</code>)})</span>
            </p>
          )}
          <h3>Planted in the chart</h3>
          {data.planted.map((n) => <NoteCard key={n.id} note={n} planted />)}
          {data.detector_withheld.length > 0 && (
            <p className="small">The detector withheld {data.detector_withheld.map((n) => <code key={n}>{n}</code>)} before drafting.</p>
          )}
          <p className="small">
            Review period {fmtDate(data.window_start)} to {fmtDate(data.review_date)}.
            {data.cost_usd != null && ` This brief cost $${data.cost_usd.toFixed(3)} and took ${Math.round(data.seconds ?? 0)} s.`}
          </p>
        </section>
        <section>
          <h2>The brief the team would read</h2>
          <BriefView headline={data.headline} items={data.items} questions={data.questions} removed={data.removed}
                     plantedIds={plantedIds} targetIds={data.target?.note_ids ?? []} />
        </section>
      </div>
    </article>
  );
}
