// Members: searchable register and individual profiles.
import { api } from "../api.js";
import { $, barList, chart, css, esc, fmt, load, toast } from "../ui.js";
import { bookCard, openBook } from "./catalog.js";

export async function renderMembers(app) {
  app.innerHTML = `
    <h1 class="title">Members</h1>
    <p class="lede">Students and faculty registered with the library. Open anyone to see their visits, loans and reading taste.</p>
    <label class="field" style="max-width:360px;margin-bottom:18px">Search by name, ID or department<input id="mq" type="search" placeholder="Priya, KU24012, MBA…"></label>
    <section class="panel flush"><div class="table-wrap" id="register"></div></section>`;
  const draw = (q = "") => load($("#register"), () => api.members(q, 200), (rows) => {
    $("#register").innerHTML = rows.length ? `<table>
      <thead><tr><th>Member</th><th>ID</th><th>Department</th><th>Year</th><th class="r">Visits</th><th class="r">Loans</th></tr></thead>
      <tbody>${rows.map((m) => `<tr class="link" data-id="${m.member_id}"><td>${esc(m.name)}</td><td class="muted">${m.member_id}</td><td>${m.department}</td><td>${m.year || "Faculty"}</td><td class="r">${m.visits}</td><td class="r">${m.loans}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">No members match that search.</div>`;
  }, 400);
  let t;
  $("#mq").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => draw(e.target.value.trim()), 220); });
  $("#register").addEventListener("click", (e) => {
    const r = e.target.closest("tr[data-id]");
    if (r) location.hash = `#/members/${r.dataset.id}`;
  });
  draw();
}

export async function renderMember(app, id) {
  app.innerHTML = `<div id="profile"></div>`;
  const draw = () => load($("#profile"), () => Promise.all([api.member(id), api.recommend(id, "hybrid", 5)]), ([p, rec]) => {
    const m = p.member, s = p.stats;
    const inside = p.visits[0] && !p.visits[0].exit_time;
    $("#profile").innerHTML = `
      <p><a href="#/members" class="muted">All members</a></p>
      <h1 class="title">${esc(m.name)}</h1>
      <p class="lede">${m.member_id} · ${m.department} · ${m.year ? `Year ${m.year}` : "Faculty"} · member since ${fmt.date(m.joined)}
        ${inside ? ` · <span class="badge ok">In the library now</span>` : ""}</p>
      <div class="ledger">
        <div><div class="v">${s.visits}</div><div class="k">Visits</div></div>
        <div><div class="v">${fmt.n(s.total_hours, 0)}<small>h</small></div><div class="k">Time in the library</div></div>
        <div><div class="v">${Math.round(s.avg_stay_min ?? 0)}<small>min</small></div><div class="k">Typical stay</div></div>
        <div><div class="v">${s.loans}</div><div class="k">Books borrowed</div></div>
        <div class="${s.late_rate > 0.4 ? "alert" : ""}"><div class="v">${fmt.pct(s.late_rate)}</div><div class="k">Returned late</div></div>
      </div>
      <div class="grid g-wide">
        <section class="panel"><h2>Recent visits</h2><div class="chart-box short"><canvas id="visits"></canvas></div>
          <div class="table-wrap" style="max-height:260px;overflow:auto;margin-top:12px"><table><thead><tr><th>In</th><th>Out</th><th class="r">Stay</th><th>Purpose</th></tr></thead>
          <tbody>${p.visits.map((v) => `<tr><td>${fmt.dateTime(v.entry_time)}</td><td>${v.exit_time ? fmt.time(v.exit_time) : `<span class="badge ok">inside</span>`}</td><td class="r">${fmt.mins(v.duration_min)}</td><td class="muted">${v.purpose || "Not recorded"}</td></tr>`).join("")}</tbody></table></div></section>
        <section class="panel"><h2>Reading taste <small>${s.favourite_genre ? `mostly ${s.favourite_genre}` : ""}</small></h2>
          ${Object.keys(p.taste).length ? barList(Object.entries(p.taste).slice(0, 8), { label: (r) => r[0], value: (r) => r[1], display: (v) => fmt.pct(v) }) : `<div class="empty">No loans yet.</div>`}</section>
      </div>
      <section class="panel" style="margin-top:18px"><h2>Loans</h2><div class="table-wrap"><table>
        <thead><tr><th>Book</th><th>Issued</th><th>Due</th><th>Status</th><th></th></tr></thead>
        <tbody>${p.loans.map((l) => `<tr><td><a href="#" data-book="${l.book_id}">${esc(l.title)}</a></td><td>${fmt.date(l.issued)}</td><td>${fmt.date(l.due)}</td>
          <td><span class="badge ${l.status === "overdue" ? "warn" : l.status === "on loan" ? "ok" : "keep"}">${l.status}</span></td>
          <td class="r">${l.returned ? "" : `<button class="btn ghost" data-return="${l.loan_id}" type="button">Mark returned</button>`}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No loans yet.</td></tr>`}</tbody>
      </table></div></section>
      <section style="margin-top:22px"><h2>Suggested next reads <small><a href="#/discover/${m.member_id}">compare approaches</a></small></h2>
        <div class="shelf">${rec.items.map((it) => bookCard(it.book, `<div class="chips" style="margin-top:4px">${it.reasons.slice(0, 2).map((r) => `<span class="reason">${esc(r)}</span>`).join("")}</div>`)).join("")}</div></section>`;

    // stay length of the last 30 visits, oldest first
    const vs = p.visits.filter((v) => v.duration_min != null).slice(0, 30).reverse();
    chart($("#visits"), {
      type: "line",
      data: { labels: vs.map((v) => fmt.date(v.entry_time)), datasets: [{ data: vs.map((v) => v.duration_min), borderColor: css("--brass"), backgroundColor: css("--brass") + "30", fill: true, tension: 0.3, pointRadius: 2 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt.mins(c.raw) } } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, title: { display: true, text: "minutes" } } } },
    });
  }, 500);

  app.addEventListener("click", async (e) => {
    const ret = e.target.closest("[data-return]");
    if (ret) {
      ret.disabled = true;
      try { await api.returnLoan(ret.dataset.return); toast("Marked as returned"); draw(); } catch (err) { toast(err.message, true); ret.disabled = false; }
    }
    const b = e.target.closest("[data-book]");
    if (b) { e.preventDefault(); openBook(b.dataset.book); }
  });
  draw();
}
