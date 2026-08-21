"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeftIcon, FileTextIcon } from "../../../../../components/icons";
import { ResultSummaryView, type ResultSummary } from "../../../../../components/result-summary";
import { InlineAlert, Skeleton } from "../../../../../components/ui";
import { api, apiBlob, apiText } from "../../../../../lib/api";
import { useLocale } from "../../../../../lib/i18n";

type RubricJudgment = { criteria_met?: boolean; explanation?: string };
type SampleRecord = { index: number; sample_id: string; predicted?: string | null; raw_output?: string | null; correct?: boolean; parse_failed?: boolean; error?: string | null; score?: number; rubric_judgments?: RubricJudgment[]; rubric_results?: RubricJudgment[] };
type SamplesResponse = { samples: SampleRecord[]; total?: number };
const PAGE_SIZE = 50;

function copyText(text: string) {
  if (navigator.clipboard) return navigator.clipboard.writeText(text);
  const textarea = document.createElement("textarea"); textarea.value = text; textarea.style.position = "fixed"; textarea.style.opacity = "0"; document.body.appendChild(textarea); textarea.select(); document.execCommand("copy"); textarea.remove(); return Promise.resolve();
}

export default function ResultsPage() {
  const { t } = useLocale(); const params = useParams<{ id: string }>();
  const [summary, setSummary] = useState<ResultSummary | null>(null); const [samples, setSamples] = useState<SampleRecord[]>([]); const [sampleTotal, setSampleTotal] = useState(0); const [runLog, setRunLog] = useState(""); const [error, setError] = useState(""); const [reportState, setReportState] = useState<"idle" | "busy">("idle"); const [copied, setCopied] = useState<string | null>(null); const [filter, setFilter] = useState<"all" | "issues" | "low">("all"); const [followLogs, setFollowLogs] = useState(true); const logRef = useRef<HTMLPreElement>(null); const sampleTotalRef = useRef(0); const samplesLoadedRef = useRef(false);
  const isLive = summary?.status === "queued" || summary?.status === "running";

  const loadSamples = useCallback(async (offset: number, append = false) => {
    const records = await api<SamplesResponse>(`/api/evaluations/${params.id}/samples?limit=${PAGE_SIZE}&offset=${offset}`);
    setSamples((current) => append ? [...current, ...records.samples] : records.samples);
    const total = records.total ?? (append ? offset + records.samples.length : records.samples.length);
    sampleTotalRef.current = total;
    samplesLoadedRef.current = true;
    setSampleTotal(total);
  }, [params.id]);
  const load = useCallback(async (includeSamples = true) => {
    const [result, log] = await Promise.all([api<ResultSummary>(`/api/evaluations/${params.id}/results`), apiText(`/api/evaluations/${params.id}/log`)]);
    setSummary(result); setRunLog(log); if (includeSamples) await loadSamples(0); return result;
  }, [loadSamples, params.id]);
  useEffect(() => { load().catch(() => setError(t("unableLoadResults"))); }, [load, t]);
  useEffect(() => { if (!isLive) return; const timer = window.setInterval(() => { load(false).then((result) => { if (!samplesLoadedRef.current) return undefined; const persistedSampleCount = result.completed_count + result.failed_count; if (persistedSampleCount !== sampleTotalRef.current) return loadSamples(0); return undefined; }).catch(() => undefined); }, 3000); return () => window.clearInterval(timer); }, [isLive, load, loadSamples]);
  useEffect(() => { if (followLogs && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [followLogs, runLog]);

  const visibleSamples = useMemo(() => samples.filter((sample) => filter === "all" || (filter === "issues" ? Boolean(sample.error || sample.parse_failed) : typeof sample.score === "number" && sample.score < .5)), [filter, samples]);
  async function copyWithNotice(text: string, key: string) { if (!text) return; await copyText(text); setCopied(key); window.setTimeout(() => setCopied((value) => value === key ? null : value), 1600); }
  async function generateReport() { if (!summary) return; setReportState("busy"); const reportWindow = window.open("about:blank", "_blank"); try { await api(`/api/evaluations/${summary.task_id}/report/generate`, { method: "POST" }); const report = await apiBlob(`/api/evaluations/${summary.task_id}/report`); reportWindow && (reportWindow.location.href = URL.createObjectURL(report)); } catch { reportWindow?.close(); window.alert(t("reportFailed")); } finally { setReportState("idle"); } }
  function downloadLog() { const url = URL.createObjectURL(new Blob([runLog], { type: "text/plain;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `${summary?.name ?? "evaluation"}.log`; link.click(); URL.revokeObjectURL(url); }

  if (error) return <main className="shell"><InlineAlert tone="error">{error}</InlineAlert><Link href="/app/evaluations" className="back-link"><ArrowLeftIcon size={16} />{t("backToEvaluations")}</Link></main>;
  if (!summary) return <main className="shell"><Skeleton className="skeleton-title" /><div className="metric-grid">{[1, 2, 3, 4].map((item) => <div className="metric-card" key={item}><Skeleton /><Skeleton /></div>)}</div></main>;
  const isHealthbench = typeof summary.dimension_scores.rubric_score === "number";
  return <main className="shell"><Link href="/app/evaluations" className="back-link"><ArrowLeftIcon size={16} />{t("backToEvaluations")}</Link><ResultSummaryView summary={summary} runLog={runLog} followLogs={followLogs} onFollowLogsChange={setFollowLogs} logRef={logRef} onCopyLog={() => copyWithNotice(runLog, "log")} onDownloadLog={downloadLog} action={<button className="report-action" onClick={generateReport} disabled={reportState === "busy"} aria-label={t("generateReport")} title={t("generateReport")}><FileTextIcon size={18} /></button>} /><section className="result-section"><div className="section-heading sample-review-heading"><div><p className="eyebrow">{t("sampleRecords")}</p><h2>{t("sampleRecords")}</h2></div><div className="sample-filters" aria-label={t("sampleRecords")}><button className={filter === "all" ? "filter-button active" : "filter-button"} onClick={() => setFilter("all")}>{t("showAllSamples")}</button><button className={filter === "issues" ? "filter-button active" : "filter-button"} onClick={() => setFilter("issues")}>{t("showIssuesOnly")}</button>{isHealthbench && <button className={filter === "low" ? "filter-button active" : "filter-button"} onClick={() => setFilter("low")}>{t("showLowScores")}</button>}</div></div>{visibleSamples.length ? <div className="sample-record-list">{visibleSamples.map((sample) => { const key = `${sample.index}-${sample.sample_id}`; const answer = sample.raw_output ?? sample.predicted ?? ""; const rubricJudgments = sample.rubric_judgments ?? sample.rubric_results ?? []; const hasScore = typeof sample.score === "number"; const status = isHealthbench ? (hasScore ? `${(sample.score! * 100).toFixed(1)}%` : t("scoreUnavailable")) : sample.error ? t("sampleError") : sample.parse_failed ? t("parseFailedLabel") : sample.correct ? t("correctLabel") : t("incorrectLabel"); const statusClass = sample.error || sample.parse_failed ? "sample-status-danger" : isHealthbench ? (hasScore && sample.score! >= .5 ? "sample-status-success" : "sample-status-warning") : sample.correct ? "sample-status-success" : "sample-status-warning"; return <article className="sample-record" key={key}><div className="sample-record-heading"><div><strong>{t("sampleNumber")} {sample.index + 1}{t("sampleUnit")}</strong><span className="sample-id">{t("sampleId")}: {sample.sample_id}</span></div><strong className={`sample-status ${statusClass}`}>{status}</strong></div><div className="sample-raw-block"><div className="sample-raw-heading"><span>{t("rawModelAnswer")}</span><div className="sample-raw-meta">{answer && <button className="copy-button" type="button" onClick={() => copyWithNotice(answer, key)}>{copied === key ? t("copied") : t("copyAnswer")}</button>}</div></div><pre className="sample-raw-output">{answer || t("noRawAnswer")}</pre></div>{rubricJudgments.length ? <details className="rubric-details"><summary>{t("rubricJudgments")}</summary>{rubricJudgments.map((judgment, index) => <p key={index}><strong className={judgment.criteria_met ? "rubric-met" : "rubric-not-met"}>{judgment.criteria_met ? t("met") : t("notMet")}</strong>{judgment.explanation && ` — ${judgment.explanation}`}</p>)}</details> : null}{sample.error && <p className="sample-error">{sample.error}</p>}</article>; })}</div> : <p className="muted">{t("noSampleRecords")}</p>}{samples.length < sampleTotal && <button className="action secondary load-more" onClick={() => loadSamples(samples.length, true)}>{t("loadMoreSamples")}</button>}</section></main>;
}
