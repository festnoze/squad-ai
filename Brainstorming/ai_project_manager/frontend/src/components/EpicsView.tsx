import { useCallback, useEffect, useMemo, useState } from 'react';
import { listProjectItems } from '../api/items';
import type { Item } from '../types/chat';
import StatusBadge from './StatusBadge';
import ErrorBox from './ErrorBox';
import { useItemsPolling } from '../hooks/useItemsPolling';

interface EpicsViewProps {
  projectId: string;
  onItemClick: (item: Item) => void;
  // Bumped by the parent whenever an external action (e.g. the chat
  // creating items) requires this view to refetch.
  refreshVersion?: number;
}

// Epics view: renders every Epic of the project as a card with its
// child User Stories listed inline, each clickable to open the shared
// ItemDetail panel. Unlike the flat UserStories/Tasks tabs, this view
// needs the full project tree to group US under their parent epic, so
// it loads items without a type filter.
function EpicsView({ projectId, onItemClick, refreshVersion = 0 }: EpicsViewProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);

  // Initial load + reload on projectId change, retry or external refresh.
  useEffect(() => {
    let cancelled = false;

    async function aload(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const data = await listProjectItems(projectId);
        if (cancelled) return;
        setItems(data);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Erreur de chargement');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void aload();
    return () => {
      cancelled = true;
    };
  }, [projectId, reloadKey, refreshVersion]);

  // Keep status badges fresh while something is executing in the background.
  const hasActiveItems = items.some(
    (item) => item.status === 'in_progress' || item.status === 'in_test',
  );
  const handlePolledItems = useCallback((fresh: Item[]) => {
    setItems(fresh);
  }, []);
  useItemsPolling({
    projectId,
    typeFilter: undefined,
    enabled: hasActiveItems,
    onItems: handlePolledItems,
  });

  // Group children (US) under their parent epic id. Derived, so it
  // recomputes automatically whenever `items` changes.
  const { epics, userStoriesByEpic } = useMemo(() => {
    const epicList = items.filter((it) => it.type === 'epic');
    const usByEpic = new Map<string, Item[]>();
    for (const it of items) {
      if (it.type === 'user_story' && it.parent_id) {
        const arr = usByEpic.get(it.parent_id) ?? [];
        arr.push(it);
        usByEpic.set(it.parent_id, arr);
      }
    }
    return { epics: epicList, userStoriesByEpic: usByEpic };
  }, [items]);

  if (loading) {
    return <p className="text-sm text-gray-500">Chargement des epics...</p>;
  }

  if (error) {
    return (
      <ErrorBox
        message={error}
        onRetry={() => setReloadKey((k) => k + 1)}
      />
    );
  }

  if (epics.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
        Aucune Epic pour ce projet
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {epics.map((epic) => {
        const children = userStoriesByEpic.get(epic.id) ?? [];
        return (
          <div
            key={epic.id}
            className="overflow-hidden rounded border border-gray-200 bg-white shadow-sm"
          >
            {/* Epic header: clickable to open the detail panel */}
            <button
              type="button"
              onClick={() => onItemClick(epic)}
              className="flex w-full items-start justify-between gap-4 border-b border-gray-100 px-4 py-3 text-left hover:bg-gray-50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="inline-block rounded bg-purple-100 px-2 py-0.5 text-xs font-medium uppercase text-purple-800">
                    Epic
                  </span>
                  <h3 className="truncate text-sm font-semibold text-gray-900">
                    {epic.title}
                  </h3>
                </div>
                {epic.description && (
                  <p className="mt-1 line-clamp-2 text-xs text-gray-600">
                    {epic.description}
                  </p>
                )}
              </div>
              <StatusBadge status={epic.status} />
            </button>

            {/* Children User Stories */}
            <div className="px-4 py-2">
              {children.length === 0 ? (
                <p className="py-2 text-xs italic text-gray-400">
                  Aucune User Story rattachee a cette Epic
                </p>
              ) : (
                <ul className="divide-y divide-gray-100">
                  {children.map((us) => (
                    <li key={us.id}>
                      <button
                        type="button"
                        onClick={() => onItemClick(us)}
                        className="flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-gray-50"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="inline-block rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-blue-800">
                            US
                          </span>
                          <span className="truncate text-sm text-gray-800">
                            {us.title}
                          </span>
                        </span>
                        <StatusBadge status={us.status} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default EpicsView;
