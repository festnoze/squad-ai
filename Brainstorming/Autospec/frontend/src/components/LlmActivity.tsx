import { useCallback, useEffect, useState } from "react";
import { getItemInteractions } from "../api";
import { useI18n } from "../i18n/i18n";
import { AgentInteraction } from "../types";

/** Agent role → icon + label translation key. Covers the build crew and the
 *  planning personas, so a call captured under "phase:spec" (pm) reads as nicely
 *  as a dev/qa/critic call captured under a story. */
const ROLE_META: Record<string, { icon: string; labelKey: string }> = {
  dev: { icon: "👨‍💻", labelKey: "llmActivity.roleDev" },
  "dev-frontend": { icon: "🎨", labelKey: "llmActivity.roleDevFrontend" },
  qa: { icon: "🧪", labelKey: "llmActivity.roleQa" },
  critic: { icon: "🔍", labelKey: "llmActivity.roleCritic" },
  judge: { icon: "⚖️", labelKey: "llmActivity.roleJudge" },
  architect: { icon: "🏛️", labelKey: "llmActivity.roleArchitect" },
  analyst: { icon: "📊", labelKey: "llmActivity.roleAnalyst" },
  pm: { icon: "📋", labelKey: "llmActivity.rolePm" },
  sm: { icon: "🗂", labelKey: "llmActivity.roleSm" },
  "tech-writer": { icon: "📝", labelKey: "llmActivity.roleTechWriter" },
  evaluator: { icon: "🕵️", labelKey: "llmActivity.roleEvaluator" },
  "security-reviewer": { icon: "🛡️", labelKey: "llmActivity.roleSecurityReviewer" },
  retro: { icon: "🔄", labelKey: "llmActivity.roleRetro" },
};

/** Poll cadence while the item is live (a build in flight). */
const POLL_MS = 3000;

function roleMeta(
  persona: string,
  phase: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
) {
  const known = ROLE_META[persona];
  if (known) return { icon: known.icon, label: t(known.labelKey) };
  return {
    icon: "🤖",
    label: persona || (phase ? phase.replace(/^phase:/, "") : "agent"),
  };
}

/** Short "time ago" for a unix-seconds timestamp. */
function timeAgo(
  ts: number,
  now: number,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const s = Math.max(0, Math.round(now / 1000 - ts));
  if (s < 60) return t("llmActivity.timeAgoSeconds", { s });
  const m = Math.round(s / 60);
  if (m < 60) return t("llmActivity.timeAgoMinutes", { m });
  const h = Math.round(m / 60);
  return t("llmActivity.timeAgoHours", { h });
}

function tokens(it: AgentInteraction): string {
  const parts: string[] = [];
  if (it.input_tokens) parts.push(`${it.input_tokens.toLocaleString()} in`);
  if (it.output_tokens) parts.push(`${it.output_tokens.toLocaleString()} out`);
  return parts.join(" / ");
}

/** One captured round-trip: collapsed = header line; expanded = prompt + answer. */
function InteractionCard({
  it,
  now,
  defaultOpen,
}: {
  it: AgentInteraction;
  now: number;
  defaultOpen: boolean;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const meta = roleMeta(it.persona, it.phase, t);
  const tok = tokens(it);
  return (
    <div
      className={`llm-call${it.ok ? "" : " llm-call-error"}`}
      data-testid={`llm-call-${it.id}`}
    >
      <button
        type="button"
        className="llm-call-head"
        aria-expanded={open}
        data-testid={`llm-call-head-${it.id}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="llm-call-caret">{open ? "▾" : "▸"}</span>
        <span className="llm-call-role" title={meta.label}>
          {meta.icon} {meta.label}
        </span>
        {!it.ok && (
          <span className="llm-call-badge llm-call-badge-error">
            {t("llmActivity.badgeError")}
          </span>
        )}
        {tok && <span className="llm-call-tokens">{tok}</span>}
        {it.cost_usd > 0 && (
          <span className="llm-call-cost">${it.cost_usd.toFixed(4)}</span>
        )}
        {it.duration_ms > 0 && (
          <span className="llm-call-dur">{(it.duration_ms / 1000).toFixed(1)}s</span>
        )}
        <span className="llm-call-time">{timeAgo(it.ts, now, t)}</span>
      </button>
      {open && (
        <div className="llm-call-body">
          {!it.ok && it.error && (
            <div className="llm-call-section">
              <h6>{t("llmActivity.errorHeading")}</h6>
              <pre className="llm-pre llm-pre-error">{it.error}</pre>
            </div>
          )}
          <div className="llm-call-section">
            <h6>
              {t("llmActivity.promptHeading")}
              {it.prompt_truncated && (
                <span className="llm-trunc">{t("llmActivity.truncated")}</span>
              )}
            </h6>
            <pre className="llm-pre">{it.prompt || t("llmActivity.empty")}</pre>
          </div>
          {(it.response || it.ok) && (
            <div className="llm-call-section">
              <h6>
                {t("llmActivity.responseHeading")}
                {it.response_truncated && (
                  <span className="llm-trunc">{t("llmActivity.truncated")}</span>
                )}
              </h6>
              <pre className="llm-pre">{it.response || t("llmActivity.empty")}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * O2: integrated view of the latest LLM prompts/answers for one work item. Used
 * inside the Activity row drawer and the Board's story/task detail. Polls while
 * the item is live (a build in flight) so the operator watches calls land in real
 * time; fetches once otherwise (history). Never a popup — it renders inline.
 */
export function LlmActivity({
  projectId,
  itemId,
  live = false,
  limit = 20,
}: {
  projectId: string;
  itemId: string;
  live?: boolean;
  limit?: number;
}) {
  const { t } = useI18n();
  const [items, setItems] = useState<AgentInteraction[] | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      const data = await getItemInteractions(projectId, itemId, limit);
      setItems(data);
      setError("");
    } catch {
      // A 404 (no pipeline / no history yet) is not an error worth shouting about.
      setItems((cur) => cur ?? []);
    }
  }, [projectId, itemId, limit]);

  useEffect(() => {
    void load();
    if (!live) return;
    const id = setInterval(() => {
      setNow(Date.now());
      void load();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [load, live]);

  if (items === null) {
    return <div className="llm-activity llm-muted" data-testid={`llm-activity-${itemId}`}>{t("common.loading")}</div>;
  }

  // Newest first: the freshest call is what the operator wants to see. The newest
  // card auto-opens (its `defaultOpen` only applies on mount, so a new call landing
  // during live polling opens itself without disturbing cards already toggled).
  const ordered = [...items].reverse();
  const firstId = ordered[0]?.id;

  return (
    <div className="llm-activity" data-testid={`llm-activity-${itemId}`}>
      <div className="llm-activity-head">
        <span className="llm-activity-title">{t("llmActivity.title")}</span>
        {live && (
          <span className="llm-live" title={t("llmActivity.liveTitle")}>
            {t("llmActivity.live")}
          </span>
        )}
        <span className="llm-activity-count">{items.length}</span>
      </div>
      {error && <div className="edit-error">{error}</div>}
      {ordered.length === 0 ? (
        <p className="placeholder small">
          {live ? t("llmActivity.emptyLive") : t("llmActivity.emptyHistory")}
        </p>
      ) : (
        <div className="llm-call-list">
          {ordered.map((it) => (
            <InteractionCard
              key={it.id}
              it={it}
              now={now}
              defaultOpen={it.id === firstId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
