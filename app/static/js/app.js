// Hash router, shell behaviour (theme, clock, global search, shortcuts).
import { api } from "./api.js";
import { $, $$, destroyCharts, esc } from "./ui.js";
import { renderToday } from "./views/today.js";
import { renderGate } from "./views/gate.js";
import { renderDiscover } from "./views/discover.js";
import { renderCatalog } from "./views/catalog.js";
import { renderMembers, renderMember } from "./views/members.js";
import { renderInsights } from "./views/insights.js";
import { renderNetwork } from "./views/network.js";
import { renderTrust } from "./views/trust.js";

const routes = {
  "": renderToday,
  gate: renderGate,
  discover: renderDiscover,
  catalog: renderCatalog,
  members: renderMembers,
  insights: renderInsights,
  network: renderNetwork,
  trust: renderTrust,
};

let cleanup = null;

async function route() {
  const [name = "", arg] = location.hash.replace(/^#\/?/, "").split("/");
  if (cleanup) cleanup();
  cleanup = null;
  destroyCharts();
  $$(".rail a.nav").forEach((a) => a.setAttribute("aria-current", a.dataset.route === name ? "page" : "false"));
  const app = $("#app");
  app.classList.remove("view");
  void app.offsetWidth; // restart the fade
  app.classList.add("view");
  const render = name === "members" && arg ? (el) => renderMember(el, decodeURIComponent(arg)) : routes[name];
  if (!render) {
    app.innerHTML = `<h1 class="title">Nothing on this shelf</h1><p class="lede">That page doesn't exist. <a href="#/">Go to today's overview.</a></p>`;
    return;
  }
  cleanup = (await render(app, arg ? decodeURIComponent(arg) : undefined)) || null;
  window.scrollTo(0, 0);
}

// ---------- theme ----------
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  $("#theme-toggle").textContent = dark ? "Switch to light" : "Switch to dark";
}
$("#theme-toggle").addEventListener("click", () => {
  const dark = $("#theme-toggle").textContent.includes("light");
  const next = dark ? "light" : "dark";
  try { localStorage.setItem("theme", next); } catch {}
  applyTheme(next);
  route(); // re-render so charts pick up the new colours
});
let saved = null;
try { saved = localStorage.getItem("theme"); } catch {}
applyTheme(saved);

// ---------- clock + occupancy ----------
function tick() {
  const now = new Date();
  $("#clock").innerHTML = `${now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}<br>${now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`;
}
async function occupancy() {
  try { $("#rail-inside").textContent = (await api.overview()).inside_now; } catch { $("#rail-inside").textContent = "–"; }
}
tick(); occupancy();
setInterval(tick, 15000);
setInterval(occupancy, 15000);
window.addEventListener("gate-changed", occupancy);

// ---------- global search ----------
const search = $("#global-search"), results = $("#search-results");
let timer;
search.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const q = search.value.trim();
    if (q.length < 2) return (results.hidden = true);
    try {
      const [members, books] = await Promise.all([api.members(q, 5), api.books(q)]);
      const rows = [
        ...members.map((m) => `<a href="#/members/${m.member_id}"><span>${esc(m.name)}</span><span class="muted">${m.member_id} · ${m.department}</span></a>`),
        ...books.slice(0, 6).map((b) => `<a href="#/catalog/${b.book_id}"><span>${esc(b.title)}</span><span class="muted">${esc(b.author)}</span></a>`),
      ];
      results.innerHTML = rows.join("") || `<div class="empty">No member or book matches “${esc(q)}”.</div>`;
      results.hidden = false;
    } catch { results.hidden = true; }
  }, 200);
});
results.addEventListener("click", () => { results.hidden = true; search.value = ""; });
search.addEventListener("blur", () => setTimeout(() => (results.hidden = true), 200));

// ---------- keyboard shortcuts ----------
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); search.focus(); }
  if (e.key === "g" && !typing && !e.ctrlKey && !e.metaKey) location.hash = "#/gate";
  if (e.key === "Escape") { results.hidden = true; document.dispatchEvent(new CustomEvent("close-drawer")); }
});

window.addEventListener("hashchange", route);
route();
