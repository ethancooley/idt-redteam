// Access codes for the attack lab: make a personal code, see what each has used, change limits, turn it off.
// Not linked from the navigation; open /admin. Everything needs the admin password (REDTEAM_ADMIN_TOKEN on the
// server). The password is kept only for this browser tab and sent as a bearer token.
import { Fragment, useCallback, useEffect, useState } from "react";
import type { Summary } from "../data";
import { useData } from "../hooks";

interface CodeRecord {
  id: number; label: string; max_runs: number; max_cost_usd: number; runs_used: number; cost_used_usd: number;
  expires_at: string | null; revoked_at: string | null; created_at: string; last_used_at: string | null;
  state: "active" | "used_up" | "expired" | "revoked";
}
interface RunRecord {
  created_at: string; status: string; cost_usd: number | null; seconds: number | null;
  defense: string; attack: string; participant: string | null; code_label: string;
}
interface RunsResponse {
  runs: RunRecord[];
  today: { runs: number; cost_usd: number; limit: number };
  all_time: { runs: number; cost_usd: number };
}

const STATE_LABEL: Record<CodeRecord["state"], string> = {
  active: "Active", used_up: "Used up", expired: "Expired", revoked: "Turned off",
};
const TOKEN_KEY = "redteam-admin-token";
const readToken = () => { try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } };
const saveToken = (t: string) => {
  try { if (t) sessionStorage.setItem(TOKEN_KEY, t); else sessionStorage.removeItem(TOKEN_KEY); } catch { /* fine */ }
};
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "Never";
const money = (x: number) => `$${x.toFixed(2)}`;

function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <span className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
      <span className={pct >= 100 ? "meter-fill meter-full" : "meter-fill"} style={{ width: `${pct}%` }} />
    </span>
  );
}

export function Admin() {
  const { data: summary } = useData<Summary>("summary.json");
  const [token, setToken] = useState(readToken);
  const [codes, setCodes] = useState<CodeRecord[] | null>(null);
  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ code: string; record: CodeRecord } | null>(null);
  const [editing, setEditing] = useState<number | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const call = useCallback(async (method: string, path: string, body?: unknown): Promise<any> => {
    const r = await fetch(`/api/admin${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (r.status === 401) { saveToken(""); setToken(""); }
    if (!r.ok) throw new Error(data.error ?? `The request failed (status ${r.status}).`);
    return data;
  }, [token]);

  const refresh = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([call("GET", "/codes"), call("GET", "/runs")]);
      setCodes(c.codes); setRuns(r); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, [call]);

  useEffect(() => { if (token) void refresh(); }, [token, refresh]);

  if (!token) return <SignIn error={error} onSignIn={(t) => { saveToken(t); setToken(t); }} />;

  const active = codes?.filter((c) => c.state === "active").length ?? 0;
  const onCodes = codes?.reduce((a, c) => a + c.cost_used_usd, 0) ?? 0;
  const attackTitle = (a: string) => a === "custom" ? "Own note" : summary?.attack_info[a]?.title ?? a;
  const defenseTitle = (d: string) => summary?.defense_info[d]?.title ?? d;

  return (
    <div className="admin">
      <div className="admin-head">
        <div>
          <h1>Access codes</h1>
          <p className="lede">Give each person their own code for the attack lab, with its own limits. Turn any code
            off at any time.</p>
        </div>
        <div className="admin-tools">
          <button type="button" className="button-quiet" onClick={refresh}>Refresh</button>
          <button type="button" className="button-quiet"
                  onClick={() => { saveToken(""); setToken(""); setCodes(null); setRuns(null); }}>Sign out</button>
        </div>
      </div>

      {error && <p className="error" role="alert">{error}</p>}

      <dl className="stats">
        <div><dt>Active codes</dt><dd>{codes ? active : "–"}<span> of {codes?.length ?? 0} made</span></dd></div>
        <div>
          <dt>Lab runs today</dt>
          <dd>{runs?.today.runs ?? "–"}<span> of {runs?.today.limit ?? "–"} allowed</span></dd>
          {runs && <Meter value={runs.today.runs} max={runs.today.limit} label="Lab runs used today" />}
        </div>
        <div><dt>Spent today</dt><dd>{runs ? money(runs.today.cost_usd) : "–"}</dd></div>
        <div>
          <dt>Spent in all</dt><dd>{runs ? money(runs.all_time.cost_usd) : "–"}</dd>
          <p className="small">{codes ? `${money(onCodes)} on personal codes, the rest on the owner code` : ""}</p>
        </div>
      </dl>

      <div className="admin-grid">
        <CreateCode onCreate={async (input) => { setCreated(await call("POST", "/codes", input)); void refresh(); }} />
        {created
          ? <NewCode code={created.code} record={created.record} onDone={() => setCreated(null)} />
          : (
            <section className="panel">
              <h2>Sending a code</h2>
              <p>A new code shows here once, with a message ready to paste. Only a fingerprint of each code is stored,
                so it can't be looked up later. If someone loses theirs, make a new one.</p>
            </section>
          )}
      </div>

      <h2>Codes</h2>
      <div className="table-scroll">
        <table className="admin-table">
          <thead>
            <tr><th scope="col">For</th><th scope="col">Status</th><th scope="col">Runs</th>
              <th scope="col">Spending</th><th scope="col">Expires</th><th scope="col">Last used</th>
              <th scope="col"><span className="visually-hidden">Actions</span></th></tr>
          </thead>
          <tbody>
            {codes?.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td><strong>{c.label}</strong><span className="cell-sub">Made {when(c.created_at)}</span></td>
                  <td><span className={`state state-${c.state}`}>{STATE_LABEL[c.state]}</span></td>
                  <td>{c.runs_used} of {c.max_runs}<Meter value={c.runs_used} max={c.max_runs} label={`Runs used by ${c.label}`} /></td>
                  <td>{money(c.cost_used_usd)} of {money(c.max_cost_usd)}
                    <Meter value={c.cost_used_usd} max={c.max_cost_usd} label={`Spending by ${c.label}`} /></td>
                  <td>{c.expires_at ? new Date(c.expires_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "Never"}</td>
                  <td>{when(c.last_used_at)}</td>
                  <td><span className="actions">
                    {c.state !== "revoked" && editing !== c.id && (
                      <button type="button" className="link-button" onClick={() => setEditing(c.id)}>
                        {c.state === "active" ? "Change limits" : c.state === "expired" ? "Extend" : "Give more runs"}
                      </button>
                    )}
                    {c.state === "active" && (
                      <RevokeButton label={c.label} onRevoke={async () => {
                        try { await call("POST", `/codes/${c.id}/revoke`); void refresh(); }
                        catch (e) { setError((e as Error).message); }
                      }} />
                    )}
                  </span></td>
                </tr>
                {editing === c.id && (
                  <tr className="edit-row"><td colSpan={7}>
                    <EditLimits code={c} onCancel={() => setEditing(null)} onSave={async (input) => {
                      await call("POST", `/codes/${c.id}/update`, input); setEditing(null); void refresh();
                    }} />
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
        {codes?.length === 0 && <p className="table-empty">No codes yet. Make the first one above.</p>}
      </div>

      <h2>Recent lab runs</h2>
      <div className="table-scroll">
        <table className="admin-table">
          <thead>
            <tr><th scope="col">When</th><th scope="col">Participant</th><th scope="col">Attack</th>
              <th scope="col">Defense</th><th scope="col">Code</th><th scope="col">Result</th>
              <th scope="col" className="num">Time</th><th scope="col" className="num">Cost</th></tr>
          </thead>
          <tbody>
            {runs?.runs.map((r, i) => (
              <tr key={i}>
                <td>{when(r.created_at)}</td>
                <td>{r.participant ?? "Unknown"}</td>
                <td>{attackTitle(r.attack)}</td>
                <td>{defenseTitle(r.defense)}</td>
                <td>{r.code_label}</td>
                <td>{r.status === "ok" ? "Finished" : r.status === "failed" ? "Failed" : "Running"}</td>
                <td className="num">{r.seconds ? `${r.seconds.toFixed(0)} s` : "–"}</td>
                <td className="num">{r.cost_usd != null ? `$${r.cost_usd.toFixed(3)}` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {runs?.runs.length === 0 && <p className="table-empty">No lab runs yet.</p>}
      </div>
    </div>
  );
}

function SignIn({ onSignIn, error }: { onSignIn: (t: string) => void; error: string | null }) {
  const [value, setValue] = useState("");
  return (
    <form className="signin" onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSignIn(value.trim()); }}>
      <h1>Access codes</h1>
      <p>Enter the admin password to make and manage codes for the attack lab.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <label>Admin password
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="current-password" autoFocus />
      </label>
      <button className="button" type="submit">Sign in</button>
    </form>
  );
}

interface CreateInput { label: string; max_runs: number; max_cost_usd: number; expires_in_days: number | null }

function CreateCode({ onCreate }: { onCreate: (input: CreateInput) => Promise<void> }) {
  const [label, setLabel] = useState("");
  const [runs, setRuns] = useState(5);
  const [cost, setCost] = useState(0.5);
  const [days, setDays] = useState("14");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <form className="panel" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setErr(null);
      try {
        await onCreate({ label, max_runs: runs, max_cost_usd: cost, expires_in_days: days === "never" ? null : Number(days) });
        setLabel("");
      } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
    }}>
      <h2>Make a code</h2>
      <label>Who it's for<input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} required
                                placeholder="For example, the course instructor" /></label>
      <div className="row3">
        <label>Runs<input type="number" min={1} max={100} value={runs} onChange={(e) => setRuns(Number(e.target.value))} required /></label>
        <label>Spending limit ($)<input type="number" min={0.05} max={50} step={0.05} value={cost}
                                        onChange={(e) => setCost(Number(e.target.value))} required /></label>
        <label>Expires
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="7">In a week</option><option value="14">In two weeks</option>
            <option value="30">In a month</option><option value="90">In three months</option>
            <option value="never">Never</option>
          </select>
        </label>
      </div>
      <p className="small">A lab run usually costs about four cents.</p>
      {err && <p className="error" role="alert">{err}</p>}
      <button className="button" type="submit" disabled={busy}>{busy ? "Making…" : "Make code"}</button>
    </form>
  );
}

function NewCode({ code, record, onDone }: { code: string; record: CodeRecord; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const site = window.location.origin;
  const message = `Here's your access code for the attack lab: ${code}\n\nOpen ${site}/lab, choose a participant, an attack, and a defense, and enter the code to run the agent live. It's good for ${record.max_runs} run${record.max_runs === 1 ? "" : "s"}${record.expires_at ? ` until ${new Date(record.expires_at).toLocaleDateString([], { month: "long", day: "numeric" })}` : ""}. All participants and notes are synthetic.`;
  return (
    <section className="panel panel-new" aria-live="polite">
      <h2>Code for {record.label}</h2>
      <p className="new-code"><code>{code}</code></p>
      <p className="small">Copy it now. It isn't stored and won't be shown again.</p>
      <textarea readOnly value={message} rows={6} aria-label="Message to send" />
      <div className="row-buttons">
        <button type="button" className="button" onClick={async () => {
          try { await navigator.clipboard.writeText(message); setCopied(true); } catch { setCopied(false); }
        }}>{copied ? "Copied" : "Copy message"}</button>
        <button type="button" className="button-quiet" onClick={onDone}>Done</button>
      </div>
    </section>
  );
}

function EditLimits({ code, onSave, onCancel }: {
  code: CodeRecord; onCancel: () => void;
  onSave: (input: { max_runs: number; max_cost_usd: number; expires: string }) => Promise<void>;
}) {
  const [runs, setRuns] = useState(Math.max(code.max_runs, code.runs_used + 1));
  const [cost, setCost] = useState(code.max_cost_usd);
  const [expires, setExpires] = useState(code.state === "expired" ? "14" : "keep");
  const [err, setErr] = useState<string | null>(null);
  return (
    <form className="edit" onSubmit={async (e) => {
      e.preventDefault(); setErr(null);
      try { await onSave({ max_runs: runs, max_cost_usd: cost, expires }); } catch (x) { setErr((x as Error).message); }
    }}>
      <label>Runs<input type="number" min={1} max={100} value={runs} onChange={(e) => setRuns(Number(e.target.value))} /></label>
      <label>Spending limit ($)<input type="number" min={0.05} max={50} step={0.05} value={cost} onChange={(e) => setCost(Number(e.target.value))} /></label>
      <label>Expires
        <select value={expires} onChange={(e) => setExpires(e.target.value)}>
          <option value="keep">Keep as is</option><option value="14">Two weeks from now</option>
          <option value="30">A month from now</option><option value="never">Never</option>
        </select>
      </label>
      <button className="button" type="submit">Save limits</button>
      <button type="button" className="button-quiet" onClick={onCancel}>Cancel</button>
      {err && <p className="error" role="alert">{err}</p>}
    </form>
  );
}

function RevokeButton({ label, onRevoke }: { label: string; onRevoke: () => Promise<void> }) {
  const [sure, setSure] = useState(false);
  if (!sure) return <button type="button" className="link-button danger" onClick={() => setSure(true)}>Turn off</button>;
  return (
    <span className="confirm">
      Turn off {label}'s code for good?{" "}
      <button type="button" className="link-button danger" onClick={() => { setSure(false); void onRevoke(); }}>Turn it off</button>{" "}
      <button type="button" className="link-button" onClick={() => setSure(false)}>Keep it</button>
    </span>
  );
}
