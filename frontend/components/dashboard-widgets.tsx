import Link from "next/link";
import { ArrowRightIcon } from "./icons";
import { EmptyState, MetricCard, ProgressBar, StatusBadge } from "./ui";
import type { TaskSummary } from "../lib/types";
import type { MonitoringMetrics } from "../lib/types";
import { useLocale } from "../lib/i18n";

export function DashboardStats({ tasks }: { tasks: TaskSummary[] }) {
  const running = tasks.filter((task) => task.status === "running").length;
  const completed = tasks.filter((task) => ["completed", "partial_failed"].includes(task.status)).length;
  const failed = tasks.filter((task) => task.status === "failed").length;
  return <div className="metric-grid"><MetricCard label="Total runs" value={tasks.length} detail="All saved evaluations" /><MetricCard label="Running" value={running} detail={running ? "Needs attention now" : "No active runs"} tone={running ? "warning" : "default"} /><MetricCard label="Completed" value={completed} detail="Ready for review" tone="success" /><MetricCard label="Failed" value={failed} detail="Execution failures" tone={failed ? "danger" : "default"} /></div>;
}
export function RunningPanel({ tasks }: { tasks: TaskSummary[] }) {
  const running = tasks.filter((task) => ["queued", "running"].includes(task.status));
  return <section className="panel"><div className="section-heading"><div><p className="eyebrow">Live queue</p><h2>Running now</h2></div><Link className="result-link" href="/app/evaluations">View all <ArrowRightIcon size={15} /></Link></div>{running.length === 0 ? <EmptyState title="No active evaluations" body="Start a new evaluation and its progress will appear here." action={<Link className="action secondary" href="/app/evaluations/new">Create evaluation</Link>} /> : <div className="task-list compact-list">{running.slice(0, 3).map((task) => <article className="task-card" key={task.run_id}><div className="task-heading"><div><strong>{task.name}</strong><span className="task-id">{task.target_model_id} · {task.dataset_version_id}</span></div><StatusBadge status={task.status} /></div><ProgressBar value={task.progress.progress_percent} label={`${task.name} progress`} /><div className="task-progress"><span>{task.progress.completed_count} / {task.progress.total_count || "—"} samples</span><span>{task.progress.progress_percent.toFixed(0)}%</span></div></article>)}</div>}</section>;
}

export function RecentPanel({ tasks }: { tasks: TaskSummary[] }) {
  return <section className="panel"><div className="section-heading"><div><p className="eyebrow">Activity</p><h2>Recent evaluations</h2></div><Link className="result-link" href="/app/evaluations">Open runs <ArrowRightIcon size={15} /></Link></div>{tasks.length === 0 ? <EmptyState title="Your evaluation history is empty" body="Create your first run to start building a reviewable evaluation history." action={<Link className="action secondary" href="/app/evaluations/new">New evaluation</Link>} /> : <div className="recent-list">{tasks.slice(0, 5).map((task) => <Link className="recent-row" href={`/app/evaluations/${task.run_id}/results`} key={task.run_id}><div><strong>{task.name}</strong><span>{task.target_model_id} · {task.dataset_version_id}</span></div><div><StatusBadge status={task.status} /><span className="task-id">{task.progress.progress_percent.toFixed(0)}%</span></div></Link>)}</div>}</section>;
}

function formatBytes(value: number, locale: string) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value;
  let unit = units[0];
  for (const next of units) {
    amount /= 1024;
    unit = next;
    if (amount < 1024 || next === units[units.length - 1]) break;
  }
  return `${amount.toLocaleString(locale === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: 1 })} ${unit}`;
}

export function MonitoringPanel({ metrics, error }: { metrics: MonitoringMetrics | null; error?: string }) {
  const { t, locale } = useLocale();
  return <section className="panel monitoring-panel" aria-labelledby="monitoring-title"><div className="section-heading"><div><p className="eyebrow">{t("monitoring")}</p><h2 id="monitoring-title">{t("monitoring")}</h2></div>{metrics && <span className="muted">{new Date(metrics.generated_at).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US")}</span>}</div>{error || !metrics ? <p className="muted" role={error ? "alert" : undefined}>{error ?? t("monitoringUnavailable")}</p> : <div className="metric-grid monitoring-grid"><MetricCard label={t("queueDepth")} value={metrics.queue_depth ?? "—"} detail={`${t("queuePending")}: ${metrics.queue_pending ?? "—"}`} tone={metrics.queue_error ? "warning" : "default"} /><MetricCard label={t("expiredLeases")} value={metrics.expired_leases} detail={Object.entries(metrics.status_counts).map(([status, count]) => `${status}: ${count}`).join(" · ") || "—"} tone={metrics.expired_leases ? "danger" : "default"} /><MetricCard label={t("parseRate")} value={metrics.parse_success_rate == null ? "—" : `${(metrics.parse_success_rate * 100).toFixed(1)}%`} detail={`${metrics.request_success_count} requests · ${metrics.parse_failed_count} failed`} tone={metrics.parse_failed_count ? "warning" : "success"} /><MetricCard label={t("artifactStorage")} value={formatBytes(metrics.artifact_bytes, locale)} detail={`${metrics.artifact_file_count} files`} /></div>}</section>;
}
