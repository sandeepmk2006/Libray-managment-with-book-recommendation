// Shared UI helpers: DOM, formatting, states, charts.
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export const fmt = {
  n: (v, d = 0) => (v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v, d = 0) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`),
  p: (v) => (v == null ? "–" : v < 0.001 ? "< 0.001" : v.toFixed(3)),
  mins: (m) => {
    if (m == null) return "–";
    const h = Math.floor(m / 60), r = Math.round(m % 60);
    return h ? `${h} h ${r} min` : `${r} min`;
  },
  time: (iso) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "–"),
  date: (iso) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "–"),
  dateTime: (iso) => (iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–"),
  hour: (h) => `${String(h).padStart(2, "0")}:00`,
};

export const skeleton = (h = 220) => `<div class="skeleton" style="height:${h}px"></div>`;
export const errorBox = (e, retry) =>
  `<div class="error-box">${esc(e.message || e)}${retry ? `<br><button class="btn ghost" style="margin-top:10px" data-retry>Try again</button>` : ""}</div>`;

export function toast(message, bad = false) {
  const el = document.createElement("div");
  el.className = `toast${bad ? " bad" : ""}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 3600);
}

// Load data into a container, with skeleton + inline error + retry.
export async function load(container, fetcher, render, height = 220) {
  container.innerHTML = skeleton(height);
  try {
    render(await fetcher());
  } catch (e) {
    container.innerHTML = errorBox(e, true);
    container.querySelector("[data-retry]")?.addEventListener("click", () => load(container, fetcher, render, height));
  }
}

// ---------- genre colours & generated book covers ----------
const GENRES = ["Science Fiction", "Fantasy", "Mystery", "Classics", "Literary Fiction", "History", "Science",
  "Psychology", "Self Help", "Biography", "Computer Science", "Economics", "Philosophy", "Horror", "Romance",
  "Young Adult", "Graphic Novel", "Poetry"];
const PALETTE = ["#1f6f5c", "#7a3e65", "#2d5d8a", "#8a5a1f", "#b4442c", "#3f4f8f", "#5b7a2e", "#6b4f2a", "#2f7a7a",
  "#8c3b3b", "#264653", "#9a6b12", "#4a3b6b", "#3b3b3b", "#a34d6d", "#2e6b3f", "#59408a", "#7c6a2e"];
export const genreColor = (g) => PALETTE[Math.max(0, GENRES.indexOf(g)) % PALETTE.length];

export function cover(book) {
  const c = genreColor(book.genre);
  return `<div class="cover" style="background:linear-gradient(160deg, ${c}, color-mix(in srgb, ${c} 70%, #000))">
      <span class="t">${esc(book.title)}</span><span class="a">${esc(book.author)}</span></div>`;
}

export const stars = (r) => (r == null ? "" : `<span class="stars" aria-label="${r.toFixed(1)} out of 5">${"★".repeat(Math.round(r))}${"☆".repeat(5 - Math.round(r))}</span>`);

// ---------- Chart.js theming ----------
const charts = new Set();
export function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
export function chart(canvas, config) {
  if (!canvas || !canvas.isConnected) return null; // view changed before the data arrived
  if (!window.Chart) {
    canvas.parentElement.innerHTML = `<div class="empty">Charts need an internet connection to load.</div>`;
    return null;
  }
  const ink = css("--ink-soft"), rule = css("--rule");
  Chart.defaults.font.family = css("--font-body");
  Chart.defaults.color = ink;
  Chart.defaults.borderColor = rule;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.tooltip.backgroundColor = css("--ink");
  Chart.defaults.plugins.tooltip.titleColor = css("--paper");
  Chart.defaults.plugins.tooltip.bodyColor = css("--paper");
  config.options = { responsive: true, maintainAspectRatio: false, ...config.options };
  const c = new Chart(canvas, config);
  charts.add(c);
  return c;
}

export function destroyCharts() {
  charts.forEach((c) => c.destroy());
  charts.clear();
}

// Horizontal bar list rendered in HTML (lighter than a chart for ranked lists).
export function barList(rows, { label, value, display = (v) => fmt.n(v), max } = {}) {
  const top = max ?? Math.max(...rows.map(value), 0.0001);
  return `<div class="bar-list">${rows.map((r) => `
    <div class="item"><span>${esc(label(r))}</span>
      <div class="track"><div class="fill" style="width:${(value(r) / top) * 100}%"></div></div>
      <span class="r num">${display(value(r))}</span></div>`).join("")}</div>`;
}

// Searchable member picker used by several views.
export function memberPicker(input, onPick) {
  const list = document.createElement("div");
  list.className = "search-results";
  list.hidden = true;
  input.parentElement.style.position = "relative";
  input.parentElement.append(list);
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (!q) return (list.hidden = true);
      const { api } = await import("./api.js");
      const rows = await api.members(q, 8).catch(() => []);
      list.innerHTML = rows.length
        ? rows.map((m) => `<a href="#" data-id="${m.member_id}"><span>${esc(m.name)}</span><span class="muted">${m.member_id} · ${m.department}</span></a>`).join("")
        : `<div class="empty">No member matches “${esc(q)}”.</div>`;
      list.hidden = false;
    }, 180);
  });
  list.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-id]");
    if (!a) return;
    e.preventDefault();
    list.hidden = true;
    input.value = a.dataset.id;
    onPick(a.dataset.id);
  });
  input.addEventListener("blur", () => setTimeout(() => (list.hidden = true), 200));
}
