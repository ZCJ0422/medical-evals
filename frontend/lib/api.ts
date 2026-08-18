const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = typeof window === "undefined" ? null : window.sessionStorage.getItem("medical_evals_token");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) } });
  if (!response.ok) throw new Error(await response.text());
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiBlob(path: string): Promise<Blob> {
  const token = typeof window === "undefined" ? null : window.sessionStorage.getItem("medical_evals_token");
  const response = await fetch(`${API_BASE}${path}`, { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  if (!response.ok) throw new Error(await response.text());
  return response.blob();
}

export async function apiText(path: string): Promise<string> {
  const token = typeof window === "undefined" ? null : window.sessionStorage.getItem("medical_evals_token");
  const response = await fetch(`${API_BASE}${path}`, { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } });
  if (!response.ok) throw new Error(await response.text());
  return response.text();
}

export function saveToken(token: string) { window.sessionStorage.setItem("medical_evals_token", token); }
export function clearToken() { window.sessionStorage.removeItem("medical_evals_token"); }
export function hasToken() { return Boolean(window.sessionStorage.getItem("medical_evals_token")); }
