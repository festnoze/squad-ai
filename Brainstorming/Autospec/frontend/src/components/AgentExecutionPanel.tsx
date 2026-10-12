import { useEffect, useState } from "react";
import type { AgentExecution } from "../types";
import { useI18n } from "../i18n/i18n";

export function AgentExecutionPanel({ activities = {}, incomplete = false }: {
  activities?: Record<string, AgentExecution>;
  incomplete?: boolean;
}) {
  const { t } = useI18n();
  const [now, setNow] = useState(Date.now());
  const rows = Object.entries(activities).sort(([a], [b]) => a.localeCompare(b));
  useEffect(() => {
    if (!rows.length) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [rows.length]);
  if (!rows.length && !incomplete) return null;
  const active = Math.max(0, ...rows.map(([, a]) => a.active_provider_calls || 0));
  const labels: Record<string, string> = {
    waiting_budget: "activity.waitingBudget", provider: "activity.providerExecuting",
    waiting_claim: "activity.waitingClaim", waiting_dependency: "activity.waitingDependency",
    dependency: "activity.resolvingDependency", tests: "activity.executingTests",
    waiting_merge: "activity.waitingMerge", merging: "activity.merging",
    repair: "activity.repairing", preparing: "activity.preparing",
  };
  return <section className="panel" aria-label={t("activity.executionTitle")} data-testid="agent-execution">
    <p>{t("activity.providerActive", { n: active })}</p>
    {rows.length > 0 && <ul>{rows.map(([id, activity]) => <li key={id}>
      {id} — {t(labels[activity.phase] || "activity.unknownExecution")}
      {" · "}{Math.max(0, Math.round(now / 1000 - (activity.since || now / 1000)))} s
      {activity.owner?.length ? ` (${activity.owner.join(", ")})` : ""}
    </li>)}</ul>}
    {(incomplete || rows.some(([, a]) => a.cost_incomplete)) &&
      <p role="status">{t("activity.costIncomplete")}</p>}
  </section>;
}
