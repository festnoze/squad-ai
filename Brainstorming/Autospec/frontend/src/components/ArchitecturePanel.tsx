import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";

interface Props {
  architecture: string;
  planQuality: number;
}

export function ArchitecturePanel({ architecture, planQuality }: Props) {
  const { t } = useI18n();
  const hasArchitecture = architecture.trim() !== "";
  const hasPlanQuality = planQuality >= 0;
  if (!hasArchitecture && !hasPlanQuality) return null;

  return (
    <CollapsibleSection title={t("architecturePanel.title")} className="architecture">
      {hasPlanQuality && (
        <div className="plan-quality">
          {t("architecturePanel.planQuality")} <strong>{planQuality}/100</strong>
        </div>
      )}
      {hasArchitecture && <pre className="architecture-design">{architecture}</pre>}
    </CollapsibleSection>
  );
}
