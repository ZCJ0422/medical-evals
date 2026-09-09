"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GlobeIcon, GridIcon, ListIcon, LogoutIcon } from "./icons";
import { currentUser, hasToken, logout } from "../lib/auth";
import { clearToken } from "../lib/api";
import type { User } from "../lib/types";
import { useLocale } from "../lib/i18n";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter(); const pathname = usePathname(); const [ready, setReady] = useState(false); const [user, setUser] = useState<User | null>(null); const { t, locale, setLocale } = useLocale();
  useEffect(() => { let active = true; if (!hasToken()) { router.replace("/admin/login"); return; } currentUser().then((value) => { if (value.role !== "admin") { clearToken(); router.replace("/admin/login"); return; } if (active) { setUser(value); setReady(true); } }).catch(() => router.replace("/admin/login")); const expire = () => router.replace("/admin/login"); window.addEventListener("medical-evals:session-expired", expire); return () => { active = false; window.removeEventListener("medical-evals:session-expired", expire); }; }, [router]);
  if (!ready) return <main className="shell"><p className="lede">{t("checkingSession")}</p></main>;
  return <div className="app-frame"><a className="skip-link" href="#main-content">{t("skipToContent")}</a><aside className="sidebar"><Link className="brand" href="/app"><span className="brand-mark">M</span>Medical Evals</Link><nav aria-label="Main navigation"><Link className={pathname === "/app" ? "nav-link active" : "nav-link"} href="/app"><GridIcon size={17} />{t("overview")}</Link><Link className={pathname.startsWith("/app/models") ? "nav-link active" : "nav-link"} href="/app/models"><ListIcon size={17} />{t("models")}</Link><Link className={pathname.startsWith("/app/evaluations") ? "nav-link active" : "nav-link"} href="/app/evaluations"><ListIcon size={17} />{t("evaluations")}</Link><Link className={pathname.startsWith("/app/config") ? "nav-link active" : "nav-link"} href="/app/config"><ListIcon size={17} />测评配置</Link></nav><div className="sidebar-footer"><span className="sidebar-caption">{user?.username} · {user?.role}</span><button className="locale-toggle" onClick={() => setLocale(locale === "en" ? "zh" : "en")}><GlobeIcon size={17} />{t("language")}</button><button className="logout" onClick={() => { void logout(); router.replace("/admin/login"); }}><LogoutIcon size={17} />{t("signOut")}</button></div></aside><section className="app-content" id="main-content">{children}</section></div>;
}
