import type { BriefItem } from "../data";

interface Props {
  headline: string;
  items: BriefItem[];
  questions: string[];
  removed?: BriefItem[];
  plantedIds: string[];
  targetIds?: string[];
}

function ItemRow({ item, plantedIds, targetIds }: { item: BriefItem; plantedIds: Set<string>; targetIds: Set<string> }) {
  const planted = item.citations.some((c) => plantedIds.has(c));
  const target = item.citations.some((c) => targetIds.has(c));
  return (
    <li className={`item sev-${item.severity}${planted ? " item-planted" : ""}${target ? " item-target" : ""}`}>
      <span className="sev">{item.severity}</span>
      <div>
        <p>{item.statement}</p>
        <p className="cites">
          {item.citations.map((c) => (
            <code key={c} className={plantedIds.has(c) ? "cite cite-planted" : targetIds.has(c) ? "cite cite-target" : "cite"}>{c}</code>
          ))}
        </p>
        {(target || planted) && (
          <p className="item-notes">
            {target && <span>Cites the note that proves the attacked event.</span>}
            {planted && <span>Cites a planted note.</span>}
          </p>
        )}
      </div>
    </li>
  );
}

export function BriefView({ headline, items, questions, removed = [], plantedIds, targetIds = [] }: Props) {
  const p = new Set(plantedIds);
  const t = new Set(targetIds);
  return (
    <div className="brief">
      <p className="brief-headline">{headline}</p>
      <ol className="items">
        {items.map((it, i) => <ItemRow key={i} item={it} plantedIds={p} targetIds={t} />)}
      </ol>
      {questions.length > 0 && (
        <>
          <h4>Questions for the team</h4>
          <ul className="questions">{questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </>
      )}
      {removed.length > 0 && (
        <>
          <h4>Removed by the verifier</h4>
          <ul className="questions removed">
            {removed.map((r, i) => <li key={i}>{r.statement} <em>({r.verifier_note})</em></li>)}
          </ul>
        </>
      )}
    </div>
  );
}
