import type { ReactNode } from "react";
import type { TaskStatus } from "../lib/types";
import { ActivityIcon } from "./icons";
import { useLocale } from "../lib/i18n";

export function StatusBadge({ status }: { status: TaskStatus | string }) {
  const { t } = useLocale();
  const labels: Record<string, string> = { queued: t("queuedStatus"), running: t("runningStatus"), completed: t("completedStatus"), partial_failed: t("partialFailedStatus"), failed: t("failedStatus"), cancelled: t("cancelledStatus") };
  const label = labels[status] ?? status.replaceAll("_", " ");
  return <span className={`status status-${status}`} role="img" aria-label={label} title={label}><span className="status-dot" aria-hidden="true" /></span>;
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const safeValue = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return <div className="progress-track" role="progressbar" aria-label={label ?? `${safeValue.toFixed(0)}% complete`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={safeValue}><span style={{ width: `${safeValue}%` }} /></div>;
}

export function MetricCard({ label, value, detail, tone = "default" }: { label: string; value: string | number; detail?: string; tone?: "default" | "success" | "warning" | "danger" }) {
  return <article className={`metric-card metric-${tone}`}><span className="metric-label">{label}</span><strong>{value}</strong>{detail && <span className="metric-detail">{detail}</span>}</article>;
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon" aria-hidden="true"><ActivityIcon size={17} /></div><strong>{title}</strong><span>{body}</span>{action}</div>;
}

export function InlineAlert({ tone = "info", children }: { tone?: "info" | "success" | "error"; children: ReactNode }) {
  return <div className={`inline-alert alert-${tone}`} role={tone === "error" ? "alert" : "status"}>{children}</div>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`skeleton ${className}`} aria-hidden="true" />;
}
