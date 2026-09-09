"use client";

import { FormEvent, useEffect, useState } from "react";
import { InlineAlert } from "../../../components/ui";
import { PageHeader } from "../../../components/page-header";
import { api } from "../../../lib/api";
import type { EvaluationDefinition, ModelProfile } from "../../../lib/types";

type ConfigValue = { split: string; samples: string; judge: string };

export default function EvaluationConfigPage() {
  const [datasets, setDatasets] = useState<EvaluationDefinition[]>([]);
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [values, setValues] = useState<Record<string, ConfigValue>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([api<EvaluationDefinition[]>("/api/v1/datasets"), api<ModelProfile[]>("/api/v1/models")]).then(([definitions, profiles]) => {
      setDatasets(definitions);
      setModels(profiles.filter((item) => item.has_api_key && item.is_active));
      setValues(Object.fromEntries(definitions.map((item) => [item.id, { split: item.default_split ?? item.splits[0]?.id ?? "", samples: String(item.default_sample_limit ?? item.splits[0]?.default_sample_limit ?? ""), judge: item.judge_model_id ?? "" }])));
    }).catch((cause) => setError(cause instanceof Error ? cause.message : "无法加载测评配置。")).finally(() => setLoading(false));
  }, []);

  async function save(event: FormEvent<HTMLFormElement>, definition: EvaluationDefinition) {
    event.preventDefault();
    const value = values[definition.id];
    if (!value) return;
    setBusy(definition.id); setError(""); setNotice("");
    try {
      const updated = await api<EvaluationDefinition>(`/api/v1/datasets/${definition.id}/config`, { method: "PATCH", body: JSON.stringify({ default_split: value.split, default_sample_limit: Number(value.samples), judge_model_id: definition.requires_judge ? value.judge || null : null }) });
      setValues((current) => ({ ...current, [definition.id]: { split: updated.default_split ?? value.split, samples: String(updated.default_sample_limit ?? value.samples), judge: updated.judge_model_id ?? "" } }));
      setNotice(`${definition.name} 配置已保存。`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存测评配置失败。"); } finally { setBusy(""); }
  }

  return <main className="shell"><PageHeader eyebrow="Workspace" title="测评配置" description="统一设置公众端提交测评时使用的数据集版本、样本数量和 Judge 模型。" />{error && <InlineAlert tone="error">{error}</InlineAlert>}{notice && <InlineAlert tone="success">{notice}</InlineAlert>}{loading ? <div className="panel loading-list"><p className="muted">正在加载配置…</p></div> : <div className="config-list">{datasets.map((definition) => { const value = values[definition.id]; return <form className="panel config-card" key={definition.id} onSubmit={(event) => void save(event, definition)}><div className="section-heading"><div><p className="eyebrow">{definition.requires_judge ? "Rubric evaluation" : "Exact evaluation"}</p><h2>{definition.name}</h2></div><span className="config-status">统一配置</span></div><div className="config-grid"><label>默认数据集版本<select required value={value?.split ?? ""} onChange={(event) => setValues((current) => ({ ...current, [definition.id]: { ...current[definition.id], split: event.target.value } }))}>{definition.splits.map((split) => <option value={split.id} key={split.id}>{split.version} · {split.sample_count.toLocaleString()} 个样本</option>)}</select></label><label>默认样本数量<input required type="number" min="1" max={definition.splits.find((split) => split.id === value?.split)?.sample_count ?? 10000} value={value?.samples ?? ""} onChange={(event) => setValues((current) => ({ ...current, [definition.id]: { ...current[definition.id], samples: event.target.value } }))} /></label>{definition.requires_judge && <label>Judge 模型<select required value={value?.judge ?? ""} onChange={(event) => setValues((current) => ({ ...current, [definition.id]: { ...current[definition.id], judge: event.target.value } }))}><option value="">请选择 Judge 模型</option>{models.map((model) => <option value={model.id} key={model.id}>{model.name} · {model.model_name}</option>)}</select></label>}</div><div className="config-actions"><span className="muted">公众端提交时自动使用以上默认值</span><button className="action" disabled={busy === definition.id}>{busy === definition.id ? "保存中…" : "保存配置"}</button></div></form>; })}</div>}</main>;
}
