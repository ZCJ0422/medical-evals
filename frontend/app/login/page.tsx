"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "../../lib/auth";
import { useLocale } from "../../lib/i18n";

export default function LoginPage() {
  const router = useRouter(); const { t, locale, setLocale } = useLocale();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try { await login(String(form.get("username")), String(form.get("password"))); router.push("/app"); router.refresh(); }
    catch { setError(t("loginError")); } finally { setBusy(false); }
  }
  return <main className="shell auth-shell"><button className="language-button" onClick={() => setLocale(locale === "en" ? "zh" : "en")}>{t("language")}</button><p className="eyebrow">{t("adminWorkspace")}</p><h1>{t("login")}</h1><p className="lede">{t("signInLead")}</p><form className="form card" onSubmit={submit}><label>{t("username")}<input name="username" aria-label="Username" required autoComplete="username" defaultValue="admin" /></label><label>{t("password")}<input name="password" aria-label="Password" type="password" required autoComplete="current-password" /></label>{error && <p className="error" role="alert">{t("loginError")}</p>}<button className="action" type="submit" disabled={busy}>{busy ? t("signInBusy") : t("login")}</button><p className="hint">{t("defaultAccount")}</p></form></main>;
}
