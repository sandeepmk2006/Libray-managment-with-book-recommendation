// Thin fetch wrapper around the Flask API.
async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const type = res.headers.get("content-type") || "";
  const data = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

const get = (p) => request(p);
const post = (p, body) => request(p, { method: "POST", body: body || {} });

export const api = {
  overview: () => get("/api/overview"),
  scan: (member_id) => post("/api/gate/scan", { member_id }),
  simulate: (n = 8) => post("/api/gate/simulate", { n }),
  live: () => get("/api/gate/live"),
  members: (q = "", limit = 50) => get(`/api/members?q=${encodeURIComponent(q)}&limit=${limit}`),
  member: (id) => get(`/api/members/${encodeURIComponent(id)}`),
  books: (q = "", genre = "") => get(`/api/books?q=${encodeURIComponent(q)}&genre=${encodeURIComponent(genre)}`),
  book: (id) => get(`/api/books/${id}`),
  genres: () => get("/api/genres"),
  issue: (member_id, book_id) => post("/api/loans", { member_id, book_id }),
  returnLoan: (id) => post(`/api/loans/${id}/return`),
  recommend: (id, method = "hybrid", k = 10) => get(`/api/recommend/${encodeURIComponent(id)}?method=${method}&k=${k}`),
  similar: (id, k = 8) => get(`/api/recommend/similar/${id}?k=${k}`),
  evaluate: () => get("/api/recommend/evaluate"),
  analytics: (name) => get(`/api/analytics/${name}`),
  predictLate: (member_id, book_id) => post("/api/analytics/predict_late", { member_id, book_id }),
  graph: (minWeight = 3) => get(`/api/graph/books?min_weight=${minWeight}`),
  cypher: () => get("/api/graph/cypher"),
  ethics: () => get("/api/ethics/report"),
};
