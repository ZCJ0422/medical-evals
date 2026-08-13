export default function DashboardPage() {
  return (
    <main className="shell" aria-labelledby="page-title">
      <p className="eyebrow">Admin workbench</p>
      <h1 id="page-title">Evaluation control room</h1>
      <p className="lede">Configure one model, one dataset version, and one independent judge for each reproducible run.</p>
      <div className="empty-state"><strong>No evaluations yet</strong><span>Create a run to see progress and protected result summaries here.</span></div>
    </main>
  );
}
