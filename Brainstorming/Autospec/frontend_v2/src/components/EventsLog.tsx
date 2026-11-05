import { useEffect, useRef } from "react";
import type { ProjectEvent } from "../api";
import { formatTime } from "../format";
import { useEvents, type StreamMode } from "../useEvents";

const TYPE_LABELS: Record<string, string> = {
  phase: "Phase",
  story: "Story",
  plan: "Plan",
  plan_rejected: "Plan rejeté",
  scaffold: "Squelette",
  agent_start: "Agent lancé",
  agent_end: "Agent terminé",
  agent_error: "Erreur d'agent",
  acceptance_tests: "Tests d'acceptance",
  qa_rejected: "QA rejetée",
  already_green: "Déjà vert",
  suite: "Suite de tests",
  verify_failed: "Vérification échouée",
  smoke: "Smoke",
  end: "Fin",
  auto_resume: "Reprise automatique",
  unreadable: "Ligne illisible",
};

const BAD_TYPES = new Set(["agent_error", "plan_rejected", "qa_rejected", "verify_failed", "unreadable"]);

const MODE_LABELS: Record<StreamMode, string> = {
  connecting: "Connexion...",
  live: "En direct",
  polling: "Interrogation périodique",
  paused: "En pause (onglet masqué)",
  gone: "Projet introuvable",
};

export function eventTone(event: ProjectEvent): "good" | "bad" | "" {
  if (BAD_TYPES.has(event.type) || event.ok === false) return "bad";
  if (event.ok === true) return "good";
  return "";
}

function formatValue(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 300 ? `${text.slice(0, 300)}...` : text;
}

/** "key=value" pairs of everything but ts, type and the empty values (null, ""). */
export function eventSummary(event: ProjectEvent): string {
  return Object.entries(event)
    .filter(([key, value]) => key !== "ts" && key !== "type" && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}=${formatValue(value)}`)
    .join("  ");
}

export function EventsLog({
  projectId,
  pollMs,
  onEvents,
  onGone,
}: {
  projectId: string;
  pollMs?: number;
  onEvents?: (events: ProjectEvent[]) => void;
  onGone?: () => void;
}) {
  const { events, mode } = useEvents(projectId, { pollMs, onEvents, onGone });
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight; // follow the tail
  }, [events.length]);

  return (
    <section className="card" aria-labelledby="events-title">
      <div className="section-head">
        <h2 id="events-title">Journal</h2>
        <span className={`stream-mode mode-${mode}`} role="status">
          {MODE_LABELS[mode]}
        </span>
      </div>
      {events.length === 0 ? (
        <p className="empty">Aucun événement pour l'instant.</p>
      ) : (
        <div className="events" role="log" aria-label="Événements du projet" ref={listRef} tabIndex={0}>
          <ol>
            {events.map((event, index) => (
              <li key={index} className={eventTone(event)}>
                <time className="mono muted" dateTime={event.ts}>
                  {formatTime(event.ts)}
                </time>
                <span className="event-type">{TYPE_LABELS[event.type] ?? event.type}</span>
                <span className="event-data mono">{eventSummary(event)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
