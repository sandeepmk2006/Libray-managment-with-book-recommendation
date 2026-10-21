// Catalogue: search, genre filter, shelf of covers, book drawer with issue + "readers also liked".
import { api } from "../api.js";
import { $, cover, esc, fmt, load, memberPicker, stars, toast } from "../ui.js";

export function bookCard(b, extra = "") {
  return `<button class="book" data-book="${b.book_id}" type="button">${cover(b)}
    <div><div style="font-weight:600;line-height:1.3">${esc(b.title)}</div>${extra}</div></button>`;
}

export async function openBook(bookId) {
  const back = document.createElement("div");
  back.className = "drawer-backdrop";
  const drawer = document.createElement("aside");
  drawer.className = "drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-label", "Book details");
  document.body.append(back, drawer);
  const close = () => { back.remove(); drawer.remove(); document.removeEventListener("close-drawer", close); };
  back.addEventListener("click", close);
  document.addEventListener("close-drawer", close);

  await load(drawer, () => api.book(bookId), (b) => {
    drawer.innerHTML = `
      <button class="btn ghost close" type="button" aria-label="Close">Close</button>
      <div style="width:150px;margin-bottom:18px">${cover(b)}</div>
      <h1 class="title" style="font-size:34px">${esc(b.title)}</h1>
      <p class="muted" style="margin:0 0 12px">${esc(b.author)}, ${b.year < 0 ? `${-b.year} BCE` : b.year} · ${b.genre} · ${b.pages} pages</p>
      <p>${esc(b.description)}.</p>
      <p>${stars(b.avg_rating)} <span class="muted">${b.avg_rating ? `${b.avg_rating.toFixed(1)} from ${b.n_ratings} ratings` : "Not rated yet"}</span></p>
      <p><span class="badge ${b.available > 0 ? "ok" : "warn"}">${b.available > 0 ? `${b.available} of ${b.copies} on the shelf` : "All copies are out"}</span></p>
      <form id="issue-form" class="row" style="margin:18px 0 26px">
        <label class="field" style="flex:1">Issue to member<input id="issue-member" placeholder="Member ID or name" required></label>
        <button class="btn" ${b.available > 0 ? "" : "disabled"}>Issue book</button>
      </form>
      <h2>Readers also liked</h2>
      <div class="grid">${b.similar.map((s) => `
        <a href="#" data-book="${s.book.book_id}" style="display:grid;grid-template-columns:44px 1fr;gap:12px;text-decoration:none;align-items:center">
          <div style="font-size:0">${cover(s.book).replace('class="cover"', 'class="cover" style="padding:4px;font-size:0"')}</div>
          <div><b>${esc(s.book.title)}</b><div class="chips" style="margin-top:4px">${s.reasons.map((r) => `<span class="reason">${esc(r)}</span>`).join("")}</div></div></a>`).join("")}
      </div>`;
    drawer.querySelector(".close").addEventListener("click", close);
    drawer.querySelector(".close").focus();
    memberPicker($("#issue-member", drawer), () => {});
    $("#issue-form", drawer).addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const loan = await api.issue($("#issue-member", drawer).value.trim(), b.book_id);
        toast(`Issued to ${loan.member_id}. Due ${fmt.date(loan.due)}.`);
        close();
      } catch (err) { toast(err.message, true); }
    });
    drawer.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-book]");
      if (a) { e.preventDefault(); close(); openBook(a.dataset.book); }
    });
  }, 400);
}

export async function renderCatalog(app, sub) {
  app.innerHTML = `
    <h1 class="title">Catalogue</h1>
    <p class="lede">Every title on the shelves, with live availability. Open a book to issue it or find its neighbours.</p>
    <div class="row" style="margin-bottom:14px">
      <label class="field" style="flex:1;max-width:360px">Search titles, authors, themes<input id="q" type="search" placeholder="space, detective, India…"></label>
    </div>
    <div class="chips" id="genres" style="margin-bottom:22px"></div>
    <div id="shelf"></div>`;

  let genre = "", q = "";
  const genres = await api.genres().catch(() => []);
  $("#genres").innerHTML = ["", ...genres].map((g) => `<button class="chip" type="button" data-g="${esc(g)}" aria-pressed="${g === genre}">${g || "All genres"}</button>`).join("");

  const draw = () => load($("#shelf"), () => api.books(q, genre), (books) => {
    $("#shelf").innerHTML = books.length
      ? `<p class="muted">${books.length} title${books.length === 1 ? "" : "s"}</p><div class="shelf">${books.map((b) => bookCard(b,
          `<div class="meta"><span>${esc(b.author)}</span><span>${b.available > 0 ? `${b.available} in` : "out"}</span></div>${stars(b.avg_rating)}`)).join("")}</div>`
      : `<div class="empty">No titles match. Try another word or clear the genre filter.</div>`;
  }, 400);

  $("#genres").addEventListener("click", (e) => {
    const c = e.target.closest("[data-g]");
    if (!c) return;
    genre = c.dataset.g;
    document.querySelectorAll("#genres .chip").forEach((x) => x.setAttribute("aria-pressed", x === c));
    draw();
  });
  let t;
  $("#q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { q = e.target.value.trim(); draw(); }, 220); });
  app.addEventListener("click", (e) => {
    const b = e.target.closest(".book[data-book]");
    if (b) openBook(b.dataset.book);
  });
  draw();
  if (sub) openBook(sub);
}
