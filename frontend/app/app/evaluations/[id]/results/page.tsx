"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeftIcon } from "../../../../../components/icons";
import { ResultSummaryView, type ResultSummary } from "../../../../../components/result-summary";
import { InlineAlert, Skeleton } from "../../../../../components/ui";
import { api } from "../../../../../lib/api";
import { useLocale } from "../../../../../lib/i18n";

type RubricJudgment = { criterion?: string; points?: number; tags?: string[]; criteria_met?: boolean; explanation?: string };
type SampleRecord = { index: number; sample_id: string; predicted?: string | null; raw_output?: string | null; correct?: boolean; parse_failed?: boolean; error?: string | null; score?: number; achieved?: number; positive_max?: number; rubric_judgments?: RubricJudgment[]; rubric_results?: RubricJudgment[] };
type SamplesResponse = { samples: SampleRecord[]; total?: number };
const PAGE_SIZE = 50;

function copyText(text: string) {
  if (navigator.clipboard) return navigator.clipboard.writeText(text);
  const textarea = document.createElement("textarea"); textarea.value = text; textarea.style.position = "fixed"; textarea.style.opacity = "0"; document.body.appendChild(textarea); textarea.select(); document.execCommand("copy"); textarea.remove(); return Promise.resolve();
}

function HealthBenchRubrics({ sample }: { sample: SampleRecord }) {
  const judgments = sample.rubric_judgments ?? sample.rubric_results ?? [];
  return <details className="rubric-details" open>
    <summary>Rubric 评分明细</summary>
    <div className="rubric-list">{judgments.length ? judgments.map((judgment, index) => <div className="rubric-item" key={`${judgment.criterion ?? "rubric"}-${index}`}>
      <div className="rubric-item-heading"><strong>Rubric {index + 1}</strong><span className={judgment.criteria_met ? "rubric-met" : "rubric-not-met"}>{judgment.criteria_met ? "满足" : "未满足"}{typeof judgment.points === "number" ? ` · ${judgment.points} 分` : ""}</span></div>
      {judgment.criterion && <p className="rubric-criterion">{judgment.criterion}</p>}
      {judgment.explanation && <p>{judgment.explanation}</p>}
    </div>) : <p>暂无 rubric 评分明细。</p>}</div>
  </details>;
}

export default function ResultsPage() {
  const { t } = useLocale(); const params = useParams<{ id: string }>();
  const [summary, setSummary] = useState<ResultSummary | null>(null); const [samples, setSamples] = useState<SampleRecord[]>([]); const [sampleTotal, setSampleTotal] = useState(0); const [runLog, setRunLog] = useState(""); const [error, setError] = useState(""); const [reportState, setReportState] = useState<"idle" | "busy">("idle"); const [copied, setCopied] = useState<string | null>(null); const [filter, setFilter] = useState<"all" | "issues" | "low">("all"); const [followLogs, setFollowLogs] = useState(true); const logRef = useRef<HTMLPreElement>(null); const sampleTotalRef = useRef(0); const samplesLoadedRef = useRef(false);
  const isLive = summary?.status === "queued" || summary?.status === "running";

  const loadSamples = useCallback(async (offset: number, append = false) => {
    const records = await api<SamplesResponse>(`/api/v1/evaluations/${params.id}/samples?limit=${PAGE_SIZE}&offset=${offset}`);
    setSamples((current) => append ? [...current, ...records.samples] : records.samples);
    const total = records.total ?? (append ? offset + records.samples.length : records.samples.length);
    sampleTotalRef.current = total;
    samplesLoadedRef.current = true;
    setSampleTotal(total);
  }, [params.id]);
  const load = useCallback(async (includeSamples = true) => {
    const result = await api<any>(`/api/v1/evaluations/${params.id}/summary`); const normalized = { ...result, task_id: result.run_id, stage: result.progress?.stage, progress_percent: result.progress?.progress_percent }; setSummary(normalized); setRunLog(""); if (includeSamples) await loadSamples(0); return normalized;
  }, [loadSamples, params.id]);
  useEffect(() => { load().catch(() => setError(t("unableLoadResults"))); }, [load, t]);
  useEffect(() => { if (!isLive) return; const timer = window.setInterval(() => { load(false).then((result) => { if (!samplesLoadedRef.current) return undefined; const persistedSampleCount = result.completed_count + result.failed_count; if (persistedSampleCount !== sampleTotalRef.current) return loadSamples(0); return undefined; }).catch(() => undefined); }, 3000); return () => window.clearInterval(timer); }, [isLive, load, loadSamples]);
  useEffect(() => { if (followLogs && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [followLogs, runLog]);

  const visibleSamples = useMemo(() => samples.filter((sample) => filter === "all" || (filter === "issues" ? Boolean(sample.error || sample.parse_failed) : typeof sample.score === "number" && sample.score < .5)), [filter, samples]);
  async function copyWithNotice(text: string, key: string) { if (!text) return; await copyText(text); setCopied(key); window.setTimeout(() => setCopied((value) => value === key ? null : value), 1600); }
  function downloadLog() { const url = URL.createObjectURL(new Blob([runLog], { type: "text/plain;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `${summary?.name ?? "evaluation"}.log`; link.click(); URL.revokeObjectURL(url); }

  if (error) return <main className="shell"><InlineAlert tone="error">{error}</InlineAlert><Link href="/app/evaluations" className="back-link"><ArrowLeftIcon size={16} />{t("backToEvaluations")}</Link></main>;
  if (!summary) return <main className="shell"><Skeleton className="skeleton-title" /><div className="metric-grid">{[1, 2, 3, 4].map((item) => <div className="metric-card" key={item}><Skeleton /><Skeleton /></div>)}</div></main>;
  const isHealthbench = typeof summary.dimension_scores.rubric_score === "number";
  return <main className="shell"><Link href="/app/evaluations" className="back-link"><ArrowLeftIcon size={16} />{t("backToEvaluations")}</Link><ResultSummaryView summary={summary} runLog={runLog} followLogs={followLogs} onFollowLogsChange={setFollowLogs} logRef={logRef} onCopyLog={() => copyWithNotice(runLog, "log")} onDownloadLog={downloadLog} /><section className="result-section"><div className="section-heading sample-review-heading"><div><p className="eyebrow">{t("sampleRecords")}</p><h2>{t("sampleRecords")}</h2></div><div className="sample-filters"><button className={filter === "all" ? "filter-button active" : "filter-button"} onClick={() => setFilter("all")}>{t("showAllSamples")}</button><button className={filter === "issues" ? "filter-button active" : "filter-button"} onClick={() => setFilter("issues")}>{t("showIssuesOnly")}</button>{isHealthbench && <button className={filter === "low" ? "filter-button active" : "filter-button"} onClick={() => setFilter("low")}>{t("showLowScores")}</button>}</div></div>{visibleSamples.length ? <div className="sample-record-list">{visibleSamples.map((sample) => <article className="sample-record" key={`${sample.index}-${sample.sample_id}`}><div className="sample-record-heading"><strong>{t("sampleNumber")} {sample.index + 1}{t("sampleUnit")}</strong>{isHealthbench ? <div className="sample-score"><strong className={`sample-status ${sample.error ? "sample-status-danger" : "sample-status-success"}`}>{sample.error ? t("sampleError") : `得分 ${typeof sample.score === "number" ? `${(sample.score * 100).toFixed(1)}%` : "—"}`}</strong>{typeof sample.achieved === "number" && typeof sample.positive_max === "number" && <span>{sample.achieved} / {sample.positive_max} 分</span>}</div> : <strong className={`sample-status ${sample.error || sample.parse_failed ? "sample-status-danger" : sample.correct ? "sample-status-success" : "sample-status-warning"}`}>{sample.error ? t("sampleError") : sample.correct ? t("correctLabel") : t("incorrectLabel")}</strong>}</div><pre className="sample-raw-output">{sample.raw_output ?? sample.predicted ?? t("noRawAnswer")}</pre>{isHealthbench && <HealthBenchRubrics sample={sample} />}{sample.error && <p className="sample-error">{sample.error}</p>}</article>)}</div> : <p className="muted">{t("noSampleRecords")}</p>}{samples.length < sampleTotal && <button className="action secondary load-more" onClick={() => loadSamples(samples.length, true)}>{t("loadMoreSamples")}</button>}</section></main>;
}
