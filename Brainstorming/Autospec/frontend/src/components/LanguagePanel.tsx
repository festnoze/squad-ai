import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";

interface Props {
  language?: "python" | "go" | "rust";
  complexity?: number;
  criticality?: number;
  rationale?: string;
  onSet: (language: "python" | "go" | "rust") => void;
}

/**
 * L2 : langage backend recommandé (par analyse complexité/criticité) + override.
 * Ne s'affiche qu'une fois l'analyse faite (scores ≥ 0).
 */
export function LanguagePanel({ language, complexity, criticality, rationale, onSet }: Props) {
  const { t } = useI18n();
  // Keep value/emoji as-is; only the surrounding UI is translated.
  const LANGS: { value: "python" | "go" | "rust"; label: string }[] = [
    { value: "python", label: "🐍 Python" },
    { value: "go", label: "🐹 Go" },
    { value: "rust", label: "🦀 Rust" },
  ];
  const analyzed = (complexity ?? -1) >= 0 || (criticality ?? -1) >= 0;
  if (!analyzed || !language) return null;

  return (
    <CollapsibleSection title={t("languagePanel.title")} className="language">
      <div className="language-scores">
        <span className="language-score" title={t("languagePanel.complexityTitle")}>
          {t("languagePanel.complexity")} <strong>{complexity}/5</strong>
        </span>
        <span className="language-score" title={t("languagePanel.criticalityTitle")}>
          {t("languagePanel.criticality")} <strong>{criticality}/5</strong>
        </span>
      </div>
      {rationale && <p className="language-rationale">{rationale}</p>}
      <label className="language-override">
        <span>{t("languagePanel.languageLabel")}</span>
        <select
          aria-label={t("languagePanel.selectAriaLabel")}
          value={language}
          onChange={(e) => onSet(e.target.value as "python" | "go" | "rust")}
        >
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
    </CollapsibleSection>
  );
}
