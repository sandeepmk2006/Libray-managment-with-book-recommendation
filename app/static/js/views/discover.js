// Discover: personalised picks for a member, with method switcher, reasons, taste profile and scorecard.
import { api } from "../api.js";
import { $, chart, css, esc, fmt, genreColor, load, memberPicker } from "../ui.js";
import { bookCard, openBook } from "./catalog.js";

const METHODS = [
  ["hybrid", "Best blend", "Mixes every approach below, then spreads picks across themes so the list isn't ten copies of one idea."],
  ["content", "Similar books", "Matches the words, themes and genres of what this reader already enjoyed."],
  ["user_cf", "Readers like them", "Finds members with overlapping ratings and borrows their favourites."],
  ["item_cf", "Often read together", "Books that tend to be borrowed and rated by the same people."],
  ["svd", "Hidden tastes", "Learns latent taste factors from the whole ratings table (matrix factorisation)."],
  ["popular", "Library favourites", "Highest-rated, most-borrowed titles. Used for new members and anyone who opted out."],
];

export async function renderDiscover(app, memberId) {
  let method = "hybrid";
  let current = memberId || null;
  app.innerHTML = `
    <h1 class="title">Discover</h1>
    <p class="lede">Pick a reader to see what they might borrow next, and why. Switch approaches to compare how each one thinks.</p>
    <div class="row" style="margin-bottom:16px">
      <label class="field" style="flex:1;max-width:360px">Reader<input id="who" placeholder="Name or member ID" value="${esc(current || "")}"></label>
      <button class="btn ghost" id="surprise" type="button">Pick a random reader</button>
    </div>
    <div class="chips" id="methods" role="group" aria-label="Recommendation approach">
      ${METHODS.map(([k, label]) => `<button class="chip" type="button" data-m="${k}" aria-pressed="${k === method}">${label}</button>`).join("")}
    </div>
    <p class="muted" id="method-note" style="margin:10px 0 22px;max-width:70ch"></p>
    <div class="grid g-wide">
      <section id="recs"><div class="empty">Choose a reader above to see their shelf.</div></section>
      <section class="grid" style="align-content:start">
        <div class="panel" id="profile"><h2>Reading taste</h2><p class="muted">The genre mix of everything this reader has borrowed.</p><div class="chart-box"><canvas id="taste"></canvas></div></div>
      </section>
    </div>
    <section class="panel" style="margin-top:22px">
      <h2>How well does each approach work? <small>tested on books members actually borrowed later</small></h2>
      <div id="scorecard"></div>
    </section>`;

  const note = () => ($("#method-note").textContent = METHODS.find((m) => m[0] === method)[2]);
  note();
  let tasteChart = null;

  async function show() {
    if (!current) return;
    history.replaceState(null, "", `#/discover/${current}`);
    await load($("#recs"), () => Promise.all([api.recommend(current, method, 10), api.member(current)]), ([rec, profile]) => {
      const m = profile.member;
      $("#recs").innerHTML = `
        <h2>${esc(m.name)} <small>${m.department}${m.year ? `, year ${m.year}` : ", faculty"} · ${profile.stats.loans} books borrowed${rec.cold_start ? " · new reader" : ""}</small></h2>
        ${m.consent ? "" : `<p class="badge warn" style="margin-bottom:14px">Opted out of personalisation, showing library favourites only</p>`}
        <div class="shelf">${rec.items.map((it) => bookCard(it.book, `
          <div class="score" title="Match ${Math.round(it.score * 100)}%"><span style="width:${it.score * 100}%"></span></div>
          <div class="chips" style="margin-top:6px">${it.reasons.map((r) => `<span class="reason">${esc(r)}</span>`).join("")}</div>`)).join("")}</div>`;

      const taste = Object.entries(profile.taste).slice(0, 8);
      if (tasteChart) tasteChart.destroy();
      tasteChart = taste.length > 2 ? chart($("#taste"), {
        type: "radar",
        data: { labels: taste.map((t) => t[0]), datasets: [{ data: taste.map((t) => t[1] * 100), backgroundColor: css("--brass") + "40", borderColor: css("--brass"), pointBackgroundColor: css("--brass") }] },
        options: { plugins: { legend: { display: false } }, scales: { r: { beginAtZero: true, ticks: { display: false }, grid: { color: css("--rule") }, angleLines: { color: css("--rule") }, pointLabels: { font: { size: 11 } } } } },
      }) : ($("#taste").parentElement.innerHTML = `<div class="empty">Not enough borrowing history yet.</div>`, null);
    }, 420);
  }

  memberPicker($("#who"), (id) => { current = id; show(); });
  $("#methods").addEventListener("click", (e) => {
    const c = e.target.closest("[data-m]");
    if (!c) return;
    method = c.dataset.m;
    document.querySelectorAll("#methods .chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
    note();
    show();
  });
  $("#surprise").addEventListener("click", async () => {
    const all = await api.members("", 500);
    const pick = all.filter((m) => m.loans >= 4);
    current = pick[Math.floor(Math.random() * pick.length)].member_id;
    $("#who").value = current;
    show();
  });
  app.addEventListener("click", (e) => {
    const b = e.target.closest(".book[data-book]");
    if (b) openBook(b.dataset.book);
  });

  // Scorecard
  load($("#scorecard"), api.evaluate, (ev) => {
    const names = Object.fromEntries(METHODS.map(([k, l]) => [k, l]));
    const rows = Object.entries(ev.methods);
    const best = rows.reduce((a, b) => (b[1].ndcg > a[1].ndcg ? b : a))[0];
    $("#scorecard").innerHTML = `
      <div class="grid">
        <div class="chart-box tall"><canvas id="eval-chart"></canvas></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Approach</th><th class="r">Precision@${ev.k}</th><th class="r">Recall@${ev.k}</th><th class="r">NDCG</th><th class="r">Hit rate</th><th class="r">Coverage</th><th class="r">Variety</th><th class="r">RMSE</th></tr></thead>
          <tbody>${rows.map(([k, m]) => `<tr class="${k === best ? "best" : ""}"><td>${names[k]}</td>
            <td class="r">${fmt.n(m.precision, 3)}</td><td class="r">${fmt.n(m.recall, 3)}</td><td class="r">${fmt.n(m.ndcg, 3)}</td>
            <td class="r">${fmt.pct(m.hit_rate)}</td><td class="r">${fmt.pct(m.coverage)}</td><td class="r">${fmt.n(m.diversity, 2)}</td><td class="r">${m.rmse == null ? "–" : fmt.n(m.rmse, 3)}</td></tr>`).join("")}</tbody>
        </table></div>
      </div>
      <p class="muted" style="font-size:13px">${esc(ev.protocol)} ${ev.users_evaluated} members tested. Highlighted row ranks best on NDCG. Variety is the average dissimilarity between books in one list; RMSE is the rating prediction error, where the approach predicts ratings.</p>`;
    const metrics = ["precision", "recall", "ndcg", "hit_rate"];
    const colors = [css("--lamp"), css("--brass"), "#2d5d8a", css("--pencil")];
    chart($("#eval-chart"), {
      type: "bar",
      data: { labels: rows.map(([k]) => names[k]), datasets: metrics.map((m, i) => ({ label: m.replace("_", " "), data: rows.map(([, v]) => v[m]), backgroundColor: colors[i], borderRadius: 2 })) },
      options: { scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } },
    });
  }, 300);

  if (current) show();
}
