export const API_BASE = (import.meta.env?.VITE_API_BASE || '').replace(/\/+$/, '');

export async function apiFetch(path, opts = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const res = await fetch(url, opts);
  if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t}`); }
  return res.json();
}

export function fileUrl(p) {
  return `${API_BASE}/api/file?path=${encodeURIComponent(p)}`;
}
