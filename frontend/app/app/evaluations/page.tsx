"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PlusIcon, RefreshIcon } from "../../../components/icons";
import { EvaluationFilters, filterTasks } from "../../../components/evaluation-filters";
import { EvaluationTable } from "../../../components/evaluation-table";
import { InlineAlert, Skeleton } from "../../../components/ui";
import { PageHeader } from "../../../components/page-header";
import { api } from "../../../lib/api";
import type { TaskStatus, TaskSummary } from "../../../lib/types";
import { useLocale } from "../../../lib/i18n";

export default function EvaluationsPage() {
  const { t } = useLocale();
  const [tasks, setTasks] = useState<TaskSummary[]>([]); const [query, setQuery] = useState(""); const [status, setStatus] = useState<"all" | TaskStatus>("all"); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [loading, setLoading] = useState(true); const [refreshing, setRefreshing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null); const [rememberDeleteChoice, setRememberDeleteChoice] = useState(false);
  const deletePromptKey = "medical_evals_skip_delete_prompt";
  async function performDelete(taskId: string) { try { await api(`/api/v1/evaluations/${taskId}`, { method: "DELETE" }); setTasks((items) => items.filter((item) => item.run_id !== taskId)); setNotice(t("deleted")); } catch (cause) { setError(cause instanceof Error ? cause.message : t("unableLoadTasks")); } }
  function removeTask(taskId: string) { if (window.localStorage.getItem(deletePromptKey) === "true") { void performDelete(taskId); return; } setDeleteTarget(taskId); setRememberDeleteChoice(false); }
  function closeDeleteDialog() { setDeleteTarget(null); setRememberDeleteChoice(false); }
  function confirmDelete() { if (!deleteTarget) return; if (rememberDeleteChoice) window.localStorage.setItem(deletePromptKey, "true"); const taskId = deleteTarget; closeDeleteDialog(); void performDelete(taskId); }
  async function cancelTask(taskId: string) { if (!window.confirm(t("cancelConfirm"))) return; try { const updated = await api<TaskSummary>(`/api/v1/evaluations/${taskId}/cancel`, { method: "POST" }); setTasks((items) => items.map((item) => item.run_id === taskId ? updated : item)); setNotice(t("cancelled")); } catch (cause) { setError(cause instanceof Error ? cause.message : t("unableLoadTasks")); } }
  async function retryTask(taskId: string) { if (!window.confirm(t("retryConfirm"))) return; try { const created = await api<TaskSummary>(`/api/v1/evaluations/${taskId}/retry`, { method: "POST" }); setTasks((items) => [created, ...items]); setNotice(t("retryCreated")); } catch (cause) { setError(cause instanceof Error ? cause.message : t("unableLoadTasks")); } }
  async function resumeTask(taskId: string) { return retryTask(taskId); }
  const load = useCallback(async (manual = false) => { if (manual) setRefreshing(true); try { setTasks(await api<TaskSummary[]>("/api/v1/evaluations?limit=200")); setError(""); } catch { setError(t("unableLoadTasks")); } finally { setLoading(false); setRefreshing(false); } }, [t]);
  useEffect(() => { void load(); const timer = window.setInterval(() => { if (document.visibilityState === "visible") void load(); }, 3000); const wake = () => void load(); document.addEventListener("visibilitychange", wake); return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", wake); }; }, [load]);
  const visibleTasks = filterTasks(tasks, query, status); const runningCount = tasks.filter((task) => ["queued", "running"].includes(task.status)).length;
  return <main className="shell"><PageHeader eyebrow={t("evaluations")} title={t("evaluations")} description={t("controlLead")} action={<div className="page-header-actions"><button type="button" className="action secondary" onClick={() => void load(true)} disabled={refreshing}><RefreshIcon size={17} />{t("refresh")}</button><Link className="action" href="/app/evaluations/new"><PlusIcon size={17} />{t("newEvaluation")}</Link></div>} />{error && <InlineAlert tone="error">{error}</InlineAlert>}{notice && <InlineAlert tone="success">{notice}</InlineAlert>}<EvaluationFilters query={query} status={status} onQueryChange={setQuery} onStatusChange={setStatus} /><div className="list-summary"><span><strong>{visibleTasks.length}</strong> {t("visibleRuns")}</span><span>{runningCount} {t("activeRuns")}</span></div>{loading ? <div className="panel loading-list"><Skeleton /><Skeleton /><Skeleton /></div> : <EvaluationTable tasks={visibleTasks} onDelete={removeTask} onCancel={cancelTask} onRetry={retryTask} onResume={resumeTask} />}{deleteTarget && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDeleteDialog(); }}><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title" aria-describedby="delete-dialog-hint"><div className="dialog-icon" aria-hidden="true">!</div><h2 id="delete-dialog-title">{t("deleteDialogTitle")}</h2><p id="delete-dialog-hint" className="hint">{t("deleteDialogHint")}</p><label className="dialog-option"><input type="checkbox" checked={rememberDeleteChoice} onChange={(event) => setRememberDeleteChoice(event.target.checked)} />{t("deleteDialogDontShow")}</label><div className="dialog-actions"><button className="action secondary" type="button" onClick={closeDeleteDialog}>{t("cancelAction")}</button><button className="action dialog-danger" type="button" onClick={confirmDelete}>{t("confirmDelete")}</button></div></section></div>}</main>;
}
