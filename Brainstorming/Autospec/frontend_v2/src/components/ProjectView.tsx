import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError, deleteProject, getProject, resumeProject, stopProject, type ProjectDetail } from "../api";
import { formatCost, formatCountdown, formatDateTime, PROFILE_LABELS } from "../format";
import { EventsLog } from "./EventsLog";
import { FileBrowser } from "./FileBrowser";
import { PhaseBadge } from "./PhaseBadge";
import { StoriesTable } from "./StoriesTable";
import { StoryDiff } from "./StoryDiff";

type Action = "resume" | "stop" | "delete";

const message = (exc: unknown) => (exc instanceof Error ? exc.message : String(exc));

export const PROJECT_REFRESH_MS = 5000;

export function ProjectView({
  projectId,
  onDeleted,
  pollMs,
  refreshDelayMs = 400,
  refreshMs = PROJECT_REFRESH_MS,
}: {
  projectId: string;
  onDeleted: () => void;
  pollMs?: number;
  /** New events trigger one coalesced reload of the state after this delay. */
  refreshDelayMs?: number;
  /** Periodic reload while a run is active or parked: `running` flips after the last event. */
  refreshMs?: number;
}) {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState<Action | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  /** While true the events log is unmounted and no reload runs: nothing reads the workspace. */
  const [deleting, setDeleting] = useState(false);
  const [diffStory, setDiffStory] = useState<string | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setProject(await getProject(projectId));
      setLoadError("");
      setNotFound(false);
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 404) setNotFound(true);
      else setLoadError(message(exc));
    }
  }, [projectId]);

  useEffect(() => {
    setProject(null);
    setDiffStory(null);
    setConfirmingDelete(false);
    void load();
  }, [load]);

  const onEvents = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = undefined;
      void load();
    }, refreshDelayMs);
  }, [load, refreshDelayMs]);

  const cancelRefresh = () => {
    clearTimeout(refreshTimer.current);
    refreshTimer.current = undefined;
  };
  useEffect(() => cancelRefresh, []);

  // The journal stream ended and polling got a 404: reload to show "Projet introuvable".
  const onGone = useCallback(() => void load(), [load]);

  const active = (Boolean(project?.running) || typeof project?.resume_at === "number") && !deleting;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), refreshMs);
    return () => clearInterval(timer);
  }, [active, load, refreshMs]);

  async function act(action: Action) {
    setPending(action);
    setActionError("");
    try {
      if (action === "delete") {
        // Close the event stream and stop the reloads before the request: on Windows the
        // server cannot delete a journal that one of them is reading at that moment.
        cancelRefresh();
        flushSync(() => setDeleting(true));
        await deleteProject(projectId);
        onDeleted();
        return;
      }
      await (action === "stop" ? stopProject : resumeProject)(projectId);
      await load();
    } catch (exc) {
      setActionError(message(exc));
      setDeleting(false);
    } finally {
      setPending(null);
      setConfirmingDelete(false);
    }
  }

  if (notFound) {
    return (
      <section className="card">
        <h1>Projet introuvable</h1>
        <p>
          Le projet <span className="mono">{projectId}</span> n'existe pas ou a été supprimé.
        </p>
        <a href="#/">Retour aux projets</a>
      </section>
    );
  }
  if (!project) {
    return loadError ? (
      <p className="alert" role="alert">
        Impossible de charger le projet : {loadError}
      </p>
    ) : (
      <p className="muted">Chargement du projet...</p>
    );
  }

  const done = project.stories.filter((story) => story.status === "done").length;
  const busy = pending !== null;
  const resumeAt = typeof project.resume_at === "number" ? project.resume_at : null;

  return (
    <>
      <nav aria-label="Fil d'Ariane" className="crumbs">
        <a href="#/">← Projets</a>
      </nav>

      <section className="card project-head" aria-labelledby="project-title">
        <div className="section-head">
          <h1 id="project-title">{project.name}</h1>
          <PhaseBadge phase={project.phase} running={project.running} />
        </div>

        <dl className="facts">
          <div>
            <dt>Profil</dt>
            <dd>{project.profile ? PROFILE_LABELS[project.profile] : "choisi par le PO"}</dd>
          </div>
          <div>
            <dt>Paquet</dt>
            <dd className="mono">{project.package}</dd>
          </div>
          <div>
            <dt>Coût</dt>
            <dd>{formatCost(project.usage.cost_usd)}</dd>
          </div>
          {project.model && (
            <div>
              <dt>Modèle</dt>
              <dd className="mono">{project.model}</dd>
            </div>
          )}
          <div>
            <dt>Appels d'agent</dt>
            <dd>{project.usage.calls}</dd>
          </div>
          <div>
            <dt>Stories terminées</dt>
            <dd>
              {done}/{project.stories.length}
            </dd>
          </div>
          <div>
            <dt>Mis à jour</dt>
            <dd>{formatDateTime(project.updated_at)}</dd>
          </div>
        </dl>

        {resumeAt !== null && (
          <p className="banner" role="status">
            Reprise automatique prévue le {formatDateTime(resumeAt * 1000)} ({formatCountdown(resumeAt)}).
          </p>
        )}
        {project.error && (
          <div className="alert" role="alert">
            <strong>Erreur</strong>
            <pre>{project.error}</pre>
          </div>
        )}
        {loadError && (
          <p className="alert" role="alert">
            État non actualisé : {loadError}
          </p>
        )}

        <div className="actions" role="group" aria-label="Actions du projet">
          <button
            type="button"
            className="primary"
            onClick={() => void act("resume")}
            disabled={busy || project.running || project.phase === "done"}
          >
            {pending === "resume" ? "Reprise..." : "Reprendre"}
          </button>
          {/* Stopping a parked project cancels its automatic resume. */}
          <button
            type="button"
            onClick={() => void act("stop")}
            disabled={busy || (!project.running && resumeAt === null)}
          >
            {pending === "stop" ? "Arrêt..." : "Arrêter"}
          </button>
          {confirmingDelete ? (
            <span className="confirm" role="group" aria-label="Confirmation de suppression">
              <span>Supprimer définitivement « {project.name} » ?</span>
              <button type="button" className="danger" onClick={() => void act("delete")} disabled={busy}>
                Confirmer la suppression
              </button>
              <button type="button" onClick={() => setConfirmingDelete(false)} disabled={busy}>
                Annuler
              </button>
            </span>
          ) : (
            <button
              type="button"
              className="danger"
              onClick={() => setConfirmingDelete(true)}
              disabled={busy || project.running}
            >
              Supprimer
            </button>
          )}
        </div>
        {actionError && (
          <p className="alert" role="alert">
            {actionError}
          </p>
        )}

        {(project.brief || project.goal) && (
          <details className="brief">
            <summary>{project.brief ? "Brief" : "Objectif"}</summary>
            <pre>{project.brief || project.goal}</pre>
          </details>
        )}
      </section>

      <div className="detail-grid">
        <div className="detail-main">
          <section className="card" aria-labelledby="stories-title">
            <h2 id="stories-title">Stories</h2>
            <StoriesTable
              stories={project.stories}
              selectedDiff={diffStory}
              onShowDiff={(id) => setDiffStory((current) => (current === id ? null : id))}
            />
          </section>
          {diffStory && <StoryDiff projectId={projectId} storyId={diffStory} onClose={() => setDiffStory(null)} />}
        </div>
        <div className="detail-side">
          {!deleting && <EventsLog projectId={projectId} pollMs={pollMs} onEvents={onEvents} onGone={onGone} />}
        </div>
      </div>

      <FileBrowser projectId={projectId} refreshKey={`${project.phase}:${done}`} />
    </>
  );
}
