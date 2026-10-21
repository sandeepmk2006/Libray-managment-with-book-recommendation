// Privacy & fairness: what the system stores, how it is anonymised, and whether it treats groups equally.
import { api } from "../api.js";
import { $, barList, chart, css, esc, fmt, load } from "../ui.js";

export async function renderTrust(app) {
  app.innerHTML = `
    <h1 class="title">Privacy &amp; fairness</h1>
    <p class="lede">What leaves the gate log, how readers are protected, and whether the models treat every group the same way.</p>
    <div id="trust"></div>`;

  load($("#trust"), api.ethics, (r) => {
    const k = r.k_anonymity, f = r.fairness;
    const di = f.disparate_impact;
    const groups = Object.entries(f.late_model_parity);
    $("#trust").innerHTML = `
      <div class="ledger" style="grid-template-columns:repeat(4,minmax(0,1fr))">
        <div><div class="v">${r.consent.opted_in}</div><div class="k">Members allow personal picks</div></div>
        <div><div class="v">${r.consent.opted_out}</div><div class="k">Opted out</div></div>
        <div class="${k.after_generalisation.k < k.after_generalisation.threshold ? "alert" : ""}"><div class="v">k = ${k.after_generalisation.k}</div><div class="k">Smallest group after anonymising (was ${k.k})</div></div>
        <div class="${di < 0.8 ? "alert" : ""}"><div class="v">${fmt.n(di, 2)}</div><div class="k">Disparate impact, late-return model</div></div>
      </div>

      <div class="grid g2">
        <section class="panel"><h2>What an exported visit looks like</h2>
          <p class="muted" style="margin-top:0">Names are dropped, IDs become salted one-way tokens, year of study becomes a cohort, and times are rounded to the hour.</p>
          <div class="table-wrap"><table><thead><tr><th>Token</th><th>School</th><th>Cohort</th><th>Arrived</th><th>Stay</th></tr></thead>
          <tbody>${r.anonymised_sample.map((s) => `<tr><td class="muted" style="font-family:ui-monospace,monospace;font-size:12.5px">${s.token}</td><td>${s.department}</td><td>${s.cohort}</td><td>${s.entry_hour}</td><td>${s.stay_band}</td></tr>`).join("")}</tbody></table></div>
        </section>
        <section class="panel"><h2>Re-identification risk</h2>
          <p class="muted" style="margin-top:0">k-anonymity: every combination of ${k.quasi_identifiers.join(", ")} should match at least ${k.threshold} people, so nobody can be singled out.</p>
          <table><thead><tr><th></th><th class="r">Smallest group (k)</th><th class="r">Groups</th><th class="r">Groups below ${k.threshold}</th></tr></thead><tbody>
            <tr><td>Raw records</td><td class="r">${k.k}</td><td class="r">${k.groups}</td><td class="r">${k.violations}</td></tr>
            <tr class="best"><td>After generalising</td><td class="r">${k.after_generalisation.k}</td><td class="r">${k.after_generalisation.groups}</td><td class="r">${k.after_generalisation.violations}</td></tr></tbody></table>
          <p class="muted" style="font-size:13px">${esc(k.note)}</p>
        </section>

        <section class="panel"><h2>Late-return model, by gender</h2>
          <p class="muted" style="margin-top:0">Gender is not a model input. We still check the outcome: a group should not be flagged as "likely late" much more often than another.</p>
          <div class="chart-box short"><canvas id="parity"></canvas></div>
          <p style="font-size:14px">${di >= 0.8 ? `<span class="badge ok">Passes</span> the four-fifths rule` : `<span class="badge warn">Fails</span> the four-fifths rule`}: the less favoured group gets a favourable outcome at ${fmt.pct(di)} of the rate of the more favoured one.</p>
        </section>
        <section class="panel"><h2>Recommendation quality by group</h2>
          <p class="muted" style="margin-top:0">Share of each reader's top-10 picks that fall in genres they actually read. Large gaps would mean some groups get worse suggestions.</p>
          <h3>Gender</h3>${barList(Object.entries(f.recommendation_exposure_by_gender), { label: ([g, v]) => `${g === "F" ? "Women" : "Men"} (${v.n})`, value: ([, v]) => v.relevance, display: (v) => fmt.pct(v), max: 1 })}
          <h3 style="margin-top:16px">Department</h3>${barList(Object.entries(f.by_department), { label: ([g, v]) => `${g} (${v.n})`, value: ([, v]) => v.relevance, display: (v) => fmt.pct(v), max: 1 })}
        </section>
      </div>

      <section class="panel" style="margin-top:18px"><h2>Our commitments</h2>
        <ul style="margin:0;padding-left:20px;display:grid;gap:6px">${r.transparency.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></section>`;

    chart($("#parity"), {
      type: "bar",
      data: {
        labels: groups.map(([g]) => (g === "F" ? "Women" : "Men")),
        datasets: [
          { label: "Predicted on time", data: groups.map(([, v]) => v.favourable_rate), backgroundColor: css("--lamp") },
          { label: "Caught real late returns", data: groups.map(([, v]) => v.true_positive_rate), backgroundColor: css("--brass") },
          { label: "Accuracy", data: groups.map(([, v]) => v.accuracy), backgroundColor: "#2d5d8a" },
        ],
      },
      options: { indexAxis: "y", scales: { x: { min: 0, max: 1, ticks: { callback: (v) => `${v * 100}%` } }, y: { grid: { display: false } } } },
    });
  }, 500);
}
