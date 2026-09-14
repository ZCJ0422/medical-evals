"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActivityIcon, PlusIcon } from "../../components/icons";
import { DashboardStats, MonitoringPanel, RecentPanel, RunningPanel } from "../../components/dashboard-widgets";
import { EmptyState, InlineAlert, Skeleton } from "../../components/ui";
import { PageHeader } from "../../components/page-header";
import { api } from "../../lib/api";
import type { MonitoringMetrics, TaskSummary } from "../../lib/types";
import { useLocale } from "../../lib/i18n";

export default function DashboardPage() {
  const { t } = useLocale();
  const [tasks, setTasks] = useState<TaskSummary[]>([]); const [monitoring, setMonitoring] = useState<MonitoringMetrics | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [monitoringError, setMonitoringError] = useState("");
  useEffect(() => { let active = true; const load = async () => { const [runs, metrics] = await Promise.allSettled([api<TaskSummary[]>("/api/v1/evaluations?limit=200"), api<MonitoringMetrics>("/api/v1/ops/metrics")]); if (!active) return; if (runs.status === "fulfilled") { setTasks(runs.value); setError(""); } else { setError("Unable to load dashboard activity. Retry from Evaluations."); } if (metrics.status === "fulfilled") { setMonitoring(metrics.value); setMonitoringError(""); } else { setMonitoringError(metrics.reason instanceof Error ? metrics.reason.message : t("monitoringUnavailable")); } setLoading(false); }; void load(); const timer = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, 5000); return () => { active = false; window.clearInterval(timer); }; }, [t]);
  return (
    <main className="shell" aria-labelledby="page-title">
      <PageHeader eyebrow={t("adminWorkbench")} title={t("controlRoom")} description={t("controlLead")} action={<Link className="action" href="/app/evaluations/new"><PlusIcon size={17} />{t("newEvaluation")}</Link>} />
      {error && <InlineAlert tone="error">{t("unableLoadDashboard")}</InlineAlert>}
      {loading ? <div className="metric-grid">{[1, 2, 3, 4].map((item) => <div className="metric-card" key={item}><Skeleton /><Skeleton className="skeleton-number" /></div>)}</div> : <DashboardStats tasks={tasks} />}
      {!loading && <MonitoringPanel metrics={monitoring} error={monitoringError} />}
      {!loading && tasks.length === 0 && <EmptyState title={t("readyTitle")} body={t("readyBody")} action={<Link className="action" href="/app/evaluations/new"><ActivityIcon size={17} />{t("startFirstRun")}</Link>} />}
      {!loading && tasks.length > 0 && <div className="dashboard-grid"><RunningPanel tasks={tasks} /><RecentPanel tasks={tasks} /></div>}
      <section className="panel quick-start-panel"><div className="section-heading"><div><p className="eyebrow">{t("quickStart")}</p><h2>{t("fromConfiguration")}</h2></div></div><ol className="quick-start"><li><span className="step-number">01</span><div><strong>{t("chooseDatasetStep")}</strong><span className="muted">{t("chooseDatasetStepHint")}</span></div></li><li><span className="step-number">02</span><div><strong>{t("configureModelsStep")}</strong><span className="muted">{t("configureModelsStepHint")}</span></div></li><li><span className="step-number">03</span><div><strong>{t("reviewResultsStep")}</strong><span className="muted">{t("reviewResultsStepHint")}</span></div></li></ol></section>
    </main>
  );
}
