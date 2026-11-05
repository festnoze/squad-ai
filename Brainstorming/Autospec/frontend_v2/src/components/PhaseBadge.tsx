import type { Phase } from "../api";
import { PHASE_LABELS } from "../format";

export function PhaseBadge({ phase, running }: { phase: Phase; running?: boolean }) {
  return (
    <span className="badges">
      <span className={`badge phase-${phase}`}>{PHASE_LABELS[phase] ?? phase}</span>
      {running && <span className="badge running">en cours</span>}
    </span>
  );
}
