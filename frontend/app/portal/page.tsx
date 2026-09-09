"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ActivityIcon } from "../../components/icons";
import { api } from "../../lib/api";
import { currentUser, logout } from "../../lib/auth";
import type { EvaluationDefinition, EvaluationRun, ModelProfile, User } from "../../lib/types";
import { useRouter } from "next/navigation";

type PortalView = "profile" | "submit" | "records";
const emptyEvaluationForm = { definition: "", split: "", modelName: "", baseUrl: "", apiKey: "" };

export default function PublicPortalPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDefinition[]>([]);
  const [form, setForm] = useState(emptyEvaluationForm);
  const [submitting, setSubmitting] = useState(false);
  const [view, setView] = useState<PortalView>("profile");
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([currentUser(), api<EvaluationRun[]>("/api/v1/evaluations"), api<EvaluationDefinition[]>("/api/v1/datasets")])
      .then(([account, items, definitions]) => {
        if (account.role === "admin") {
          router.replace("/app");
          return;
        }
        setUser(account);
        setRuns(items);
        setDatasets(definitions);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "无法加载测评空间。"));
  }, [router]);

  async function signOut() {
    await logout();
    router.replace("/");
  }

  async function showRecords() {
    setView("records");
    setError("");
    try {
      setRuns(await api<EvaluationRun[]>("/api/v1/evaluations"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法刷新提交记录。");
    }
  }

  const selectedDefinition = datasets.find((item) => item.id === form.definition);
  const selectedSplit = selectedDefinition?.splits.find((item) => item.id === form.split);

  async function submitEvaluation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDefinition || !selectedSplit || !form.modelName || !form.baseUrl || !form.apiKey) {
      setError("请填写完整的数据集和模型信息。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const model = await api<ModelProfile>("/api/v1/models", { method: "POST", body: JSON.stringify({ name: form.modelName, model_name: form.modelName, base_url: form.baseUrl, api_key: form.apiKey }) });
      const created = await api<EvaluationRun>("/api/v1/evaluations", { method: "POST", body: JSON.stringify({ name: "", evaluation_definition_id: selectedDefinition.id, target_model_id: model.id, judge_model_id: "", config: {} }) });
      setRuns((items) => [created, ...items]);
      setView("records");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "提交测评失败，请重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="public-site portal-page">
    <nav className="public-nav portal-nav" aria-label="主导航">
      <Link className="public-brand" href="/"><span className="brand-mark"><ActivityIcon size={18} /></span><span>Medical Evals</span></Link>
      <div className="public-nav-links"><Link href="#docs">文档</Link><Link href="#pricing">定价</Link><Link href="/portal">控制台</Link>{user && <div className="account-menu"><button className="account-avatar" type="button" aria-label="打开账号菜单">{user.username.slice(0, 1).toUpperCase()}</button><div className="account-popover"><strong>{user.username}</strong><span>公众用户</span><button type="button" onClick={() => void signOut()}>退出登录</button></div></div>}</div>
    </nav>
    <div className="portal-workspace">
      <aside className="portal-sidebar" aria-label="测评空间菜单">
        <p className="portal-sidebar-title">账户</p>
        <button className={view === "profile" ? "portal-sidebar-item active" : "portal-sidebar-item"} onClick={() => setView("profile")}>个人信息</button>
        <p className="portal-sidebar-title portal-sidebar-group">测评</p>
        <button className={view === "submit" ? "portal-sidebar-item active" : "portal-sidebar-item"} onClick={() => { setForm(emptyEvaluationForm); setError(""); setView("submit"); }}>提交测评</button>
        <button className={view === "records" ? "portal-sidebar-item active" : "portal-sidebar-item"} onClick={() => void showRecords()}>提交记录</button>
      </aside>
      <section className="portal-content">
        {error && <p className="portal-error" role="alert">{error}</p>}
        {view === "profile" && <><header className="portal-content-heading"><h1>个人信息</h1><p>管理你的账户信息和测评记录</p></header><h2 className="portal-section-title">基本信息</h2><section className="portal-panel"><div className="portal-profile"><span className="portal-profile-avatar">{user?.username.slice(0, 1).toUpperCase() ?? "M"}</span><div><span>用户名</span><strong>{user?.username ?? "—"} <button className="portal-inline-action" type="button">修改</button></strong></div></div><dl className="portal-details"><div><dt>手机号</dt><dd>— <button className="portal-inline-action" type="button">修改</button></dd></div><div><dt>邮箱</dt><dd>— <button className="portal-inline-action" type="button">去绑定</button></dd></div><div><dt>UID</dt><dd>—</dd></div></dl></section></>}
        {view === "submit" && <><header className="portal-content-heading"><h1>欢迎参与 Medical Evals 测评</h1><p>填写模型信息和评测数据集，提交一次新的医疗大模型测评</p></header><form className="portal-panel portal-form" onSubmit={submitEvaluation}><label>评测数据集<select required value={form.definition} onChange={(event) => { const definition = datasets.find((item) => item.id === event.target.value); setForm({ ...form, definition: event.target.value, split: definition?.default_split ?? definition?.splits[0]?.id ?? "" }); }}><option value="">请选择数据集</option>{datasets.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Model name<input required value={form.modelName} onChange={(event) => setForm({ ...form, modelName: event.target.value })} placeholder="例如：GPT-4o" /></label><label>Base URL<input required type="url" value={form.baseUrl} onChange={(event) => setForm({ ...form, baseUrl: event.target.value })} placeholder="https://api.example.com/v1" /></label><label>API key<input required type="password" value={form.apiKey} onChange={(event) => setForm({ ...form, apiKey: event.target.value })} autoComplete="off" /></label><button className="portal-primary-button" type="submit" disabled={submitting}>{submitting ? "提交中…" : "提交测评"}</button></form></>}
        {view === "records" && <><header className="portal-content-heading"><h1>提交记录</h1><p>查看你提交过的医疗大模型测评</p></header><section className="portal-panel"><h2>{runs.length ? `${runs.length} 条记录` : "暂无提交记录"}</h2>{runs.length > 0 ? <div className="portal-record-list">{runs.map((run) => <div className="portal-record" key={run.run_id}><div><strong>{run.name || "未命名测评"}</strong><span>{run.dataset_version_id}</span></div><span className="portal-record-status">{run.status}</span></div>)}</div> : <p>你的测评记录会显示在这里。</p>}</section></>}
      </section>
    </div>
  </main>;
}
