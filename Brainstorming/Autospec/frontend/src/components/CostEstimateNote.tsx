import { useI18n } from "../i18n/i18n";

/** Never infer billing/authentication mode from an estimated dollar amount. */
export function CostEstimateNote({
  withBudget = false,
  unreportedCalls = 0,
}: {
  withBudget?: boolean;
  unreportedCalls?: number;
}) {
  const { t } = useI18n();
  return (
    <details className="cost-estimate-note" open={unreportedCalls > 0}>
      <summary>
        {unreportedCalls > 0
          ? t("common.costEstimateIncomplete", { n: unreportedCalls })
          : t("common.costEstimateAbout")}
      </summary>
      <p>{t("common.costEstimateHint")}</p>
      {withBudget && <p>{t("common.budgetEstimateHint")}</p>}
    </details>
  );
}
