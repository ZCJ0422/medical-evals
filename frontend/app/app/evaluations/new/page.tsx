"use client";

import { FormEvent, useState } from "react";

export default function NewEvaluationPage() {
  const [submitted, setSubmitted] = useState(false);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSubmitted(true); }
  return <main className="shell"><p className="eyebrow">New evaluation</p><h1>Configure a run</h1><form className="form" onSubmit={submit}><label>Run name<input name="name" required placeholder="HealthBench smoke" /></label><label>Target model<input name="target" required placeholder="model-id" /></label><label>Judge Model<input name="judge" required placeholder="judge-model-id" /></label><label>Dataset version<select name="dataset" defaultValue="healthbench-v1"><option value="healthbench-v1">HealthBench · v1</option></select></label><button className="action" type="submit">Preflight and continue</button>{submitted && <p role="status">Preflight request ready for API integration.</p>}</form></main>;
}
