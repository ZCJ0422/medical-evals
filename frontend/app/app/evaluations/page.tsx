import Link from "next/link";

export default function EvaluationsPage() {
  return <main className="shell"><p className="eyebrow">Evaluations</p><h1>Runs</h1><p className="lede">Track queued, running, and completed evaluation tasks.</p><Link className="action" href="/app/evaluations/new">New evaluation</Link><div className="empty-state"><strong>No saved runs</strong><span>Results and reports will appear here after the first run.</span></div></main>;
}
