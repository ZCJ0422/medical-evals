"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GlobeIcon, GridIcon, ListIcon, LogoutIcon } from "./icons";
import { hasToken, logout } from "../lib/auth";
import { useLocale } from "../lib/i18n";

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter(); const pathname = usePathname(); const [ready, setReady] = useState(false); const { t, locale, setLocale } = useLocale();
  useEffect(() => { if (!hasToken()) router.replace("/login"); else setReady(true); }, [router]);
  if (!ready) return <main className="shell"><p className="lede">{t("checkingSession")}</p></main>;
  return <div className="app-frame"><a className="skip-link" href="#main-content">{t("skipToContent")}</a><aside className="sidebar"><Link className="brand" href="/app"><span className="brand-mark">M</span>Medical Evals</Link><nav aria-label="Main navigation"><Link className={pathname === "/app" ? "nav-link active" : "nav-link"} href="/app"><GridIcon size={17} />{t("overview")}</Link><Link className={pathname.startsWith("/app/evaluations") ? "nav-link active" : "nav-link"} href="/app/evaluations"><ListIcon size={17} />{t("evaluations")}</Link></nav><div className="sidebar-footer"><span className="sidebar-caption">{t("adminWorkspace")}</span><button className="locale-toggle" onClick={() => setLocale(locale === "en" ? "zh" : "en")}><GlobeIcon size={17} />{t("language")}</button><button className="logout" onClick={() => { logout(); router.replace("/login"); }}><LogoutIcon size={17} />{t("signOut")}</button></div></aside><section className="app-content" id="main-content">{children}</section></div>;
}
