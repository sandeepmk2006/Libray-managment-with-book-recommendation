// Gate kiosk: one input records entry or exit; the result is stamped like a date-due card.
import { api } from "../api.js";
import { $, css, esc, fmt, toast } from "../ui.js";

export async function renderGate(app) {
  app.innerHTML = `
    <h1 class="title">Gate</h1>
    <p class="lede">Scan a member card or type the ID. The first scan checks the reader in, the next one checks them out and records how long they stayed.</p>
    <div class="gate">
      <section class="scanner">
        <form id="scan-form" autocomplete="off">
          <label for="scan-id">Member ID</label>
          <input id="scan-id" placeholder="KU24000" spellcheck="false" autofocus>
          <div class="row" style="justify-content:space-between">
            <span class="hint">Press Enter to record. Card scanners that type the ID work too.</span>
            <button class="btn brass" type="submit">Record</button>
          </div>
        </form>
        <div class="stamp-area" id="stamp"><p class="hint">Waiting for the first scan.</p></div>
      </section>
      <section class="grid" style="align-content:start">
        <div class="panel">
          <h2>Occupancy</h2>
          <div class="gauge-wrap"><svg id="gauge" width="220" height="220" viewBox="0 0 220 220" aria-hidden="true"></svg>
            <div class="center"><strong id="gauge-n">–</strong><span class="muted" id="gauge-cap"></span></div></div>
        </div>
        <div class="panel">
          <h2>Busy afternoon to demo?</h2>
          <p class="muted" style="margin-top:0">Let a few random members walk through the gate to see the floor update.</p>
          <button class="btn ghost" id="simulate" type="button">Send 8 readers through the gate</button>
        </div>
        <div class="panel"><h2>Last scans</h2><ul class="feed" id="gate-feed"></ul></div>
      </section>
    </div>`;

  const input = $("#scan-id");
  input.focus();

  function stamp(res) {
    const exit = res.action === "exit";
    $("#stamp").innerHTML = `
      <div class="stamp ${res.action}">
        <div class="word">${exit ? "CHECKED OUT" : "CHECKED IN"}</div>
        <div class="name">${esc(res.member.name)}</div>
        <div class="meta">${res.member.member_id} · ${res.member.department}${res.member.year ? ` · Year ${res.member.year}` : " · Faculty"}</div>
        <div class="time">${new Date(res.time).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).toUpperCase()}</div>
        ${exit ? `<div class="meta">Stayed ${fmt.mins(res.duration_min)}</div>` : ""}
      </div>`;
  }

  function drawGauge(inside, cap) {
    const svg = d3.select("#gauge");
    svg.selectAll("*").remove();
    const arc = d3.arc().innerRadius(82).outerRadius(100).startAngle(-Math.PI * 0.75);
    const g = svg.append("g").attr("transform", "translate(110,115)");
    g.append("path").attr("d", arc({ endAngle: Math.PI * 0.75 })).attr("fill", css("--rule"));
    const share = Math.min(1, inside / cap);
    g.append("path").attr("d", arc({ endAngle: -Math.PI * 0.75 + share * Math.PI * 1.5 }))
      .attr("fill", share > 0.85 ? css("--pencil") : css("--brass"));
    $("#gauge-n").textContent = inside;
    $("#gauge-cap").textContent = `of ${cap} seats`;
  }

  async function refresh() {
    try {
      const live = await api.live();
      if (window.d3) drawGauge(live.inside.length, live.capacity);
      $("#gate-feed").innerHTML = live.recent.slice(0, 8).map((e) => `
        <li><time>${fmt.time(e.time)}</time><span>${esc(e.name)}</span><span class="dir ${e.action}">${e.action === "entry" ? "In" : "Out"}</span></li>`).join("");
    } catch (e) {
      $("#gate-feed").innerHTML = `<li class="muted">${esc(e.message)}</li>`;
    }
  }

  $("#scan-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = input.value.trim();
    if (!id) return input.focus();
    try {
      const res = await api.scan(id);
      stamp(res);
      window.dispatchEvent(new Event("gate-changed"));
      refresh();
    } catch (err) {
      $("#stamp").innerHTML = `<div class="stamp error"><div class="word">NOT RECOGNISED</div><div class="meta">${esc(err.message)}. Check the ID on the card and scan again.</div></div>`;
    }
    input.value = "";
    input.focus();
  });

  $("#simulate").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const { events } = await api.simulate(8);
      const ins = events.filter((x) => x.action === "entry").length;
      if (events.length) stamp(events[events.length - 1]);
      toast(`${ins} checked in, ${events.length - ins} checked out`);
      window.dispatchEvent(new Event("gate-changed"));
      refresh();
    } catch (err) {
      toast(err.message, true);
    }
    e.target.disabled = false;
  });

  refresh();
  const timer = setInterval(refresh, 10000);
  return () => clearInterval(timer);
}
