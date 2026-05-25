import { useCallback, useEffect, useRef, useState } from 'react';
import { getCurrentProjectRun, startProjectRun } from '../api/project_run';
import type {
  ProjectRun,
  ProjectRunDetail,
  ProjectRunStep,
} from '../types/project_run';
import ErrorBox from './ErrorBox';

interface RunPanelProps {
  projectId: string;
  // Fires when a run state transition should make the items panels
  // refresh (e.g. a task just flipped to `done`). The parent bumps its
  // `itemsVersion` which re-runs the item list effects.
  onItemsChanged: () => void;
}

// Poll interval while a run is actively running. Kept short enough that
// the UI feels responsive on a local dev machine, but not so short that
// it hammers the backend.
const POLL_INTERVAL_MS = 1500;

function formatTime(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function roleLabel(role: ProjectRunStep['role']): string {
  if (role === 'orchestrator') return 'Orchestrator';
  if (role === 'dev') return 'Dev';
  if (role === 'qa') return 'QA';
  return role;
}

function stepClasses(step: ProjectRunStep): string {
  if (step.status === 'running') return 'bg-blue-50 border-blue-200';
  if (step.status === 'succeeded') return 'bg-green-50 border-green-200';
  if (step.status === 'failed') return 'bg-red-50 border-red-200';
  if (step.status === 'rejected') return 'bg-orange-50 border-orange-200';
  return 'bg-gray-50 border-gray-200';
}

function statusLabel(run: ProjectRun): string {
  if (run.status === 'running') return 'En cours';
  if (run.status === 'succeeded') return 'Termine';
  if (run.status === 'failed') return 'Echec';
  return 'En attente';
}

function statusBadgeClasses(run: ProjectRun): string {
  if (run.status === 'running') return 'bg-blue-600 text-white';
  if (run.status === 'succeeded') return 'bg-green-600 text-white';
  if (run.status === 'failed') return 'bg-red-700 text-white';
  return 'bg-gray-300 text-gray-800';
}

function RunPanel({ projectId, onItemsChanged }: RunPanelProps) {
  const [detail, setDetail] = useState<ProjectRunDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [starting, setStarting] = useState<boolean>(false);
  const [startError, setStartError] = useState<string | null>(null);

  // Counters observed on the previous poll so we can detect a task
  // transition and notify the parent only when something actually
  // changed (no useless refresh of the items panels).
  const prevCountsRef = useRef<{ done: number; blocked: number }>({
    done: 0,
    blocked: 0,
  });
  // Keep the latest `onItemsChanged` in a ref so the polling effect
  // does not have to list it in its dependency array (parents pass
  // inline arrow functions that would otherwise reinstall the timer).
  const onItemsChangedRef = useRef(onItemsChanged);
  onItemsChangedRef.current = onItemsChanged;

  // Initial fetch + background polling while a run is in flight.
  useEffect(() => {
    let cancelled = false;
    let timeoutId: number | null = null;

    async function afetchOnce(): Promise<void> {
      try {
        const data = await getCurrentProjectRun(projectId);
        if (cancelled) return;
        setDetail(data);
        setLoadError(null);

        // Detect a change in counters → the items panels must refresh.
        const prev = prevCountsRef.current;
        if (
          data.run.done_tasks !== prev.done ||
          data.run.blocked_tasks !== prev.blocked
        ) {
          prevCountsRef.current = {
            done: data.run.done_tasks,
            blocked: data.run.blocked_tasks,
          };
          onItemsChangedRef.current();
        }

        // Schedule the next poll only while the run is running.
        if (!cancelled && data.run.status === 'running') {
          timeoutId = window.setTimeout(
            () => void afetchOnce(),
            POLL_INTERVAL_MS,
          );
        }
      } catch (err) {
        if (cancelled) return;
        // A 404 is the nominal "no run yet" state — don't show it as
        // an error, just clear the detail and stop polling.
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes('No run found')) {
          setDetail(null);
          setLoadError(null);
        } else {
          setLoadError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void afetchOnce();
    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [projectId]);

  const ahandleStart = useCallback(async (): Promise<void> => {
    setStarting(true);
    setStartError(null);
    try {
      await startProjectRun(projectId);
      // Reset counters so the next poll can detect progress from 0.
      prevCountsRef.current = { done: 0, blocked: 0 };
      // Force an immediate refetch to pick up the new run.
      const fresh = await getCurrentProjectRun(projectId);
      setDetail(fresh);
      onItemsChangedRef.current();
    } catch (err) {
      setStartError(
        err instanceof Error ? err.message : "Impossible de lancer le run",
      );
    } finally {
      setStarting(false);
    }
  }, [projectId]);

  if (loading) {
    return (
      <div className="rounded border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Chargement du run...
      </div>
    );
  }

  if (loadError) {
    return <ErrorBox message={loadError} size="sm" />;
  }

  const run = detail?.run ?? null;
  const isRunning = run?.status === 'running';
  const canStart = !isRunning && !starting;

  return (
    <div className="rounded border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 border-b border-gray-100 px-4 py-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">
            Implementation du projet
          </h3>
          <p className="mt-1 text-xs text-gray-500">
            {run === null
              ? "Lance l'implementation pour que les agents generent le code des taches."
              : `Dernier run ${statusLabel(run)} — ${run.done_tasks}/${run.total_tasks} taches terminees${
                  run.blocked_tasks > 0 ? `, ${run.blocked_tasks} bloquee(s)` : ''
                }.`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void ahandleStart()}
          disabled={!canStart}
          className="shrink-0 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {starting
            ? 'Lancement...'
            : isRunning
              ? 'En cours...'
              : "Lancer l'implementation"}
        </button>
      </div>

      {startError && (
        <div className="px-4 pt-3">
          <ErrorBox message={startError} size="sm" />
        </div>
      )}

      {/* Progress + status */}
      {run && (
        <div className="px-4 py-3">
          <div className="flex items-center gap-3">
            <span
              className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusBadgeClasses(run)}`}
            >
              {statusLabel(run)}
            </span>
            <span className="text-xs text-gray-600">
              Demarre a {formatTime(run.started_at)}
              {run.finished_at && ` — termine a ${formatTime(run.finished_at)}`}
            </span>
          </div>
          {/* Progress bar */}
          <div className="mt-3 h-2 w-full overflow-hidden rounded bg-gray-100">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{
                width: `${
                  run.total_tasks > 0
                    ? Math.min(
                        100,
                        ((run.done_tasks + run.blocked_tasks) /
                          run.total_tasks) *
                          100,
                      )
                    : 0
                }%`,
              }}
            />
          </div>
          {run.error && (
            <p className="mt-2 text-xs text-red-700">
              Erreur: {run.error.split('\n')[0]}
            </p>
          )}
        </div>
      )}

      {/* Steps log */}
      {detail && detail.steps.length > 0 && (
        <div className="border-t border-gray-100 px-4 py-3">
          <h4 className="mb-2 text-xs font-semibold uppercase text-gray-500">
            Journal d'execution
          </h4>
          <ul className="max-h-60 space-y-1 overflow-y-auto text-xs">
            {detail.steps.map((step) => (
              <li
                key={step.id}
                className={`rounded border px-2 py-1 ${stepClasses(step)}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium text-gray-800">
                    [{roleLabel(step.role)}
                    {step.iteration > 0 ? ` #${step.iteration}` : ''}]{' '}
                    {step.summary}
                  </span>
                  <span className="shrink-0 text-[10px] text-gray-500">
                    {formatTime(step.started_at ?? step.created_at)}
                  </span>
                </div>
                {step.detail && (
                  <p className="mt-1 whitespace-pre-wrap text-[11px] text-gray-600">
                    {step.detail}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default RunPanel;
