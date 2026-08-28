"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { currentUser, login } from "../../lib/auth";
import { ActivityIcon } from "../../components/icons";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try { await login(String(form.get("username")), String(form.get("password"))); const user = await currentUser(); router.replace(user.role === "admin" ? "/app" : "/"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "登录失败，请检查账号和密码。"); }
    finally { setBusy(false); }
  }
  return <main className="public-auth-page auth-page"><Link className="auth-brand" href="/"><span className="auth-brand-mark"><ActivityIcon size={25} /></span><span>Medical Evals</span></Link><form className="form card auth-card" onSubmit={submit}><h1>登录</h1><label>用户名<input name="username" required autoComplete="username" /></label><label>密码<input name="password" type="password" required autoComplete="current-password" /></label>{error && <p className="error" role="alert">{error}</p>}<button className="action" type="submit" disabled={busy}>{busy ? "登录中…" : "登录"}</button><p className="hint">还没有账户？ <Link href="/register">注册</Link></p></form></main>;
}
