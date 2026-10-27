// Today: ledger of key numbers, hourly footfall, who's inside, recent gate activity.
import { api } from "../api.js";
import { $, chart, css, errorBox, esc, fmt, skeleton } from "../ui.js";

export async function renderToday(app) {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  app.innerHTML = `
    <h1 class="title">${greeting}. Here's the floor today.</h1>
    <p class="lede">Who came in, who is still reading, and which books are out. Refreshes every ten seconds.</p>
    <div id="ledger">${skeleton(96)}</div>
    <div class="grid g-wide">
      <section class="panel"><h2>Arrivals by hour <small id="busiest"></small></h2><div class="chart-box"><canvas id="hourly"></canvas></div></section>
      <section class="panel"><h2>In the building now <small id="inside-count"></small></h2><div id="inside" style="max-height:260px;overflow:auto">${skeleton(200)}</div></section>
      <section class="panel span-2" style="grid-column:1/-1"><h2>Expected crowd today <small id="occ-note"></small></h2>
        <div id="occ-alerts"></div><div class="chart-box short"><canvas id="occ"></canvas></div></section>
      <section class="panel span-2" style="grid-column:1/-1"><h2>Gate activity</h2><ul class="feed" id="feed">${skeleton(160)}</ul></section>
    </div>`;

  let hourlyChart = null;

  async function refresh() {
    try {
      const [o, live] = await Promise.all([api.overview(), api.live()]);
      $("#ledger").innerHTML = `<div class="ledger">
        <div><div class="v">${fmt.n(o.inside_now)}<small>/ ${o.capacity}</small></div><div class="k">Inside right now</div></div>
        <div><div class="v">${fmt.n(o.visits_today)}</div><div class="k">Visits today</div></div>
        <div><div class="v">${Math.round(o.avg_stay_min ?? 0)}<small>min</small></div><div class="k">Average stay, last 30 days</div></div>
        <div><div class="v">${fmt.n(o.active_loans)}</div><div class="k">Books on loan</div></div>
        <div class="${o.overdue_loans ? "alert" : ""}"><div class="v">${fmt.n(o.overdue_loans)}</div><div class="k">Overdue</div></div></div>`;
      $("#busiest").textContent = o.busiest_hour != null ? `usually busiest at ${fmt.hour(o.busiest_hour)}` : "";

      const hours = [...Array(14).keys()].map((i) => i + 8);
      const data = hours.map((h) => o.today_hourly[h]);
      if (hourlyChart) {
        hourlyChart.data.datasets[0].data = data;
        hourlyChart.update("none");
      } else {
        hourlyChart = chart($("#hourly"), {
          type: "bar",
          data: { labels: hours.map(fmt.hour), datasets: [{ data, backgroundColor: hours.map((h) => (h === new Date().getHours() ? css("--brass") : css("--series-1"))), borderRadius: 3 }] },
          options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 } } } },
        });
      }

      $("#inside-count").textContent = `${live.inside.length} reader${live.inside.length === 1 ? "" : "s"}`;
      $("#inside").innerHTML = live.inside.length
        ? `<table><tbody>${live.inside.map((r) => `<tr class="link" data-id="${r.member_id}"><td>${esc(r.name)}<div class="muted" style="font-size:12.5px">${r.department}</div></td><td class="r num">${fmt.mins(r.minutes)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">The reading room is empty. <a href="#/gate">Open the gate</a> to check someone in.</div>`;

      $("#feed").innerHTML = live.recent.map((e) => `
        <li><time>${fmt.time(e.time)}</time>
          <span><a href="#/members/${e.member_id}">${esc(e.name)}</a> ${e.action === "exit" && e.duration_min != null ? `<span class="muted">after ${fmt.mins(e.duration_min)}</span>` : ""}</span>
          <span class="dir ${e.action}">${e.action === "entry" ? "In" : "Out"}</span></li>`).join("");
    } catch (e) {
      $("#ledger").innerHTML = errorBox(e);
    }
  }

  app.addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-id]");
    if (row) location.hash = `#/members/${row.dataset.id}`;
  });
  // occupancy forecast: predicted arrivals x how long people stay
  api.occupancy().then((f) => {
    $("#occ-note").textContent = `${f.model} for arrivals, typical stay ${Math.round(f.median_stay_min)} min, ${f.capacity} seats`;
    $("#occ-alerts").innerHTML = f.alerts.length
      ? f.alerts.map((a) => `<p class="badge warn" style="display:block;margin:0 0 8px;font-weight:500">${esc(a)}</p>`).join("")
      : `<p class="muted" style="margin-top:0">No crowding expected in the coming hours.</p>`;
    chart($("#occ"), {
      type: "line",
      data: { labels: f.hours.map((h) => fmt.hour(+h.hour_iso.slice(11, 13))), datasets: [
        { label: "Predicted readers inside", data: f.hours.map((h) => h.predicted_inside), borderColor: css("--brass"), backgroundColor: css("--brass") + "30", fill: true, tension: 0.3 },
        { label: "Seats", data: f.hours.map(() => f.capacity), borderColor: css("--pencil"), borderDash: [5, 5], pointRadius: 0 },
      ] },
      options: { scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } },
    });
  }).catch((e) => { $("#occ-alerts").innerHTML = `<div class="error-box">${esc(e.message)}</div>`; });

  await refresh();
  const timer = setInterval(refresh, 10000);
  return () => clearInterval(timer);
}
