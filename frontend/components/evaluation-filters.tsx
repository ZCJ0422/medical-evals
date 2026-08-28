import { SearchIcon, SlidersIcon } from "./icons";
import type { TaskStatus } from "../lib/types";
import { useLocale } from "../lib/i18n";

export function EvaluationFilters({ query, status, onQueryChange, onStatusChange }: { query: string; status: "all" | TaskStatus; onQueryChange: (value: string) => void; onStatusChange: (value: "all" | TaskStatus) => void }) {
  const { t } = useLocale();
  const statusFilters: Array<{ value: "all" | TaskStatus; label: string }> = [
    { value: "all", label: t("allStatuses") }, { value: "queued", label: t("queuedStatus") }, { value: "running", label: t("runningStatus") }, { value: "completed", label: t("completedStatus") }, { value: "partial_failed", label: t("partialFailedStatus") }, { value: "failed", label: t("failedStatus") }, { value: "cancelled", label: t("cancelledStatus") },
  ];
  return <div className="toolbar" aria-label={t("searchEvaluations")}><label className="search-field"><SearchIcon size={18} /><span className="sr-only">{t("searchEvaluations")}</span><input aria-label={t("searchEvaluations")} value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder={t("searchPlaceholder")} /></label><label className="filter-select"><SlidersIcon size={16} /><span className="sr-only">{t("filterByStatus")}</span><select aria-label={t("filterByStatus")} value={status} onChange={(event) => onStatusChange(event.target.value as "all" | TaskStatus)}>{statusFilters.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>;
}

export function filterTasks(tasks: import("../lib/types").TaskSummary[], query: string, status: "all" | TaskStatus) {
  const needle = query.trim().toLowerCase();
  return tasks.filter((task) => (status === "all" || task.status === status) && (!needle || [task.name, task.target_model_id, task.judge_model_id, task.dataset_version_id, task.run_id].some((value) => value.toLowerCase().includes(needle))));
}
