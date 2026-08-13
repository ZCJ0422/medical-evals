export default function HomePage() {
  return (
    <main className="shell" aria-labelledby="page-title">
      <p className="eyebrow">Internal evaluation workspace</p>
      <h1 id="page-title">Medical Evals</h1>
      <p className="lede">Run reproducible medical language-model evaluations with protected benchmark data.</p>
      <div className="empty-state" role="status">
        <strong>Workspace ready</strong>
        <span>Sign in to configure a model and start an evaluation.</span>
      </div>
    </main>
  );
}
