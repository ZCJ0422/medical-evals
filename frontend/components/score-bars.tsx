import { ProgressBar } from "./ui";

export function ScoreBars({ scores }: { scores: Record<string, number> }) {
  const entries = Object.entries(scores);
  if (!entries.length) return <p className="muted">No dimension scores recorded.</p>;
  return <div className="score-list">{entries.map(([name, score]) => { const percent = Math.max(0, Math.min(100, score * 100)); return <div className="score-row" key={name}><div className="score-row-head"><span className="bar-label">{name}</span><strong>{percent.toFixed(1)}%</strong></div><ProgressBar value={percent} label={`${name} score`} /></div>; })}</div>;
}
