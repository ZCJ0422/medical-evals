import type { ReactNode, RefObject } from "react";
import { MetricCard, StatusBadge } from "./ui";
import { ScoreBars } from "./score-bars";
import { useLocale } from "../lib/i18n";

export type ResultSummary = {
  task_id: string;
  name: string;
  status: string;
  dataset_version_id: string;
  target_model_id: string;
  judge_model_id: string;
  created_at: string;
  updated_at: string;
  error: string | null;
  stage: string;
  progress_percent: number;
  total_score: number;
  dimension_scores: Record<string, number>;
  accuracy: number;
  parse_success_rate: number | null;
  request_success_count: number;
  parse_failed_count: number;
  error_categories: Record<string, number>;
  completed_count: number;
  failed_count: number;
  retry_count: number;
};

const stageKey: Record<string, string> = { queued: "stageQueued", preparing: "stagePreparing", target_model: "stageTargetModel", judge_model: "stageJudgeModel", parsing: "stageParsing", scoring: "stageScoring", saving: "stageSaving", completed: "stageCompleted", partial_failed: "stagePartialFailed", failed: "stageFailed" };

export function ResultSummaryView({ summary, runLog, onCopyLog, onDownloadLog, followLogs, onFollowLogsChange, logRef, action }: { summary: ResultSummary; runLog: string; onCopyLog: () => void; onDownloadLog: () => void; followLogs: boolean; onFollowLogsChange: (next: boolean) => void; logRef?: RefObject<HTMLPreElement | null>; action?: ReactNode }) {
  const { t } = useLocale();
  const errorEntries = Object.entries(summary.error_categories);
  const parseValue = summary.parse_success_rate === null ? "—" : `${(summary.parse_success_rate * 100).toFixed(1)}%`;
  const isRubricBased = typeof summary.dimension_scores.rubric_score === "number";
  const stage = t(stageKey[summary.stage] ?? "stagePreparing");
  const updatedAt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(new Date(summary.updated_at));
  return <>
    <div className="result-heading"><div><p className="eyebrow">{t("evaluationResults")}</p><h1>{summary.name}</h1><p className="task-id">Task {summary.task_id}</p></div><div className="result-heading-actions"><StatusBadge status={summary.status} />{action}</div></div>
    <div className="result-meta"><span>{t("dataset")}: <strong>{summary.dataset_version_id}</strong></span><span>{t("target")}: <strong>{summary.target_model_id}</strong></span>{summary.judge_model_id && <span>{t("judgePrefix")}: <strong>{summary.judge_model_id}</strong></span>}<span>{t("currentStage")}: <strong>{stage}</strong></span><span>{t("lastUpdated")}: <strong>{updatedAt}</strong></span></div>
    {summary.error && <div className="task-detail-error" role="alert"><strong>{t("latestIssue")}</strong><span>{summary.error}</span></div>}
    <section className="metric-grid">{isRubricBased ? <><MetricCard label={t("totalScore")} value={`${(summary.total_score * 100).toFixed(1)}%`} tone={summary.total_score >= .8 ? "success" : "warning"} /><MetricCard label={t("scoredSamples")} value={summary.completed_count} /><MetricCard label={t("requestSuccess")} value={summary.request_success_count} /><MetricCard label={t("failedSamples")} value={summary.failed_count} tone={summary.failed_count ? "warning" : "default"} /></> : <><MetricCard label={t("parseSuccessRate")} value={parseValue} tone={summary.parse_success_rate === null || summary.parse_success_rate >= .8 ? "success" : "warning"} /><MetricCard label={t("accuracy")} value={`${(summary.accuracy * 100).toFixed(1)}%`} tone={summary.accuracy >= .8 ? "success" : "warning"} /><MetricCard label={t("requestSuccess")} value={summary.request_success_count} /><MetricCard label={t("parseFailed")} value={summary.parse_failed_count} tone={summary.parse_failed_count ? "warning" : "default"} /></>}</section>
    <div className="result-analysis-grid"><section className="result-section"><div className="section-heading"><div><p className="eyebrow">{t("rubricAnalysis")}</p><h2>{t("dimensionScores")}</h2></div></div><ScoreBars scores={summary.dimension_scores} /></section><section className="result-section"><div className="section-heading"><div><p className="eyebrow">{t("reliability")}</p><h2>{t("errorBreakdown")}</h2></div></div>{errorEntries.length ? <div className="error-breakdown">{errorEntries.map(([name, count]) => <div className="error-row" key={name}><span>{name}</span><strong>{count}</strong></div>)}</div> : <p className="muted">{t("noExecutionErrors")}</p>}</section></div>
    <section className="result-section run-log-section"><div className="section-heading"><div><p className="eyebrow">{t("runLog")}</p><h2>{t("runLog")}</h2></div><div className="log-actions"><label><input type="checkbox" checked={followLogs} onChange={(event) => onFollowLogsChange(event.target.checked)} />{t("followLatest")}</label><button type="button" className="copy-button" onClick={onCopyLog}>{t("copyLog")}</button><button type="button" className="copy-button" onClick={onDownloadLog}>{t("downloadLog")}</button></div></div>{runLog ? <pre ref={logRef} className="run-log">{runLog}</pre> : <p className="muted">{t("noRunLog")}</p>}</section>
  </>;
}
