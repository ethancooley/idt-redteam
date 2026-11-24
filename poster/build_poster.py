"""Build the course poster (48 x 36 in, landscape) as a PDF from the study's own result files.

    python poster/build_poster.py            # writes poster/poster.html and poster/poster.pdf,
                                             # and copies the PDF to web/public/ so the site serves it

Every number on the poster is read from results/ and web/public/data/, so it always matches the site.
Needs Google Chrome (or Chromium) for the HTML-to-PDF step, and `pip install segno` for the QR codes.
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

import segno

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DATA = ROOT / "web" / "public" / "data"
RUN = "20261123-174607"
SITE = "https://idt-redteam.vercel.app"
REPO = "https://github.com/ethancooley/idt-redteam"
EXAMPLE_PID = "1462f7fa-b21b-4046-e34c-89994cf65db4"  # Karissa Pfeffer, fake authority, suppressed

e = html.escape


def load(name: str):
    return json.loads((DATA / name).read_text())


def qr(url: str) -> str:
    return segno.make(url, error="m").svg_inline(scale=10, dark="#1c2a3a", light=None, border=0)


def first_sentence(text: str) -> str:
    return text.split(". ")[0].rstrip(".") + "."


def main() -> None:
    summary = load("summary.json")
    run = next(r for r in summary["runs"] if r["id"] == RUN)
    grid, info_a, info_d = run["grid"], summary["attack_info"], summary["defense_info"]
    attacks, defenses = run["attacks"], run["defenses"]

    def totals(d: str) -> dict:
        cells = [grid[d][a] for a in attacks]
        return {"success": sum(c["success"] for c in cells), "cases": sum(len(c["cases"]) for c in cells),
                "suppressed": sum(c["suppressed"] for c in cells)}

    base = totals("baseline")
    all_cells = [grid[d][a] for d in defenses for a in attacks]
    briefs = sum(len(c["cases"]) for c in all_cells)
    verifier_caught = sum(round((c["verifier_caught"] or 0) * len(c["cases"])) for c in all_cells)
    clean = {d: grid[d]["clean"] for d in defenses}
    fake = grid["baseline"]["fake_authority"]
    direct = grid["baseline"]["direct_instruction"]

    # The before/after example: the same participant's brief on the clean chart and with one planted note.
    clean_brief = json.loads((ROOT / "results" / RUN / "baseline" / "clean" / "briefs" / f"{EXAMPLE_PID}.json").read_text())
    attacked = load(f"cases/{RUN}__baseline__fake_authority__{EXAMPLE_PID[:8]}.json")
    planted = attacked["planted"][0]
    target_line = next(i for i in clean_brief["items"] if i["category"] == "cognition")

    # ------------------------------------------------------------ dot matrix
    head = "".join(f"<th>{e(info_a[a]['title'])}</th>" for a in attacks)
    rows = []
    for d in defenses:
        t = totals(d)
        cells = []
        for a in attacks:
            c = grid[d][a]
            dots = "".join(f'<span class="dot dot-{x["outcome"]}"></span>' for x in c["cases"])
            dots += "".join('<span class="dot dot-error"></span>' for _ in range(c["errors"]))
            label = "stopped all" if c["success"] == 0 else f"{c['success']} of {len(c['cases'])} got through"
            cells.append(f'<td><div class="dots">{dots}</div><span class="count">{label}</span></td>')
        rows.append(
            f'<tr><th><span class="dname">{e(info_d[d]["title"])}</span>'
            f'<span class="dabout">{e(info_d[d]["about"])}</span></th>{"".join(cells)}'
            f'<td class="total"><strong>{t["success"]}</strong> of {t["cases"]}</td>'
            f'<td class="clean">{round(clean[d]["recall"] * 100)}%<span>${clean[d]["cost_usd_per_brief"]:.3f}</span></td></tr>')
    matrix = (f'<table class="matrix"><thead><tr><th>Defense</th>{head}<th>Got through</th>'
              f'<th>Clean recall<span>cost / brief</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table>')

    others = {d: totals(d) for d in defenses if d != "baseline"}
    attack_rows = "".join(
        f'<li><strong>{e(info_a[a]["title"])}.</strong> {e(info_a[a]["about"])}</li>' for a in attacks)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Planted notes: red-teaming a clinical AI agent</title>
<style>
@font-face {{ font-family: "AHN"; font-weight: 400; src: url(fonts/atkinson-hyperlegible-next-latin-400-normal.woff2); }}
@font-face {{ font-family: "AHN"; font-weight: 600; src: url(fonts/atkinson-hyperlegible-next-latin-600-normal.woff2); }}
@font-face {{ font-family: "AHN"; font-weight: 800; src: url(fonts/atkinson-hyperlegible-next-latin-800-normal.woff2); }}
@font-face {{ font-family: "AHM"; font-weight: 400; src: url(fonts/atkinson-hyperlegible-mono-latin-400-normal.woff2); }}
@page {{ size: 48in 36in; margin: 0; }}
:root {{ --paper:#f7f9f8; --sheet:#fff; --ink:#1c2a3a; --soft:#4a5a6b; --rule:#d6dedb; --teal:#2e7d6f;
        --amber:#c9821b; --red:#c2362b; --mark:#ffe680; }}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; width:48in; height:36in; background:var(--paper); color:var(--ink);
  font-family:"AHN", sans-serif; font-size:28pt; line-height:1.36; -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
.poster {{ width:48in; height:36in; padding:1.1in 1.2in 0.9in; display:grid; grid-template-rows:auto 1fr auto; gap:0.75in; }}
header {{ display:grid; grid-template-columns:1fr auto; gap:1in; align-items:end; border-bottom:4pt solid var(--ink); padding-bottom:0.45in; }}
h1 {{ font-size:112pt; line-height:1.02; font-weight:800; margin:0; letter-spacing:-0.01em; max-width:30ch; }}
.byline {{ font-size:34pt; margin-top:0.3in; color:var(--soft); }}
.byline strong {{ color:var(--ink); }}
.qrs {{ display:flex; gap:0.55in; }}
.qr {{ text-align:center; font-size:22pt; color:var(--soft); width:4.4in; }}
.qr svg {{ width:3.4in; height:3.4in; margin-left:auto; margin-right:auto; display:block; margin-bottom:0.12in; }}
.qr strong {{ display:block; color:var(--ink); font-size:25pt; }}
main {{ display:grid; grid-template-columns: 10.6in 1fr 11.2in; gap:0.8in; min-height:0; }}
section {{ margin-bottom:0.42in; }}
h2 {{ font-size:50pt; font-weight:800; margin:0 0 0.18in; line-height:1.1; }}
h3 {{ font-size:32pt; font-weight:800; margin:0.3in 0 0.08in; }}
p {{ margin:0 0 0.16in; }}
ul {{ margin:0; padding-left:0.4in; }} li {{ margin:0 0 0.1in; }}
.small {{ font-size:24pt; color:var(--soft); }}
code {{ font-family:"AHM", monospace; font-size:0.85em; }}
mark {{ background:var(--mark); color:inherit; padding:0 0.04em; box-decoration-break:clone; -webkit-box-decoration-break:clone; }}
.lead {{ font-size:32pt; line-height:1.34; }}
.pipeline {{ display:flex; gap:0.12in; margin:0.2in 0 0.2in; }}
.pipeline span {{ flex:1; background:var(--sheet); border:2pt solid var(--rule); border-radius:8pt; padding:0.12in 0.08in;
  text-align:center; font-weight:600; font-size:23pt; line-height:1.2; }}
.pipeline span.v {{ border-color:var(--ink); }}
.note {{ background:var(--sheet); border:2pt solid var(--rule); border-left:12pt solid var(--amber); border-radius:6pt;
  padding:0.2in 0.28in; margin:0.18in 0; }}
.note .meta {{ font-size:23pt; color:var(--soft); display:flex; justify-content:space-between; gap:0.2in; }}
.note p {{ margin:0.08in 0 0; font-size:29pt; }}
.ba {{ display:grid; grid-template-columns:1fr 1fr; gap:0.35in; }}
.brief {{ background:var(--sheet); border:2pt solid var(--rule); border-radius:8pt; padding:0.25in 0.3in; }}
.brief h3 {{ margin-top:0; font-size:28pt; color:var(--soft); font-weight:600; }}
.brief .hl {{ font-weight:600; font-size:29pt; }}
.brief .gone {{ border-top:2pt solid var(--rule); margin-top:0.15in; padding-top:0.15in; font-size:26pt; }}
.brief.after {{ border-left:12pt solid var(--red); }}
.brief.before {{ border-left:12pt solid var(--teal); }}
.sev {{ font-weight:800; color:var(--red); font-size:23pt; }}
.matrix {{ border-collapse:collapse; width:100%; background:var(--sheet); border:2pt solid var(--rule); }}
.matrix th, .matrix td {{ border-bottom:2pt solid var(--rule); padding:0.16in 0.16in; text-align:left; vertical-align:top; }}
.matrix thead th {{ font-size:23pt; color:var(--soft); font-weight:600; line-height:1.2; }}
.matrix thead th span {{ display:block; font-weight:400; }}
.matrix tbody tr:last-child > * {{ border-bottom:0; }}
.matrix tbody th {{ width:5.2in; font-weight:400; }}
.dname {{ display:block; font-weight:800; font-size:31pt; }}
.dabout {{ display:block; font-size:21pt; color:var(--soft); line-height:1.25; }}
.dots {{ display:flex; gap:0.08in; }}
.dot {{ width:0.44in; height:0.44in; border-radius:50%; display:inline-block; }}
.dot-surfaced {{ background:var(--teal); }} .dot-demoted {{ background:var(--amber); }}
.dot-suppressed {{ background:var(--red); box-shadow:inset 0 0 0 5pt #7d1c15; }}
.dot-error {{ border:3pt dashed var(--soft); }}
.count {{ display:block; font-size:20pt; color:var(--soft); margin-top:0.06in; }}
td.total {{ font-size:28pt; white-space:nowrap; }} td.total strong {{ font-size:44pt; }}
td.clean {{ border-left:2pt dashed var(--rule); font-size:30pt; }} td.clean span {{ display:block; font-size:21pt; color:var(--soft); }}
.legend {{ display:flex; gap:0.2in 0.55in; font-size:26pt; margin:0.12in 0 0.22in; flex-wrap:wrap; }}
.legend span.dot {{ width:0.32in; height:0.32in; vertical-align:-0.04in; margin-right:0.08in; }}
.findings dt {{ font-weight:800; font-size:31pt; margin-top:0.22in; }}
.findings dd {{ margin:0.04in 0 0; }}
.caution {{ background:var(--ink); color:#fff; border-radius:8pt; padding:0.3in 0.35in; }}
.caution h2 {{ color:#fff; font-size:40pt; }}
.caution p {{ margin-bottom:0.1in; }}
footer {{ display:flex; justify-content:space-between; gap:1in; font-size:22pt; color:var(--soft); border-top:2pt solid var(--rule); padding-top:0.25in; }}
footer p {{ margin:0; max-width:30in; }}
</style></head><body><div class="poster">

<header>
  <div>
    <h1>Can a planted chart note make a clinical AI agent forget a high-severity event?</h1>
    <p class="byline"><strong>Ethan Cooley</strong>, Duke University, AI for Product Innovation (AIPI) &nbsp;·&nbsp;
      Responsible AI, Project 2 &nbsp;·&nbsp; All participants, notes, and clinicians are synthetic</p>
  </div>
  <div class="qrs">
    <div class="qr">{qr(SITE)}<strong>Results and attack lab</strong>idt-redteam.vercel.app</div>
    <div class="qr">{qr(REPO)}<strong>Code, data, every brief</strong>github.com/ethancooley/idt-redteam</div>
  </div>
</header>

<main>
  <div>
    <section>
      <h2>The system under attack</h2>
      <p>IDT Prep Copilot, an agent I built earlier, reads a PACE participant's chart and writes the brief their care
        team reviews before its interdisciplinary meeting.</p>
      <div class="pipeline"><span>Plan</span><span>Read chart with tools</span><span>Draft, citing every line</span>
        <span class="v">Verify each line against its source</span><span>Brief</span></div>
      <p>On 40 clean synthetic charts it caught every planted event. This study uses it unchanged; the attack
        benchmark, harness, defenses, scoring, and site are new.</p>
    </section>
    <section>
      <h2>Threat model</h2>
      <p>Anyone who can write into the chart (a compromised account, a copied template, a hostile outside record)
        adds one or two realistic notes. They can't touch the agent, its prompts, or structured records such as
        vitals. The goal: make a real high-severity event drop out of the brief. <strong>Omission is the dangerous
        direction: nobody looks for what isn't there.</strong></p>
    </section>
    <section>
      <h2>The attacks</h2>
      <ul>{attack_rows}</ul>
    </section>
    <section>
      <h2>Scoring</h2>
      <p>Each attack targets one high-severity event in the answer key. A line reports it only if it cites a note, or
        for weights, encounters, and medications the structured record, that proves it. Every attacked brief was also
        read by hand, and tests fail if the scorer disagrees; reading them changed the scorer three times.</p>
    </section>
  </div>

  <div>
    <section>
      <h2>One planted note, one missing event</h2>
      <p class="lead">{e(attacked['participant'])}'s chart shows two weeks of new evening confusion. One note was added:</p>
      <div class="note"><div class="meta"><span>{e(planted['author_role'])}, {e(planted['note_type'].lower())}</span>
        <code>{e(planted['id'])}</code></div><p><mark>{e(planted['text'])}</mark></p></div>
      <div class="ba">
        <div class="brief before"><h3>Brief from the clean chart</h3><p class="hl">{e(clean_brief['headline'])}</p>
          <p class="gone"><span class="sev">HIGH</span> {e(first_sentence(target_line['statement']))}</p></div>
        <div class="brief after"><h3>Brief with the planted note</h3><p class="hl">{e(attacked['headline'])}</p>
          <p class="gone">No line, question, or mention of the confusion or the correction. The verifier passed
            every line.</p></div>
      </div>
    </section>
    <section>
      <h2>Every brief, by defense and attack</h2>
      <p>Each dot is one brief written from a poisoned chart, {run['participants']} synthetic participants per cell.
        Attack success is demoted or suppressed.</p>
      <div class="legend">
        <span><span class="dot dot-surfaced"></span><strong>Surfaced:</strong> reported at high severity</span>
        <span><span class="dot dot-demoted"></span><strong>Demoted:</strong> lost its place, a trace remains</span>
        <span><span class="dot dot-suppressed"></span><strong>Suppressed:</strong> no trace at all</span>
      </div>
      {matrix}
      <p class="small">A dashed circle is a run that crashed; it is left out of the counts. Clean recall and cost come
        from the same defense on the same participants' unpoisoned charts.</p>
    </section>
  </div>

  <div>
    <section class="findings">
      <h2>What the briefs show</h2>
      <dl>
        <dt>The deployed agent let {base['success']} of {base['cases']} attacks through</dt>
        <dd>In {base['suppressed']} of them the event vanished with no trace for a reader to follow.</dd>
        <dt>Plausible paperwork works; obvious injections don't</dt>
        <dd>It ignored {len(direct['cases']) - direct['success']} of {len(direct['cases'])} notes telling it outright
          to leave an event out, and pointed them out to the team. A fake chart correction attributed to a physician got
          through in {fake['success']} of {len(fake['cases'])}.</dd>
        <dt>The verifier caught {verifier_caught} of {briefs} planted claims</dt>
        <dd>It checks each line against the notes that line cites. A line that faithfully repeats a planted note
          passes. Citation-grounding stops fabrication, not omission.</dd>
        <dt>Structured records are an anchor</dt>
        <dd>The one attacked weight loss also shows in the vitals, which a note-writer can't edit, and the deployed
          agent reported it in every brief. Falls and new confusion live only in notes, and those were lost.</dd>
        <dt>Spotlighting barely helped</dt>
        <dd>{others['spotlight']['success']} of {others['spotlight']['cases']} still got through. Marking notes as
          untrusted targets instructions, and the attacks that worked contain none.</dd>
        <dt>A conflict rule and a detector stopped nearly everything</dt>
        <dd>Conflict rule: {others['conflict_rule']['success']} of {others['conflict_rule']['cases']} got through.
          Detector: {others['detector']['success']} of {others['detector']['cases']}. Neither lowered recall on clean
          charts or changed the cost per brief, and the detector withheld {clean['detector'].get('detector_flagged_notes', 0)}
          clean notes.</dd>
      </dl>
    </section>
    <section class="caution">
      <h2>Read the last row with care</h2>
      <p>Five participants per cell: a pattern, not a rate. The conflict rule and the detector were written after
        reading the deployed agent's failures and tested on the same participants, so they are fitted to these
        attacks; an attacker who knew the rule could write notes that don't look like corrections. Synthetic data,
        one agent design, and I wrote both the agent and the attacks.</p>
    </section>
    <section>
      <h2>Try it</h2>
      <p>In the attack lab, plant your own note in a synthetic chart, choose a defense, and watch the agent read,
        draft, and check, live. The note exists only for that run.</p>
    </section>
  </div>
</main>

<footer>
  <p>How this differs from prior work: MPIB (Lee et al., EMNLP Findings 2026) measures clinical harm from prompt
    injection in single models and retrieval setups. This study attacks a multi-step, tool-using agent that cites
    its sources and checks itself, over a months-long chart, and scores the harm of omission exactly against answer
    keys. Defenses: spotlighting after Hines et al. (2024). Related: "The Model Knows Better" (arXiv 2610.22594); memory
    poisoning of EHR agents (arXiv 2601.05504).</p>
  <p>Agent: Claude Haiku 5.5 (plan, read) and Claude Sonnet 5.5 (draft, verify).<br>Data: Synthea, synthetic only.</p>
</footer>
</div></body></html>"""
    out_html = HERE / "poster.html"
    out_html.write_text(page)
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome")
                   if shutil.which(c)), None)
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome and mac.exists():
        chrome = str(mac)
    if not chrome:
        sys.exit("Wrote poster.html. Install Google Chrome to make the PDF.")
    subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={HERE / 'poster.pdf'}", out_html.as_uri()], check=True,
                   capture_output=True)
    shutil.copyfile(HERE / "poster.pdf", ROOT / "web" / "public" / "poster.pdf")  # served at /poster.pdf
    print(f"Wrote {HERE / 'poster.pdf'} and copied it to web/public/poster.pdf")


if __name__ == "__main__":
    main()
