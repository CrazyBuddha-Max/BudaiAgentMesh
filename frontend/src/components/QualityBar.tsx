import {ProgressBar} from '@astryxdesign/core/ProgressBar';

/** 质量分进度条: 0-100 */
export function QualityBar({score}: {score: number}) {
  const cls = score >= 85 ? 'q-good' : score >= 60 ? 'q-mid' : 'q-bad';
  return (
    <div style={{minWidth: 120}}>
      <ProgressBar label="质量分" isLabelHidden value={score} max={100} />
      <div className="bar-track">
        <div className={`bar-fill ${cls}`} style={{width: `${Math.max(score, 2)}%`}} />
      </div>
    </div>
  );
}
