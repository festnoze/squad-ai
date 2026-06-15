import { CollapsibleSection } from "./CollapsibleSection";

interface Props {
  architecture: string;
  planQuality: number;
}

export function ArchitecturePanel({ architecture, planQuality }: Props) {
  const hasArchitecture = architecture.trim() !== "";
  const hasPlanQuality = planQuality >= 0;
  if (!hasArchitecture && !hasPlanQuality) return null;

  return (
    <CollapsibleSection title="Architecture & qualité" className="architecture">
      {hasPlanQuality && (
        <div className="plan-quality">
          Qualité du plan : <strong>{planQuality}/100</strong>
        </div>
      )}
      {hasArchitecture && <pre className="architecture-design">{architecture}</pre>}
    </CollapsibleSection>
  );
}
