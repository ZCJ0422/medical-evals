"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import { useLocale } from "../lib/i18n";
import type { DatasetVersion } from "../lib/types";
import { ArrowLeftIcon, ArrowRightIcon, CheckIcon } from "./icons";
import { InlineAlert } from "./ui";

export type WizardDraft = { name: string; target_model_id: string; target_base_url: string; target_api_key: string; dataset_version_id: string; judge_model_id: string; judge_base_url: string; judge_api_key: string; max_samples: string };
const initialDraft: WizardDraft = { name: "", target_model_id: "", target_base_url: "https://api.openai.com/v1", target_api_key: "", dataset_version_id: "", judge_model_id: "", judge_base_url: "https://api.openai.com/v1", judge_api_key: "", max_samples: "" };

export function EvaluationWizard({ datasets }: { datasets: DatasetVersion[] }) {
  const router = useRouter();
  const { t } = useLocale();
  const [draft, setDraft] = useState<WizardDraft>(initialDraft);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedDataset = datasets.find((dataset) => dataset.dataset_version_id === draft.dataset_version_id);
  const needsJudge = Boolean(draft.dataset_version_id) && !draft.dataset_version_id.startsWith("medical-medqa");

  function update(field: keyof WizardDraft, value: string) { setDraft((current) => ({ ...current, [field]: value })); setError(""); }
  function validate(currentStep: number) {
    const errors: string[] = [];
    if (currentStep === 0 && !draft.dataset_version_id) errors.push(t("datasetRequired"));
    if (currentStep === 1) {
      if (!draft.target_model_id || !draft.target_base_url || !draft.target_api_key) errors.push(t("targetRequired"));
      if (needsJudge && (!draft.judge_model_id || !draft.judge_base_url || !draft.judge_api_key)) errors.push(t("judgeRequiredError"));
    }
    return errors;
  }
  function next() { const errors = validate(step); if (errors.length) { setError(errors.join(" ")); return; } setStep((current) => Math.min(3, current + 1)); setError(""); }
  function previous() { setStep((current) => Math.max(0, current - 1)); setError(""); }
  async function submit() {
    const errors = [...validate(0), ...validate(1)];
    if (errors.length) { setError(errors.join(" ")); setStep(errors.some((item) => item === t("datasetRequired")) ? 0 : 1); return; }
    setBusy(true); setError(""); setMessage("");
    const rubric_id = selectedDataset?.rubric_id ?? "";
    const payload = { name: draft.name, target_model_id: draft.target_model_id, judge_model_id: needsJudge ? draft.judge_model_id : "", dataset_version_id: draft.dataset_version_id, rubric_id, target_base_url: draft.target_base_url, target_api_key: draft.target_api_key, judge_base_url: needsJudge ? draft.judge_base_url : "", judge_api_key: needsJudge ? draft.judge_api_key : "", max_samples: draft.max_samples ? Number(draft.max_samples) : null };
    try {
      const check = await api<{ ready: boolean; errors: string[] }>("/api/evaluations/preflight", { method: "POST", body: JSON.stringify(payload) });
      if (!check.ready) throw new Error(check.errors.join(" "));
      const task = await api<{ task_id: string }>("/api/evaluations", { method: "POST", body: JSON.stringify(payload) });
      setMessage(`${t("runQueued")}${task.task_id}`);
      window.setTimeout(() => router.push("/app/evaluations"), 700);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to create evaluation."); } finally { setBusy(false); }
  }

  const steps = [t("chooseDataset"), t("configureModels"), t("setRunOptions"), t("reviewLaunch")];
  return <div className="wizard-layout"><div><div className="wizard-steps" aria-label={t("configure")}>
    {steps.map((label, index) => <div className={`wizard-step ${step === index ? "active" : ""} ${step > index ? "done" : ""}`} key={label}><span className="wizard-step-number">{step > index ? <CheckIcon size={15} /> : `0${index + 1}`}</span><span>{label}</span></div>)}
  </div><section className="form card wizard-card">
    {step === 0 && <fieldset className="wizard-fieldset"><legend>{t("chooseDataset")}</legend><p className="hint">{t("chooseDatasetHint")}</p><label>{t("datasetVersion")} <span className="field-badge">{t("required")}</span><select name="dataset_version_id" aria-label={`${t("datasetVersion")} ${t("required")}`} value={draft.dataset_version_id} onChange={(event) => update("dataset_version_id", event.target.value)}><option value="">{t("selectDataset")}</option>{datasets.map((dataset) => <option key={dataset.dataset_version_id} value={dataset.dataset_version_id}>{dataset.name} · {dataset.version} · {dataset.sample_count.toLocaleString()} samples</option>)}</select></label>{selectedDataset && <InlineAlert tone="info">{needsJudge ? t("rubricDatasetInfo") : t("exactDatasetInfo")}</InlineAlert>}</fieldset>}
    {step === 1 && <fieldset className="wizard-fieldset"><legend>{t("configureModels")}</legend><p className="hint">{t("configureModelsHint")}</p><label>{t("targetModel")} <span className="field-badge">{t("required")}</span><input name="target_model_id" aria-label={`${t("targetModel")} ${t("required")}`} value={draft.target_model_id} onChange={(event) => update("target_model_id", event.target.value)} placeholder="qwen-plus" /></label><label>{t("targetBaseUrl")} <span className="field-badge">{t("required")}</span><input name="target_base_url" aria-label={`${t("targetBaseUrl")} ${t("required")}`} value={draft.target_base_url} onChange={(event) => update("target_base_url", event.target.value)} placeholder="https://api.example.com/v1" /></label><label>{t("targetApiKey")} <span className="field-badge">{t("required")}</span><input name="target_api_key" aria-label={`${t("targetApiKey")} ${t("required")}`} value={draft.target_api_key} onChange={(event) => update("target_api_key", event.target.value)} type="password" autoComplete="off" placeholder="Stored only for this run" /></label>{needsJudge && <div className="conditional-fields"><legend>{t("judgeModel")}</legend><label>{t("judgeModel")} <span className="field-badge">{t("required")}</span><input name="judge_model_id" aria-label={`${t("judgeModel")} ${t("required")}`} value={draft.judge_model_id} onChange={(event) => update("judge_model_id", event.target.value)} placeholder="gpt-4o" /></label><label>{t("judgeBaseUrl")} <span className="field-badge">{t("required")}</span><input name="judge_base_url" aria-label={`${t("judgeBaseUrl")} ${t("required")}`} value={draft.judge_base_url} onChange={(event) => update("judge_base_url", event.target.value)} placeholder="https://api.example.com/v1" /></label><label>{t("judgeApiKey")} <span className="field-badge">{t("required")}</span><input name="judge_api_key" aria-label={`${t("judgeApiKey")} ${t("required")}`} value={draft.judge_api_key} onChange={(event) => update("judge_api_key", event.target.value)} type="password" autoComplete="off" placeholder="Stored only for this run" /></label></div>}</fieldset>}
    {step === 2 && <fieldset className="wizard-fieldset"><legend>{t("setRunOptions")}</legend><p className="hint">{t("setRunOptionsHint")}</p><label>{t("runName")} <span className="field-badge optional-badge">{t("optional")}</span><input name="name" aria-label={`${t("runName")} ${t("optional")}`} value={draft.name} onChange={(event) => update("name", event.target.value)} placeholder={t("healthbenchSmoke")} /></label><label>{t("maxSamples")} <span className="field-badge optional-badge">{t("optional")}</span><input name="max_samples" aria-label={`${t("maxSamples")} ${t("optional")}`} value={draft.max_samples} onChange={(event) => update("max_samples", event.target.value)} type="number" min="1" max="10000" placeholder={t("emptyFullDataset")} /></label></fieldset>}
    {step === 3 && <fieldset className="wizard-fieldset"><legend>{t("reviewLaunch")}</legend><p className="hint">{t("reviewLaunchHint")}</p><div className="inline-review"><div className="review-row"><span>{t("dataset")}</span><strong>{selectedDataset?.name ?? "—"} · {selectedDataset?.version ?? "—"}</strong></div><div className="review-row"><span>{t("targetModel")}</span><strong>{draft.target_model_id || "—"}</strong></div><div className="review-row"><span>{t("judgeModel")}</span><strong>{needsJudge ? draft.judge_model_id || "—" : t("notRequired")}</strong></div><div className="review-row"><span>{t("runSize")}</span><strong>{draft.max_samples || t("emptyFullDataset")}</strong></div><div className="review-row"><span>{t("credentials")}</span><strong>{t("protected")}</strong></div></div><InlineAlert tone="info">{t("preflightHint")}</InlineAlert></fieldset>}
    {error && <InlineAlert tone="error">{error}</InlineAlert>}{message && <InlineAlert tone="success">{message}</InlineAlert>}<div className="wizard-actions"><button className="action secondary" type="button" onClick={previous} disabled={step === 0 || busy}><ArrowLeftIcon size={16} />{t("back")}</button>{step < 3 ? <button className="action" type="button" onClick={next} disabled={busy}>{t("next")}<ArrowRightIcon size={16} /></button> : <button className="action" type="button" onClick={submit} disabled={busy}>{busy ? t("checking") : t("createEvaluation")}<CheckIcon size={16} /></button>}</div>
  </section></div><aside className="panel review-card"><p className="eyebrow">{t("configurationSummary")}</p><h2>{selectedDataset?.name ?? t("newEvaluation")}</h2><p className="muted">{selectedDataset ? `${selectedDataset.sample_count.toLocaleString()} samples · ${needsJudge ? t("judgeRequired") : t("exactScoring")}` : t("selectedDatasetHint")}</p><div className="review-row"><span>{t("step")}</span><strong>{step + 1} / 4</strong></div><div className="review-row"><span>{t("target")}</span><strong>{draft.target_model_id || t("notSet")}</strong></div></aside></div>;
}
