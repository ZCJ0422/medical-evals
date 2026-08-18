import { api, clearToken, hasToken, saveToken } from "./api";

type LoginResponse = { access_token: string; user: { username: string; role: string } };

export async function login(username: string, password: string) {
  const response = await api<LoginResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
  saveToken(response.access_token);
  return response.user;
}

export function logout() { clearToken(); }
export { hasToken };
