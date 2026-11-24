import { NoteCard } from "../components/NoteCard";
import type { Attack } from "../data";
import { useData } from "../hooks";

export function Attacks() {
  const { data, error } = useData<Attack[]>("attacks.json");
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="loading">Loading the attacks…</p>;
  return (
    <>
      <h1>The attacks</h1>
      <p className="lede">
        Each attack adds one or two realistic notes to an otherwise unchanged chart. They take the next note ids in
        the participant's own sequence and fall inside the review period, so they look like any other note. The
        clean charts and answer keys are never modified.
      </p>
      {data.map((a) => (
        <section key={a.id} className="attack">
          <h2>{a.title}</h2>
          <p>{a.about}</p>
          <p className="small">
            {a.cases} poisoned charts in the benchmark. Example from {a.example_participant}'s chart:
          </p>
          {a.example_notes.map((n) => <NoteCard key={n.id} note={n} planted />)}
        </section>
      ))}
    </>
  );
}
