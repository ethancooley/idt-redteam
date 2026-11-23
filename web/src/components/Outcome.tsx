import { OUTCOME_TEXT, type Outcome } from "../data";

export function OutcomeTag({ outcome }: { outcome: Outcome }) {
  return <span className={`tag tag-${outcome}`}>{OUTCOME_TEXT[outcome].label}</span>;
}

export function Dot({ outcome }: { outcome: Outcome }) {
  return <span className={`dot dot-${outcome}`} aria-hidden="true" />;
}

export function Legend({ errors = false }: { errors?: boolean }) {
  return (
    <ul className="legend">
      {(["surfaced", "demoted", "suppressed"] as Outcome[]).map((o) => (
        <li key={o}><Dot outcome={o} /> <strong>{OUTCOME_TEXT[o].label}.</strong> {OUTCOME_TEXT[o].meaning}</li>
      ))}
      {errors && (
        <li><span className="dot dot-error" aria-hidden="true" /> <strong>Error.</strong> The run crashed before
          writing a brief. It is left out of the counts.</li>
      )}
    </ul>
  );
}
