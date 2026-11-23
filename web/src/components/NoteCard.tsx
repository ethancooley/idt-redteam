import { fmtDate, type NoteT } from "../data";

export function NoteCard({ note, planted = false, caption }: { note: NoteT; planted?: boolean; caption?: string }) {
  return (
    <article className={`note${planted ? " note-planted" : ""}`}>
      <header>
        <span className="note-date">{fmtDate(note.note_date)}</span>
        <span className="note-who">{note.author_role}, {note.note_type.toLowerCase()}</span>
        <code className="note-id">{note.id}</code>
      </header>
      <p>{planted ? <mark>{note.text}</mark> : note.text}</p>
      {caption && <footer>{caption}</footer>}
    </article>
  );
}
