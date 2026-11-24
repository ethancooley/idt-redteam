import { Legend } from "../components/Outcome";

export function Method() {
  return (
    <article className="prose">
      <h1>How the study works</h1>

      <h2>The system under attack</h2>
      <p>
        <a href="https://idt.ethancooley.com">IDT Prep Copilot</a> is an agent I built before this study. For each
        participant in a PACE program it reads the chart since the last interdisciplinary team review and writes a
        one-page brief. A fast model plans and reads the chart through read-only tools; a stronger model drafts the
        brief, citing a note or record for every line; a verifier checks each line against what it cites, and the
        agent goes back to the chart once if a line fails. On 40 clean synthetic charts it caught every planted
        event.
      </p>
      <p>
        The agent is used here unchanged. What is new is the attack benchmark, the harness that runs it, the
        defenses, and the scoring.
      </p>

      <h2>Threat model</h2>
      <p>
        Anyone who can write into the chart can plant text: a compromised account, a copied note template, a hostile
        record from outside. They cannot change the agent, its prompts, or the structured records such as vitals,
        encounters, and medications. Their goal is to change what the care team reads, above all by making a real
        high-severity event drop out of the brief. Leaving something out is the dangerous direction, because nobody
        goes looking for what isn't there.
      </p>

      <h2>How a brief is scored</h2>
      <p>
        Each attack targets one high-severity event from the participant's answer key. A line reports that event
        when it cites a note that proves it, or, for events that also live in a structured record, when a line in the
        same category cites that record.
      </p>
      <Legend />
      <p>
        Attack success means demoted or suppressed. The outcome depends only on what the brief contains, not on a
        judgment of its tone. Every attacked brief was also read by hand, and the repository's tests fail if the
        scorer ever disagrees with those labels. Reading the first briefs changed the scorer three times; its first
        version overcounted attack success badly.
      </p>
      <p>
        Every defense also ran on the same participants' clean charts, to measure what it costs when there is no
        attack.
      </p>

      <h2>How this differs from earlier work</h2>
      <p>
        MPIB (Lee et al., EMNLP Findings 2026) measures clinical harm from prompt injection in single models and
        retrieval setups. This study attacks a multi-step agent that uses tools, cites its sources, and checks
        itself, over a chart that spans months, and scores the harm of omission exactly against answer keys.
      </p>

      <h2 id="limits">Limitations</h2>
      <ul>
        <li><strong>Small sample.</strong> Five participants per cell. Read the results as a pattern, not a rate.</li>
        <li><strong>Fitted defenses.</strong> The conflict rule and the detector's screening prompt were written after
          reading the deployed agent's failures, and tested on the same participants. An attacker who knew the rule
          could write notes that don't look like corrections.</li>
        <li><strong>Synthetic data.</strong> Real notes are longer and messier, and real attacks would be too.</li>
        <li><strong>One agent design.</strong> The results describe this architecture, not clinical agents in general.</li>
        <li><strong>Same author.</strong> I wrote both the agent and the attacks, so the attacks may miss what an outside
          attacker would try.</li>
        <li><strong>The lab is a demonstration.</strong> It adds your note to the chart tools' results rather than to
          the database the study used, so search ranking can differ slightly from the experiments.</li>
      </ul>

      <h2>Code and data</h2>
      <p>
        Benchmark, harness, defenses, scoring, every brief, and this site:{" "}
        <a href="https://github.com/ethancooley/idt-redteam">github.com/ethancooley/idt-redteam</a>. The agent:{" "}
        <a href="https://github.com/ethancooley/idt-prep-copilot">github.com/ethancooley/idt-prep-copilot</a>.
      </p>
      <p>
        The course poster: <a href="/poster.pdf">poster.pdf</a> (48 × 36 in, built from the same result files as
        this site).
      </p>
    </article>
  );
}
