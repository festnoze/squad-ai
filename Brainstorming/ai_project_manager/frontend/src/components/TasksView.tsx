import { useCallback, useEffect, useState } from 'react';
import { listProjectItems } from '../api/items';
import type { Item } from '../types/chat';
import ItemTable from './ItemTable/ItemTable';
import ErrorBox from './ErrorBox';
import { useItemsPolling } from '../hooks/useItemsPolling';

interface TasksViewProps {
  projectId: string;
  onItemClick: (item: Item) => void;
  // Bumped by the parent whenever an external action (e.g. the chat
  // creating items, or a new run starting) requires this view to
  // refetch. Any change to the value triggers the load effect.
  refreshVersion?: number;
}

function TasksView({
  projectId,
  onItemClick,
  refreshVersion = 0,
}: TasksViewProps) {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // Bumping this forces the load effect to re-run (Retry button).
  const [reloadKey, setReloadKey] = useState<number>(0);

  // Initial load + reload on projectId change, retry, or external refresh.
  useEffect(() => {
    let cancelled = false;

    async function aload(): Promise<void> {
      setLoading(true);
      setError(null);
      try {
        const data = await listProjectItems(projectId, 'task');
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

  // V1: polling is useful whenever the items can change under us —
  // a live run will flip their statuses. Cheap heuristic: poll if any
  // item is currently in_progress or in_test. When everything is
  // settled, polling pauses on its own.
  const hasActiveItems = items.some(
    (item) => item.status === 'in_progress' || item.status === 'in_test',
  );

  const handlePolledItems = useCallback((fresh: Item[]) => {
    setItems(fresh);
  }, []);

  useItemsPolling({
    projectId,
    typeFilter: 'task',
    enabled: hasActiveItems,
    onItems: handlePolledItems,
  });

  if (loading) {
    return <p className="text-sm text-gray-500">Chargement des taches...</p>;
  }

  if (error) {
    return (
      <ErrorBox
        message={error}
        onRetry={() => setReloadKey((k) => k + 1)}
      />
    );
  }

  return (
    <ItemTable
      items={items}
      onRowClick={onItemClick}
      emptyMessage="Aucune tache pour ce projet"
    />
  );
}

export default TasksView;
