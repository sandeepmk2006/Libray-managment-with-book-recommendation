// Insights: usage patterns, statistical tests, footfall forecast, late-return models, reader personas.
import { api } from "../api.js";
import { $, $$, barList, chart, css, esc, fmt, genreColor, load } from "../ui.js";

const TABS = [
  ["patterns", "Usage patterns"],
  ["tests", "Questions & evidence"],
  ["forecast", "Footfall forecast"],
  ["late", "Late returns"],
  ["personas", "Reader personas"],
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const palette = () => [css("--series-1"), css("--brass"), "#2d5d8a", css("--pencil"), "#7a3e65", "#5b7a2e", "#6b4f2a", "#3f4f8f"];

export async function renderInsights(app, tab = "patterns") {
  app.innerHTML = `
    <h1 class="title">Insights</h1>
    <p class="lede">What the gate log and loan history say about how the library is used, tested properly rather than eyeballed.</p>
    <div class="tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>
    <div id="tab"></div>`;
  $(".tabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (b) location.hash = `#/insights/${b.dataset.tab}`;
  });
  const views = { patterns, tests, forecast, late, personas };
  (views[tab] || patterns)($("#tab"));
}

// ---------------------------------------------------------------- patterns (EDA)
function patterns(el) {
  load(el, () => api.analytics("eda"), (d) => {
    el.innerHTML = `
      <div class="grid g2">
        <section class="panel span-2"><h2>When people come in <small>arrivals by weekday and hour</small></h2><div id="heat"></div></section>
        <section class="panel span-2"><h2>Daily visits</h2><div class="chart-box"><canvas id="daily"></canvas></div></section>
        <section class="panel"><h2>How long people stay <small>${d.outliers ? `${d.outliers.count} unusually long or short visits (IQR rule)` : ""}</small></h2><div class="chart-box"><canvas id="stay"></canvas></div></section>
        <section class="panel"><h2>Why they came</h2><div class="chart-box"><canvas id="purpose"></canvas></div></section>
        <section class="panel"><h2>Departments</h2><div class="table-wrap"><table><thead><tr><th>Department</th><th class="r">Visits</th><th class="r">Avg stay</th><th class="r">Loans</th><th class="r">Late</th></tr></thead>
          <tbody>${d.by_department.map((r) => `<tr><td>${r.department}</td><td class="r">${fmt.n(r.visits)}</td><td class="r">${fmt.mins(r.avg_stay)}</td><td class="r">${fmt.n(r.loans)}</td><td class="r">${fmt.pct(r.late_rate)}</td></tr>`).join("")}</tbody></table></div></section>
        <section class="panel"><h2>Most borrowed</h2><ol style="margin:0;padding-left:22px;display:grid;gap:4px">${d.top_books.slice(0, 10).map((b) => `<li><a href="#/catalog/${b.book_id}">${esc(b.title)}</a> <span class="muted">${b.loans} loans${b.avg_rating ? `, ${fmt.n(b.avg_rating, 1)}★` : ""}</span></li>`).join("")}</ol></section>
        <section class="panel"><h2>Genres <small>loans</small></h2>${barList(d.genre_popularity.slice(0, 12), { label: (r) => r.genre, value: (r) => r.loans })}</section>
        <section class="panel"><h2>What moves together <small>Pearson correlation, per member</small></h2><div id="corr"></div></section>
        <section class="panel span-2"><h2>Summary statistics</h2><div class="table-wrap" id="describe"></div></section>
        <section class="panel span-2"><h2>Data quality <small>missing values per table</small></h2><div id="missing"></div></section>
      </div>`;

    heatmap($("#heat"), d.weekday_hour);
    chart($("#daily"), {
      type: "line",
      data: { labels: d.daily.map((r) => fmt.date(r.date)), datasets: [
        { label: "Visits", data: d.daily.map((r) => r.visits), borderColor: css("--series-1"), backgroundColor: css("--series-1") + "22", fill: true, pointRadius: 0, tension: 0.25 },
        { label: "Different readers", data: d.daily.map((r) => r.unique_members), borderColor: css("--brass"), pointRadius: 0, tension: 0.25 },
      ] },
      options: { interaction: { mode: "index", intersect: false }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true } } },
    });
    const h = d.stay_histogram;
    chart($("#stay"), {
      type: "bar",
      data: { labels: h.counts.map((_, i) => `${Math.round(h.bins[i])}`), datasets: [{ data: h.counts, backgroundColor: css("--brass"), barPercentage: 1, categoryPercentage: 1 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: (c) => `${Math.round(h.bins[c[0].dataIndex])}–${Math.round(h.bins[c[0].dataIndex + 1])} min` } } },
        scales: { x: { title: { display: true, text: "minutes" }, grid: { display: false }, ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: true } } },
    });
    chart($("#purpose"), {
      type: "doughnut",
      data: { labels: d.by_purpose.map((r) => r.purpose ?? "Not recorded"), datasets: [{ data: d.by_purpose.map((r) => r.count), backgroundColor: palette(), borderColor: css("--sheet") }] },
      options: { cutout: "62%", plugins: { legend: { position: "right" } } },
    });
    corrMatrix($("#corr"), d.correlation);

    const metrics = Object.entries(d.describe);
    const cols = ["count", "mean", "median", "std", "var", "min", "q1", "q3", "max", "skew", "kurtosis"];
    $("#describe").innerHTML = `<table><thead><tr><th>Measure</th>${cols.map((c) => `<th class="r">${c === "var" ? "variance" : c === "std" ? "std dev" : c}</th>`).join("")}</tr></thead>
      <tbody>${metrics.map(([name, s]) => `<tr><td>${name.replace(/_/g, " ")}</td>${cols.map((c) => `<td class="r">${s[c] == null ? "–" : fmt.n(s[c], c === "count" ? 0 : 2)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    $("#missing").innerHTML = `<div class="grid g3">${Object.entries(d.summary).map(([t, s]) => {
      const miss = Object.entries(s.missing || {}).filter(([, v]) => v > 0);
      return `<div><h3>${t} <span class="muted" style="font-weight:400">${fmt.n(s.rows)} rows × ${s.cols} cols</span></h3>
        ${miss.length ? miss.map(([c, v]) => `<div class="muted" style="font-size:13.5px">${c}: <b style="color:var(--ink)">${fmt.n(v)}</b> missing (${fmt.pct(v / s.rows, 1)})</div>`).join("") : `<div class="muted" style="font-size:13.5px">Complete</div>`}</div>`;
    }).join("")}</div>
    <p class="muted" style="font-size:13px">Missing exit times are readers still inside or returns not yet made; missing purposes are left as “Not recorded” rather than guessed.</p>`;
  }, 600);
}

function heatmap(el, matrix) {
  if (!window.d3) return (el.innerHTML = `<div class="empty">Heatmap needs an internet connection.</div>`);
  const hours = d3.range(7, 22), cell = 100 / hours.length;
  const max = d3.max(matrix.flat());
  const color = d3.scaleSequential([0, max], d3.interpolateRgb(css("--paper"), css("--series-1")));
  el.innerHTML = `<div style="display:grid;grid-template-columns:40px 1fr;gap:4px;font-size:12px">
    ${matrix.map((row, d) => `<span class="muted" style="align-self:center">${DAYS[d]}</span>
      <div style="display:grid;grid-template-columns:repeat(${hours.length},1fr);gap:2px">${hours.map((h) => `<div title="${DAYS[d]} ${fmt.hour(h)}: ${row[h]} arrivals" style="height:26px;border-radius:2px;background:${color(row[h])}"></div>`).join("")}</div>`).join("")}
    <span></span><div style="display:grid;grid-template-columns:repeat(${hours.length},1fr)" class="muted">${hours.map((h) => `<span>${h % 2 ? "" : h}</span>`).join("")}</div></div>`;
}

function corrMatrix(el, { columns, matrix }) {
  const color = (v) => (v == null ? "transparent" : v >= 0 ? `rgba(185,133,47,${Math.abs(v)})` : `rgba(45,93,138,${Math.abs(v)})`);
  el.innerHTML = `<div class="table-wrap"><table style="font-size:12.5px"><thead><tr><th></th>${columns.map((c) => `<th class="r">${c.replace(/_/g, " ")}</th>`).join("")}</tr></thead>
    <tbody>${matrix.map((row, i) => `<tr><td>${columns[i].replace(/_/g, " ")}</td>${row.map((v) => `<td class="r" style="background:${color(v)}">${v == null ? "–" : v.toFixed(2)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="muted" style="font-size:12.5px">Brass = rise together, blue = one rises as the other falls.</p>`;
}

// ---------------------------------------------------------------- hypothesis tests
function tests(el) {
  load(el, () => api.analytics("hypothesis"), (d) => {
    el.innerHTML = `
      <p class="muted" style="max-width:70ch;margin-top:0">Each card asks a real question about the library, states what we'd expect if nothing interesting were going on (H₀), runs the right test, and says what it means. Significance level α = 0.05.</p>
      <div class="grid g2">${d.tests.map((t) => {
        const reject = t.decision.startsWith("Reject");
        return `<article class="panel test ${reject ? "reject" : ""}">
          <h3 style="font-size:16px">${esc(t.question || t.name)}</h3>
          <dl><dt>H₀</dt><dd>${esc(t.h0)}</dd><dt>H₁</dt><dd>${esc(t.h1)}</dd></dl>
          <div class="stats"><span>${esc(t.test)}</span><span>statistic <b>${fmt.n(t.statistic, 3)}</b></span><span>p <b>${fmt.p(t.p_value)}</b></span>${t.effect_size != null ? `<span>effect size <b>${fmt.n(t.effect_size, 3)}</b></span>` : ""}</div>
          <p style="margin:6px 0"><span class="badge ${reject ? "reject" : "keep"}">${t.decision}</span></p>
          <p style="margin:0">${esc(t.interpretation)}</p></article>`;
      }).join("")}</div>
      <section class="panel" style="margin-top:18px"><h2>How sure are we? <small>95% confidence intervals</small></h2><div id="ci"></div></section>`;

    $("#ci").innerHTML = d.confidence_intervals.map((c) => {
      const span = c.high - c.low || 1, pad = span * 0.6, lo = c.low - pad, hi = c.high + pad;
      const x = (v) => ((v - lo) / (hi - lo)) * 100;
      return `<div style="display:grid;grid-template-columns:minmax(120px,220px) 1fr 180px;gap:14px;align-items:center;padding:10px 0;border-bottom:1px dashed var(--rule)">
        <span>${esc({ mean_stay_min: "Average stay (minutes)", mean_rating: "Average book rating", late_rate: "Share of late returns" }[c.metric] || c.metric)}</span>
        <div style="position:relative;height:18px"><div style="position:absolute;top:8px;left:${x(c.low)}%;width:${x(c.high) - x(c.low)}%;height:3px;background:var(--brass)"></div>
          <div style="position:absolute;top:3px;left:calc(${x(c.mean)}% - 6px);width:12px;height:12px;border-radius:50%;background:var(--lamp);border:2px solid var(--sheet)"></div></div>
        <span class="num muted">${fmt.n(c.mean, 3)} <small>[${fmt.n(c.low, 3)}, ${fmt.n(c.high, 3)}]</small></span></div>`;
    }).join("");
  }, 500);
}

// ---------------------------------------------------------------- regression forecast
function forecast(el) {
  load(el, () => api.analytics("forecast"), (d) => {
    el.innerHTML = `
      <p class="muted" style="max-width:70ch;margin-top:0">How many people will walk in each hour? Three regression models learn from past weeks and are judged on the most recent days they never saw.</p>
      <div class="grid g-wide">
        <section class="panel"><h2>Predicted vs actual <small>held-out days</small></h2><div class="chart-box tall"><canvas id="avp"></canvas></div></section>
        <section class="panel"><h2>Model comparison</h2><table><thead><tr><th>Model</th><th class="r">R²</th><th class="r">MAE</th><th class="r">RMSE</th></tr></thead>
          <tbody>${d.models.map((m) => `<tr class="${m.name === d.best ? "best" : ""}"><td>${esc(m.name)}</td><td class="r">${fmt.n(m.r2, 3)}</td><td class="r">${fmt.n(m.mae, 2)}</td><td class="r">${fmt.n(m.rmse, 2)}</td></tr>`).join("")}</tbody></table>
          <p class="muted" style="font-size:13px">R² is the share of hour-to-hour variation explained (1 is perfect). MAE and RMSE are typical errors in visitors per hour. The highlighted model is used for the forecast.</p>
          <div id="coef"></div></section>
        <section class="panel span-2" style="grid-column:1/-1"><h2>Next 24 hours <small>${esc(d.best)}</small></h2><div class="chart-box"><canvas id="next"></canvas></div></section>
      </div>`;
    const avp = d.actual_vs_pred;
    const keys = Object.keys(avp[0] || {}).filter((k) => !["x", "actual"].includes(k));
    chart($("#avp"), {
      type: "line",
      data: { labels: avp.map((r) => (typeof r.x === "string" && r.x.includes("T") ? fmt.dateTime(r.x) : r.x)), datasets: [
        { label: "Actual", data: avp.map((r) => r.actual), borderColor: css("--ink"), backgroundColor: css("--ink"), pointRadius: 2, borderWidth: 2, tension: 0.2 },
        ...keys.map((k, i) => ({ label: k[0].toUpperCase() + k.slice(1), data: avp.map((r) => r[k]), borderColor: palette()[(i + 1) % 8], pointRadius: 0, borderDash: i === 0 ? [4, 4] : [], tension: 0.2 })),
      ] },
      options: { interaction: { mode: "index", intersect: false }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: true, title: { display: true, text: "arrivals / hour" } } } },
    });
    chart($("#next"), {
      type: "bar",
      data: { labels: d.next_24h.map((r) => fmt.dateTime(r.hour_iso)), datasets: [{ data: d.next_24h.map((r) => r.predicted), backgroundColor: css("--brass"), borderRadius: 3 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { beginAtZero: true } } },
    });
    const withCoef = d.models.find((m) => m.name === d.best && m.coefficients) || d.models.find((m) => m.coefficients);
    if (withCoef) {
      const rows = Object.entries(withCoef.coefficients).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 8);
      $("#coef").innerHTML = `<h3 style="margin-top:16px">${esc(withCoef.name)} coefficients</h3>${barList(rows, { label: (r) => r[0].replace(/_/g, " "), value: (r) => Math.abs(r[1]), display: (v) => fmt.n(v, 2) })}`;
    }
  }, 500);
}

// ---------------------------------------------------------------- classification
function late(el) {
  load(el, () => Promise.all([api.analytics("classify"), api.members("", 500), api.books()]), ([d, members, books]) => {
    const total = d.class_balance.late + d.class_balance.on_time;
    el.innerHTML = `
      <p class="muted" style="max-width:70ch;margin-top:0">Which loans will come back late? Four classifiers learn from ${fmt.n(total)} past returns (${fmt.pct(d.class_balance.late / total)} were late) using only what was known when the book was issued.</p>
      <section class="panel" style="margin-bottom:18px"><h2>Check a loan before issuing it</h2>
        <form class="row" id="risk-form">
          <label class="field" style="flex:1;min-width:200px">Member<select id="risk-m">${members.map((m) => `<option value="${m.member_id}">${esc(m.name)} (${m.member_id})</option>`).join("")}</select></label>
          <label class="field" style="flex:1;min-width:200px">Book<select id="risk-b">${books.map((b) => `<option value="${b.book_id}">${esc(b.title)}</option>`).join("")}</select></label>
          <button class="btn">Estimate risk</button></form>
        <div id="risk" style="margin-top:14px"></div></section>
      <div class="grid g2">
        <section class="panel span-2"><h2>Model comparison <small>held-out test set, plus 5-fold cross-validation</small></h2><div class="table-wrap"><table>
          <thead><tr><th>Model</th><th class="r">Accuracy</th><th class="r">Precision</th><th class="r">Recall</th><th class="r">F1</th><th class="r">ROC AUC</th><th class="r">CV mean ± sd</th></tr></thead>
          <tbody>${d.models.map((m) => `<tr class="${m.name === d.best ? "best" : ""}"><td>${esc(m.name)}</td><td class="r">${fmt.n(m.accuracy, 3)}</td><td class="r">${fmt.n(m.precision, 3)}</td><td class="r">${fmt.n(m.recall, 3)}</td><td class="r">${fmt.n(m.f1, 3)}</td><td class="r">${fmt.n(m.roc_auc, 3)}</td><td class="r">${fmt.n(m.cv_mean, 3)} ± ${fmt.n(m.cv_std, 3)}</td></tr>`).join("")}</tbody></table></div></section>
        <section class="panel"><h2>ROC curves</h2><div class="chart-box tall"><canvas id="roc"></canvas></div></section>
        <section class="panel"><h2>What drives lateness</h2>${barList(d.feature_importance.slice(0, 10), { label: (r) => r.feature.replace(/_/g, " "), value: (r) => r.importance, display: (v) => fmt.n(v, 3) })}</section>
        <section class="panel span-2"><h2>Confusion matrices</h2><div class="grid g3" id="cms" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))"></div></section>
        <section class="panel span-2"><h2>The decision tree, written out</h2><pre class="rules">${esc(d.tree_rules)}</pre></section>
      </div>`;

    chart($("#roc"), {
      type: "scatter",
      data: { datasets: [
        ...Object.entries(d.roc).map(([name, r], i) => ({ label: name, data: r.fpr.map((x, j) => ({ x, y: r.tpr[j] })), showLine: true, borderColor: palette()[i], backgroundColor: palette()[i], pointRadius: 0, borderWidth: 2 })),
        { label: "Chance", data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], showLine: true, borderColor: css("--rule"), borderDash: [4, 4], pointRadius: 0 },
      ] },
      options: { scales: { x: { min: 0, max: 1, title: { display: true, text: "False positive rate" } }, y: { min: 0, max: 1, title: { display: true, text: "True positive rate" } } } },
    });
    $("#cms").innerHTML = d.models.map((m) => {
      const [[tn, fp], [fn, tp]] = m.confusion, max = Math.max(tn, fp, fn, tp);
      const cell = (v, good) => `<div style="padding:12px;text-align:center;border-radius:4px;background:${good ? `rgba(47,122,85,${0.15 + 0.6 * v / max})` : `rgba(180,68,44,${0.1 + 0.6 * v / max})`}"><b>${v}</b></div>`;
      return `<div><h3>${esc(m.name)}</h3><div style="display:grid;grid-template-columns:auto 1fr 1fr;gap:4px;font-size:12.5px;align-items:center">
        <span></span><span class="muted" style="text-align:center">pred. on time</span><span class="muted" style="text-align:center">pred. late</span>
        <span class="muted">on time</span>${cell(tn, true)}${cell(fp, false)}<span class="muted">late</span>${cell(fn, false)}${cell(tp, true)}</div></div>`;
    }).join("");

    $("#risk-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const out = $("#risk");
      out.innerHTML = `<div class="skeleton" style="height:60px"></div>`;
      try {
        const r = await api.predictLate($("#risk-m").value, +$("#risk-b").value);
        const p = r.probability;
        out.innerHTML = `<div class="grid g2" style="align-items:center">
          <div><div style="font:400 48px/1 var(--font-display);color:${p > 0.5 ? "var(--pencil)" : "var(--ok)"}">${fmt.pct(p)}</div>
            <div class="muted">chance this loan comes back late · <b>${esc(r.label)}</b></div>
            <div class="score" style="margin-top:10px;height:8px"><span style="width:${p * 100}%;background:${p > 0.5 ? "var(--pencil)" : "var(--ok)"}"></span></div></div>
          <div><h3>Why</h3>${r.top_factors.map((f) => `<div style="display:flex;justify-content:space-between;font-size:14px;padding:3px 0;border-bottom:1px dashed var(--rule)"><span>${esc(f.feature.replace(/_/g, " "))}</span><span class="num" style="color:${f.contribution > 0 ? "var(--pencil)" : "var(--ok)"}">${f.contribution > 0 ? "raises" : "lowers"} risk ${fmt.n(Math.abs(f.contribution), 2)}</span></div>`).join("")}</div></div>`;
      } catch (err) { out.innerHTML = `<div class="error-box">${esc(err.message)}</div>`; }
    });
  }, 600);
}

// ---------------------------------------------------------------- clustering
function personas(el) {
  load(el, () => api.analytics("clusters"), (d) => {
    const k = d.kmeans, colors = palette();
    const featureCols = d.features;
    el.innerHTML = `
      <p class="muted" style="max-width:70ch;margin-top:0">Members grouped by how they use the library — ${featureCols.map((f) => f.replace(/_/g, " ")).join(", ")}. No labels were given; the groups emerge from the data (k-means, k = ${d.chosen_k}, chosen by silhouette score).</p>
      <div class="grid g3" style="margin-bottom:18px">${k.centroids_profile.map((c) => `
        <article class="panel persona" style="--c:${colors[c.cluster % 8]}">
          <h3>${esc(c.persona)}</h3><p class="muted" style="margin:2px 0 10px">${c.size} members</p>
          <div style="font-size:13.5px;display:grid;gap:2px">${featureCols.map((f) => c[f] != null ? `<div style="display:flex;justify-content:space-between"><span class="muted">${f.replace(/_/g, " ")}</span><span class="num">${fmt.n(c[f], 2)}</span></div>` : "").join("")}</div>
        </article>`).join("")}</div>
      <div class="grid g2">
        <section class="panel"><h2>Members on a map <small>PCA projection to two dimensions</small></h2><div class="chart-box tall"><canvas id="pca"></canvas></div></section>
        <section class="panel"><h2>Choosing the number of groups</h2><div class="chart-box tall"><canvas id="elbow"></canvas></div></section>
        <section class="panel span-2"><h2>Second opinion: hierarchical clustering</h2>
          <p class="muted" style="margin-top:0">Agglomerative clustering (Ward linkage) builds groups bottom-up. Silhouette ${fmt.n(d.agglomerative.silhouette, 3)}; agreement with k-means (adjusted Rand index) ${fmt.n(d.agglomerative.agreement_ari, 3)}.</p>
          <div id="dendro" style="height:300px"></div></section>
      </div>`;

    const groups = [...new Set(k.points.map((p) => p.cluster))].sort();
    const name = Object.fromEntries(k.centroids_profile.map((c) => [c.cluster, c.persona]));
    chart($("#pca"), {
      type: "scatter",
      data: { datasets: groups.map((g) => ({ label: name[g] ?? `Group ${g}`, data: k.points.filter((p) => p.cluster === g).map((p) => ({ x: p.x, y: p.y, id: p.member_id })), backgroundColor: colors[g % 8] + "cc", pointRadius: 3.5 })) },
      options: { plugins: { tooltip: { callbacks: { label: (c) => c.raw.id } } }, onClick: (e, els, ch) => { if (els[0]) location.hash = `#/members/${ch.data.datasets[els[0].datasetIndex].data[els[0].index].id}`; },
        scales: { x: { title: { display: true, text: "component 1" } }, y: { title: { display: true, text: "component 2" } } } },
    });
    chart($("#elbow"), {
      data: { labels: d.elbow.map((r) => r.k), datasets: [
        { type: "line", label: "Inertia (lower is tighter)", data: d.elbow.map((r) => r.inertia), borderColor: css("--series-1"), yAxisID: "y" },
        { type: "bar", label: "Silhouette (higher is better)", data: d.elbow.map((r) => r.silhouette), backgroundColor: d.elbow.map((r) => (r.k === d.chosen_k ? css("--brass") : css("--rule"))), yAxisID: "y1" },
      ] },
      options: { scales: { x: { title: { display: true, text: "k" } }, y: { position: "left" }, y1: { position: "right", grid: { display: false }, beginAtZero: true } } },
    });
    dendrogram($("#dendro"), d.agglomerative.dendrogram);
  }, 600);
}

function dendrogram(el, dg) {
  if (!window.d3 || !dg) return;
  const { width } = el.getBoundingClientRect(), height = 300, m = { t: 10, r: 10, b: 40, l: 40 };
  const xs = dg.icoord.flat(), ys = dg.dcoord.flat();
  const x = d3.scaleLinear([d3.min(xs), d3.max(xs)], [m.l, width - m.r]);
  const y = d3.scaleLinear([0, d3.max(ys)], [height - m.b, m.t]);
  const svg = d3.select(el).append("svg").attr("width", width).attr("height", height);
  svg.append("g").selectAll("path").data(dg.icoord.map((ic, i) => ic.map((xv, j) => [x(xv), y(dg.dcoord[i][j])])))
    .join("path").attr("d", d3.line()).attr("fill", "none").attr("stroke", css("--series-1")).attr("stroke-width", 1.4);
  svg.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5)).attr("color", css("--ink-soft"));
  const labels = dg.labels || dg.ivl || [];
  svg.append("g").selectAll("text").data(labels).join("text")
    .attr("x", (_, i) => x(5 + i * 10)).attr("y", height - m.b + 14).attr("text-anchor", "middle").attr("font-size", 10).attr("fill", css("--ink-soft")).text((t) => t);
}
