import { Link } from "react-router-dom";
import { isCell, type Run, type Summary } from "../data";
import { Dot } from "./Outcome";

export function Matrix({ run, summary }: { run: Run; summary: Summary }) {
  return (
    <>
    <p className="matrix-note">
      Each dot is one brief the agent wrote from a poisoned chart ({run.participants} synthetic participants per
      cell). Select a dot to read that brief.
    </p>
    <div className="matrix-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th scope="col">Defense</th>
            {run.attacks.map((a) => <th key={a} scope="col">{summary.attack_info[a]?.title ?? a}</th>)}
            <th scope="col" className="clean-col">Clean charts</th>
          </tr>
        </thead>
        <tbody>
          {run.defenses.map((d) => {
            const row = run.grid[d];
            const clean = row.clean;
            return (
              <tr key={d}>
                <th scope="row">
                  <span className="def-name">{summary.defense_info[d]?.title ?? d}</span>
                  <span className="def-about">{summary.defense_info[d]?.about}</span>
                </th>
                {run.attacks.map((a) => {
                  const cell = row[a];
                  if (!isCell(cell)) return <td key={a}>–</td>;
                  return (
                    <td key={a}>
                      <div className="dots">
                        {cell.cases.map((c) => (
                          <Link key={c.id} to={`/case/${c.id}`} className="dot-link"
                                aria-label={`${c.participant}: ${c.outcome}`} title={`${c.participant}: ${c.outcome}`}>
                            <Dot outcome={c.outcome} />
                          </Link>
                        ))}
                        {Array.from({ length: cell.errors }).map((_, i) => (
                          <span key={`e${i}`} className="dot dot-error" title="This run errored and is not counted" />
                        ))}
                      </div>
                      <span className="cell-count">
                        {cell.success === 0 ? "Stopped all" : `${cell.success} of ${cell.cases.length} got through`}
                      </span>
                    </td>
                  );
                })}
                <td className="clean-col">
                  {clean && !isCell(clean) ? (
                    <span className="cell-count">
                      Recall {Math.round(clean.recall * 100)}%<br />${clean.cost_usd_per_brief.toFixed(3)} a brief
                    </span>
                  ) : "–"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}
