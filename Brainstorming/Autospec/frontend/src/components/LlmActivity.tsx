import { useCallback, useEffect, useState } from "react";
import { getItemInteractions } from "../api";
import { AgentInteraction } from "../types";

/** Agent role → icon + human label. Covers the build crew and the planning
 *  personas, so a call captured under "phase:spec" (pm) reads as nicely as a
 *  dev/qa/critic call captured under a story. */
const ROLE_META: Record<string, { icon: string; label: string }> = {
  dev: { icon: "👨‍💻", label: "Dev" },
  "dev-frontend": { icon: "🎨", label: "Dev front" },
  qa: { icon: "🧪", label: "QA" },
  critic: { icon: "🔍", label: "Critique" },
  judge: { icon: "⚖️", label: "Juge" },
  architect: { icon: "🏛️", label: "Architecte" },
  analyst: { icon: "📊", label: "Analyste" },
  pm: { icon: "📋", label: "PM" },
  sm: { icon: "🗂", label: "PO/SM" },
  "tech-writer": { icon: "📝", label: "Rédacteur" },
  evaluator: { icon: "🕵️", label: "Évaluateur" },
  "security-reviewer": { icon: "🛡️", label: "Sécurité" },
  retro: { icon: "🔄", label: "Rétro" },
};

/** Poll cadence while the item is live (a build in flight). */
const POLL_MS = 3000;

function roleMeta(persona: string, phase: string) {
  return (
    ROLE_META[persona] ?? {
      icon: "🤖",
      label: persona || (phase ? phase.replace(/^phase:/, "") : "agent"),
    }
  );
}

/** Short "time ago" for a unix-seconds timestamp. */
function timeAgo(ts: number, now: number): string {
  const s = Math.max(0, Math.round(now / 1000 - ts));
  if (s < 60) return `il y a ${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  return `il y a ${h} h`;
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
  const [open, setOpen] = useState(defaultOpen);
  const meta = roleMeta(it.persona, it.phase);
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
        {!it.ok && <span className="llm-call-badge llm-call-badge-error">échec</span>}
        {tok && <span className="llm-call-tokens">{tok}</span>}
        {it.cost_usd > 0 && (
          <span className="llm-call-cost">${it.cost_usd.toFixed(4)}</span>
        )}
        {it.duration_ms > 0 && (
          <span className="llm-call-dur">{(it.duration_ms / 1000).toFixed(1)}s</span>
        )}
        <span className="llm-call-time">{timeAgo(it.ts, now)}</span>
      </button>
      {open && (
        <div className="llm-call-body">
          {!it.ok && it.error && (
            <div className="llm-call-section">
              <h6>Erreur</h6>
              <pre className="llm-pre llm-pre-error">{it.error}</pre>
            </div>
          )}
          <div className="llm-call-section">
            <h6>
              Prompt{it.prompt_truncated && <span className="llm-trunc"> (tronqué)</span>}
            </h6>
            <pre className="llm-pre">{it.prompt || "(vide)"}</pre>
          </div>
          {(it.response || it.ok) && (
            <div className="llm-call-section">
              <h6>
                Réponse
                {it.response_truncated && <span className="llm-trunc"> (tronqué)</span>}
              </h6>
              <pre className="llm-pre">{it.response || "(vide)"}</pre>
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
    return <div className="llm-activity llm-muted" data-testid={`llm-activity-${itemId}`}>Chargement…</div>;
  }

  // Newest first: the freshest call is what the operator wants to see. The newest
  // card auto-opens (its `defaultOpen` only applies on mount, so a new call landing
  // during live polling opens itself without disturbing cards already toggled).
  const ordered = [...items].reverse();
  const firstId = ordered[0]?.id;

  return (
    <div className="llm-activity" data-testid={`llm-activity-${itemId}`}>
      <div className="llm-activity-head">
        <span className="llm-activity-title">🧠 Appels LLM</span>
        {live && <span className="llm-live" title="Mise à jour en direct">● live</span>}
        <span className="llm-activity-count">{items.length}</span>
      </div>
      {error && <div className="edit-error">{error}</div>}
      {ordered.length === 0 ? (
        <p className="placeholder small">
          {live
            ? "Aucun appel pour l'instant — ils apparaîtront ici dès que l'agent travaille sur cet item."
            : "Aucun appel LLM enregistré pour cet item."}
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
