import { api, clearToken, hasToken, saveTokens } from "./api";
import type { TokenResponse, User } from "./types";
export async function login(username: string, password: string) { const response = await api<TokenResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }); saveTokens(response.access_token, response.refresh_token); return response.user; }
export async function register(username: string, password: string) { const response = await api<TokenResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ username, password }) }); saveTokens(response.access_token, response.refresh_token); return response.user; }
export async function currentUser() { return api<User>("/api/v1/me"); }
export async function logout() { try { const refresh = sessionStorage.getItem("medical_evals_refresh_token"); if (refresh) await api<void>("/api/v1/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refresh }) }, false); } finally { clearToken(); } }
export { hasToken };
