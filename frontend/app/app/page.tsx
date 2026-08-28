"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActivityIcon, PlusIcon } from "../../components/icons";
import { DashboardStats, RecentPanel, RunningPanel } from "../../components/dashboard-widgets";
import { EmptyState, InlineAlert, Skeleton } from "../../components/ui";
import { PageHeader } from "../../components/page-header";
import { api } from "../../lib/api";
import type { TaskSummary } from "../../lib/types";
import { useLocale } from "../../lib/i18n";

export default function DashboardPage() {
  const { t } = useLocale();
  const [tasks, setTasks] = useState<TaskSummary[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  useEffect(() => { let active = true; const load = () => api<TaskSummary[]>("/api/v1/evaluations?limit=200").then((items) => { if (active) { setTasks(items); setLoading(false); } }).catch(() => { if (active) { setError("Unable to load dashboard activity. Retry from Evaluations."); setLoading(false); } }); load(); const timer = window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 5000); return () => { active = false; window.clearInterval(timer); }; }, []);
  return (
    <main className="shell" aria-labelledby="page-title">
      <PageHeader eyebrow={t("adminWorkbench")} title={t("controlRoom")} description={t("controlLead")} action={<Link className="action" href="/app/evaluations/new"><PlusIcon size={17} />{t("newEvaluation")}</Link>} />
      {error && <InlineAlert tone="error">{t("unableLoadDashboard")}</InlineAlert>}
      {loading ? <div className="metric-grid">{[1, 2, 3, 4].map((item) => <div className="metric-card" key={item}><Skeleton /><Skeleton className="skeleton-number" /></div>)}</div> : <DashboardStats tasks={tasks} />}
      {!loading && tasks.length === 0 && <EmptyState title={t("readyTitle")} body={t("readyBody")} action={<Link className="action" href="/app/evaluations/new"><ActivityIcon size={17} />{t("startFirstRun")}</Link>} />}
      {!loading && tasks.length > 0 && <div className="dashboard-grid"><RunningPanel tasks={tasks} /><RecentPanel tasks={tasks} /></div>}
      <section className="panel quick-start-panel"><div className="section-heading"><div><p className="eyebrow">{t("quickStart")}</p><h2>{t("fromConfiguration")}</h2></div></div><ol className="quick-start"><li><span className="step-number">01</span><div><strong>{t("chooseDatasetStep")}</strong><span className="muted">{t("chooseDatasetStepHint")}</span></div></li><li><span className="step-number">02</span><div><strong>{t("configureModelsStep")}</strong><span className="muted">{t("configureModelsStepHint")}</span></div></li><li><span className="step-number">03</span><div><strong>{t("reviewResultsStep")}</strong><span className="muted">{t("reviewResultsStepHint")}</span></div></li></ol></section>
    </main>
  );
}
