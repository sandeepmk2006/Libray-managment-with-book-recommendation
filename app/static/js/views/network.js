// Reading web: force-directed graph of books borrowed by the same members.
import { api } from "../api.js";
import { $, css, esc, genreColor, toast } from "../ui.js";
import { openBook } from "./catalog.js";

export async function renderNetwork(app) {
  app.innerHTML = `
    <h1 class="title">Reading web</h1>
    <p class="lede">Two books are linked when the same readers borrowed both. Thicker lines mean more shared readers; bigger circles are borrowed more often. Drag to rearrange, scroll to zoom, click a book to open it.</p>
    <div class="row" style="margin-bottom:14px;justify-content:space-between">
      <label class="field" style="display:block">Show links shared by at least <output id="w-out">8</output> readers
        <input id="weight" type="range" min="3" max="14" value="8" style="width:220px;display:block;margin-top:6px"></label>
      <button class="btn ghost" id="cypher" type="button">Copy as Neo4j Cypher</button>
    </div>
    <div class="network" id="net"></div>
    <div class="legend" id="legend"></div>
    <p class="muted" id="net-stats" style="font-size:13px"></p>`;

  if (!window.d3) {
    $("#net").innerHTML = `<div class="empty">The graph needs an internet connection to load its drawing library.</div>`;
    return;
  }
  let sim = null;

  async function draw(minWeight) {
    if (sim) sim.stop();
    const box = $("#net");
    box.innerHTML = "";
    let data;
    try { data = await api.graph(minWeight); } catch (e) { box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`; return; }
    if (!data.nodes.length) { box.innerHTML = `<div class="empty">No pairs reach that threshold. Lower the slider.</div>`; return; }

    const { width, height } = box.getBoundingClientRect();
    const svg = d3.select(box).append("svg").attr("viewBox", [0, 0, width, height]);
    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.3, 4]).on("zoom", (e) => g.attr("transform", e.transform)));
    const tip = d3.select(box).append("div").attr("class", "tooltip").style("opacity", 0);

    const maxW = d3.max(data.links, (l) => l.weight);
    const r = d3.scaleSqrt().domain([0, d3.max(data.nodes, (n) => n.loans)]).range([4, 20]);
    sim = d3.forceSimulation(data.nodes)
      .force("link", d3.forceLink(data.links).id((d) => d.id).distance((l) => 120 - 60 * (l.weight / maxW)).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius((d) => r(d.loans) + 2));

    const link = g.append("g").attr("stroke", css("--ink-soft")).attr("stroke-opacity", 0.35)
      .selectAll("line").data(data.links).join("line").attr("stroke-width", (l) => 0.6 + 3 * (l.weight / maxW));
    const node = g.append("g").selectAll("circle").data(data.nodes).join("circle")
      .attr("r", (d) => r(d.loans)).attr("fill", (d) => genreColor(d.genre)).attr("stroke", css("--sheet")).attr("stroke-width", 1.5)
      .style("cursor", "pointer")
      .on("mouseenter", (e, d) => {
        const linked = new Set([d.id]);
        data.links.forEach((l) => { if (l.source.id === d.id) linked.add(l.target.id); if (l.target.id === d.id) linked.add(l.source.id); });
        node.attr("opacity", (n) => (linked.has(n.id) ? 1 : 0.15));
        link.attr("stroke-opacity", (l) => (l.source.id === d.id || l.target.id === d.id ? 0.8 : 0.05));
        tip.style("opacity", 1).html(`<b>${esc(d.title)}</b><br>${d.genre} · ${d.loans} loans · ${linked.size - 1} linked books`);
      })
      .on("mousemove", (e) => { const [x, y] = d3.pointer(e, box); tip.style("left", `${x + 14}px`).style("top", `${y + 10}px`); })
      .on("mouseleave", () => { node.attr("opacity", 1); link.attr("stroke-opacity", 0.35); tip.style("opacity", 0); })
      .on("click", (e, d) => openBook(d.id))
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
    const top = [...data.nodes].sort((a, b) => b.loans - a.loans).slice(0, 14);
    const label = g.append("g").selectAll("text").data(top).join("text")
      .text((d) => d.title).attr("font-size", 11).attr("fill", css("--ink")).attr("paint-order", "stroke").attr("stroke", css("--sheet")).attr("stroke-width", 3).attr("pointer-events", "none").attr("dx", (d) => r(d.loans) + 3).attr("dy", 4);

    sim.on("tick", () => {
      link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
      label.attr("x", (d) => d.x).attr("y", (d) => d.y);
    });

    const genres = [...new Set(data.nodes.map((n) => n.genre))].sort();
    $("#legend").innerHTML = genres.map((gname) => `<span><i style="background:${genreColor(gname)}"></i>${gname}</span>`).join("");
    const strongest = [...data.links].sort((a, b) => b.weight - a.weight)[0];
    $("#net-stats").textContent = `${data.nodes.length} books, ${data.links.length} links. Strongest pair: ${strongest.source.title ?? strongest.source} and ${strongest.target.title ?? strongest.target}, shared by ${strongest.weight} readers.`;
  }

  $("#weight").addEventListener("change", (e) => draw(+e.target.value));
  $("#weight").addEventListener("input", (e) => ($("#w-out").textContent = e.target.value));
  $("#cypher").addEventListener("click", async () => {
    try {
      const text = await api.cypher();
      await navigator.clipboard.writeText(text);
      toast(`Copied ${text.split("\n").length} Cypher lines. Paste them into Neo4j Browser.`);
    } catch (e) { toast(`Couldn't copy: ${e.message}`, true); }
  });
  await draw(8);
  return () => sim && sim.stop();
}
