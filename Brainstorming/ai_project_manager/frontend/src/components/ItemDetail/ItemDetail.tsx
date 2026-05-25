import { useEffect, useMemo, useRef, useState } from 'react';
import { getItem, listProjectItems } from '../../api/items';
import type { Item, ItemType } from '../../types/chat';
import StatusBadge from '../StatusBadge';
import ErrorBox from '../ErrorBox';

interface ItemDetailProps {
  itemId: string | null;
  // Needed so the panel can resolve parent + children items (titles, not
  // just the raw parent_id UUID) and render navigation links between
  // Epic / User Story / Task.
  projectId: string | null;
  onClose: () => void;
  // Called when the user clicks a parent or child link inside the panel
  // so the parent component (ProjectView) can swap `selectedItemId`
  // without closing/reopening the dialog.
  onNavigate?: (itemId: string) => void;
}

const TYPE_LABELS: Record<ItemType, string> = {
  epic: 'Epic',
  user_story: 'User Story',
  task: 'Task',
};

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function ItemDetail({ itemId, projectId, onClose, onNavigate }: ItemDetailProps) {
  const [item, setItem] = useState<Item | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  // Bumping this triggers the load effect to re-fetch (retry button).
  const [reloadKey, setReloadKey] = useState<number>(0);

  // All items of the current project, used to resolve parent + children
  // navigation links. Loaded once per open + reloaded on retry. This
  // avoids adding a dedicated /items/{id}/children endpoint on the
  // backend for the V0.
  const [projectItems, setProjectItems] = useState<Item[]>([]);

  // Keep the latest `onClose` in a ref so the Escape-key effect does NOT
  // have to list it in its dependencies. Parents typically pass an inline
  // arrow function (`onClose={() => setSelectedItemId(null)}`), which
  // creates a new reference on every render — without this ref, the
  // keydown listener would be reinstalled on every parent re-render and
  // slowly leak handlers.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Load item details with a cancelled flag to avoid stale responses
  // overwriting a newer itemId. We also fetch the full project item
  // list (parallel request) so parent + children links can be rendered
  // with real titles instead of raw UUIDs.
  useEffect(() => {
    if (itemId === null) {
      setItem(null);
      setProjectItems([]);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function aload(id: string): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const [data, siblings] = await Promise.all([
          getItem(id),
          projectId ? listProjectItems(projectId) : Promise.resolve([]),
        ]);
        if (cancelled) return;
        setItem(data);
        setProjectItems(siblings);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void aload(itemId);

    return () => {
      cancelled = true;
    };
  }, [itemId, projectId, reloadKey]);

  // Derived: parent (if any) and direct children of the currently
  // displayed item, resolved against the full project tree.
  const parent = useMemo<Item | null>(() => {
    if (!item || !item.parent_id) return null;
    return projectItems.find((it) => it.id === item.parent_id) ?? null;
  }, [item, projectItems]);

  const children = useMemo<Item[]>(() => {
    if (!item) return [];
    return projectItems.filter((it) => it.parent_id === item.id);
  }, [item, projectItems]);

  // Refs used by the focus trap: the panel itself, and the "Fermer"
  // button which gets the initial focus when the dialog opens.
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  // Escape key -> close. The effect only depends on `itemId` because
  // `onCloseRef` is mutable and always carries the latest callback.
  useEffect(() => {
    if (itemId === null) return;
    function handleKey(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        onCloseRef.current();
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
    };
  }, [itemId]);

  // Focus management: when the dialog opens, remember the element that
  // held focus, move focus to the close button, and restore focus on
  // close. Keyboard Tab / Shift+Tab is trapped inside the panel so
  // screen-reader users cannot wander onto the background content.
  useEffect(() => {
    if (itemId === null) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    // Delay one tick so the panel is actually mounted before we focus.
    const focusTimer = window.setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 0);

    function handleTab(event: KeyboardEvent): void {
      if (event.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;

      const focusable = panel.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (event.shiftKey) {
        if (active === first || !panel.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      } else if (!panel.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    }

    window.addEventListener('keydown', handleTab);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener('keydown', handleTab);
      // Restore focus to whatever the user was on before the dialog
      // opened, as long as that element still exists in the DOM.
      if (previouslyFocused && document.body.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [itemId]);

  if (itemId === null) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="flex-1 bg-black bg-opacity-30"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="item-detail-title"
        className="flex h-full w-[480px] flex-col overflow-y-auto bg-white shadow-xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <h2
            id="item-detail-title"
            className="pr-4 text-lg font-semibold text-gray-900"
          >
            Detail de l'item
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-700 hover:bg-gray-50"
          >
            Fermer
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 px-6 py-4">
          {loading && (
            <p className="text-sm text-gray-500">Chargement...</p>
          )}

          {!loading && error && (
            <ErrorBox
              message={error}
              onRetry={() => setReloadKey((k) => k + 1)}
            />
          )}

          {!loading && !error && item && (
            <div className="space-y-5">
              {/* Title */}
              <h3 className="text-xl font-bold text-gray-900">{item.title}</h3>

              {/* Type + Status badges */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs font-medium uppercase italic text-gray-700">
                  {TYPE_LABELS[item.type]}
                </span>
                <StatusBadge status={item.status} />
              </div>

              {/* Description */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                  Description
                </h4>
                {item.description ? (
                  <p className="whitespace-pre-wrap text-sm text-gray-800">
                    {item.description}
                  </p>
                ) : (
                  <p className="text-sm italic text-gray-400">
                    Aucune description
                  </p>
                )}
              </div>

              {/* Acceptance criteria */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                  Criteres d'acceptance
                </h4>
                {item.acceptance_criteria &&
                item.acceptance_criteria.length > 0 ? (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-gray-800">
                    {item.acceptance_criteria.map((c, idx) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm italic text-gray-400">
                    Aucun critere defini
                  </p>
                )}
              </div>

              {/* Related items: parent link + children list */}
              {(parent || children.length > 0) && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                    Navigation
                  </h4>

                  {parent && (
                    <div className="mb-3">
                      <p className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">
                        {parent.type === 'epic' ? 'Epic parente' : 'User Story parente'}
                      </p>
                      <button
                        type="button"
                        onClick={() => onNavigate?.(parent.id)}
                        disabled={!onNavigate}
                        className="flex w-full items-center justify-between gap-2 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-left text-sm hover:bg-gray-100 disabled:cursor-default disabled:hover:bg-gray-50"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="inline-block rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-gray-700">
                            {TYPE_LABELS[parent.type]}
                          </span>
                          <span className="truncate text-gray-900">
                            {parent.title}
                          </span>
                        </span>
                        <span className="text-xs text-blue-600">&rarr;</span>
                      </button>
                    </div>
                  )}

                  {children.length > 0 && (
                    <div>
                      <p className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">
                        {item.type === 'epic'
                          ? `User Stories (${children.length})`
                          : `Taches (${children.length})`}
                      </p>
                      <ul className="divide-y divide-gray-100 rounded border border-gray-200 bg-gray-50">
                        {children.map((child) => (
                          <li key={child.id}>
                            <button
                              type="button"
                              onClick={() => onNavigate?.(child.id)}
                              disabled={!onNavigate}
                              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-gray-100 disabled:cursor-default disabled:hover:bg-gray-50"
                            >
                              <span className="flex min-w-0 items-center gap-2">
                                <span className="inline-block rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-gray-700">
                                  {TYPE_LABELS[child.type]}
                                </span>
                                <span className="truncate text-gray-900">
                                  {child.title}
                                </span>
                              </span>
                              <StatusBadge status={child.status} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* V1: Deliverable produced by the DevAgent (+ QA notes) */}
              {(item.deliverable_paths && item.deliverable_paths.length > 0) ||
              item.deliverable_notes ||
              item.blocked_reason ? (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                    Livrable
                  </h4>

                  {item.blocked_reason && (
                    <div className="mb-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                      <p className="font-semibold">Tache bloquee</p>
                      <p className="mt-1 whitespace-pre-wrap text-xs">
                        {item.blocked_reason}
                      </p>
                    </div>
                  )}

                  {item.deliverable_paths &&
                    item.deliverable_paths.length > 0 && (
                      <div className="mb-3">
                        <p className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">
                          Fichiers generes ({item.deliverable_paths.length})
                        </p>
                        <ul className="divide-y divide-gray-100 rounded border border-gray-200 bg-gray-50 font-mono text-xs">
                          {item.deliverable_paths.map((path) => (
                            <li
                              key={path}
                              className="px-3 py-2 text-gray-800"
                            >
                              {path}
                            </li>
                          ))}
                        </ul>
                        <p className="mt-1 text-[10px] text-gray-500">
                          Relatifs au workspace
                          {` backend/generated/<project>/<item>/`}
                        </p>
                      </div>
                    )}

                  {item.deliverable_notes && (
                    <div>
                      <p className="mb-1 text-[11px] uppercase tracking-wide text-gray-400">
                        Notes dev / QA
                      </p>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800">
                        {item.deliverable_notes}
                      </pre>
                    </div>
                  )}
                </div>
              ) : null}

              {/* Meta */}
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase text-gray-500">
                  Meta
                </h4>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  <dt className="text-gray-500">Complexite</dt>
                  <dd className="text-gray-800">
                    {item.complexity ?? (
                      <span className="text-gray-400">&mdash;</span>
                    )}
                  </dd>
                  <dt className="text-gray-500">Cree le</dt>
                  <dd className="text-gray-800">
                    {formatDate(item.created_at)}
                  </dd>
                  {item.updated_at && (
                    <>
                      <dt className="text-gray-500">Mis a jour</dt>
                      <dd className="text-gray-800">
                        {formatDate(item.updated_at)}
                      </dd>
                    </>
                  )}
                </dl>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ItemDetail;
