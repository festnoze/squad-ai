import { useState } from "react";
import { useI18n } from "../i18n/i18n";

interface Props {
  onCreate: (goal: string, name: string, autoSpec: boolean, budgetUsd: number, brief?: string, brownfieldPath?: string) => void;
  busy: boolean;
}

export function ProjectSetup({ onCreate, busy }: Props) {
  const { t } = useI18n();
  const [goal, setGoal] = useState("");
  const [name, setName] = useState("");
  const [autoSpec, setAutoSpec] = useState(false);
  const [budget, setBudget] = useState("");
  const [brief, setBrief] = useState("");
  const [brownfield, setBrownfield] = useState("");

  return (
    <div className="panel setup">
      <h2>{t("projectSetup.title")}</h2>
      <input
        placeholder={t("projectSetup.namePlaceholder")}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <textarea
        placeholder={t("projectSetup.goalPlaceholder")}
        rows={6}
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
      />
      <label className="autospec-toggle">
        <input
          type="checkbox"
          checked={autoSpec}
          onChange={(e) => setAutoSpec(e.target.checked)}
        />
        <span>
          <strong>{t("projectSetup.autoSpecLabel")}</strong>
          {" "}
          {t("projectSetup.autoSpecDescription")}
        </span>
      </label>
      <textarea
        placeholder={t("projectSetup.briefPlaceholder")}
        rows={4}
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
      />
      <input
        aria-label={t("projectSetup.brownfieldAriaLabel")}
        placeholder={t("projectSetup.brownfieldPlaceholder")}
        value={brownfield}
        onChange={(e) => setBrownfield(e.target.value)}
      />
      <input
        type="number"
        aria-label={t("projectSetup.budgetAriaLabel")}
        min={0}
        step={0.1}
        placeholder={t("projectSetup.budgetPlaceholder")}
        value={budget}
        onChange={(e) => setBudget(e.target.value)}
      />
      <button
        className="primary"
        disabled={busy || !goal.trim()}
        onClick={() => onCreate(goal.trim(), name.trim(), autoSpec, Number(budget) || 0, brief.trim() || undefined, brownfield.trim() || undefined)}
      >
        {autoSpec ? t("projectSetup.submitAutoSpec") : t("projectSetup.submitSpec")}
      </button>
    </div>
  );
}
