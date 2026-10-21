const API_ROOT = '/api';
async function request(path, options = {}) {
  const res = await fetch(`${API_ROOT}${path}`, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
const qs = (params) => { const s = new URLSearchParams(params); return s.toString() ? `?${s}` : ''; };
export const api = {
  overview:()=>request('/overview'), scan:(member_id)=>request('/gate/scan',{method:'POST',body:JSON.stringify({member_id})}),
  simulate:(n=8)=>request('/gate/simulate',{method:'POST',body:JSON.stringify({n})}), live:()=>request('/gate/live'),
  members:(p={})=>request(`/members${qs(p)}`), member:(id)=>request(`/members/${encodeURIComponent(id)}`),
  books:(p={})=>request(`/books${qs(p)}`), book:(id)=>request(`/books/${id}`), genres:()=>request('/genres'),
  loan:(member_id,book_id)=>request('/loans',{method:'POST',body:JSON.stringify({member_id,book_id})}), returnLoan:(id)=>request(`/loans/${id}/return`,{method:'POST'}),
  recommend:(id,method='hybrid')=>request(`/recommend/${encodeURIComponent(id)}${qs({method,k:10})}`), similar:(id)=>request(`/recommend/similar/${id}${qs({k:8})}`), evaluate:()=>request('/recommend/evaluate'),
  analytics:(kind)=>request(`/analytics/${kind}`), predictLate:(member_id,book_id)=>request('/analytics/predict_late',{method:'POST',body:JSON.stringify({member_id,book_id})}),
  graph:(min_weight=3)=>request(`/graph/books${qs({min_weight})}`), cypher:()=>fetch('/api/graph/cypher').then(r=>r.text()), ethics:()=>request('/ethics/report')
};
