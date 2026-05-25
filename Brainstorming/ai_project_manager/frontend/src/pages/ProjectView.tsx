import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { listProjects } from '../api/projects';
import type { Project } from '../types/project';
import Chat from '../components/Chat/Chat';
import Tabs from '../components/Tabs';
import UserStoriesView from '../components/UserStoriesView';
import TasksView from '../components/TasksView';
import EpicsView from '../components/EpicsView';
import ItemDetail from '../components/ItemDetail/ItemDetail';
import ErrorBox from '../components/ErrorBox';
import RunPanel from '../components/RunPanel';

type ActiveTab = 'epics' | 'user_stories' | 'tasks';

const ACTIVE_TAB_STORAGE_KEY = 'projectview-active-tab';

function parseActiveTab(raw: string | null): ActiveTab {
  if (raw === 'epics' || raw === 'tasks' || raw === 'user_stories') {
    return raw;
  }
  return 'user_stories';
}

function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<boolean>(false);

  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    return parseActiveTab(sessionStorage.getItem(ACTIVE_TAB_STORAGE_KEY));
  });
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

  // Bumped by <Chat> whenever a scoping turn created or updated items,
  // and by <RunPanel> whenever a task transition happens during a run.
  // Both list views observe this version and refetch when it changes,
  // so the left panel stays in sync with what's happening on the right
  // without any shared store.
  const [itemsVersion, setItemsVersion] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;

    async function aload(): Promise<void> {
      if (!id) {
        setNotFound(true);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        // Workaround: no GET /projects/{id} endpoint yet, so we fetch the
        // full list and find the project by id. Fine for local MVP.
        const projects = await listProjects();
        if (cancelled) return;
        const found = projects.find((p) => p.id === id);
        if (!found) {
          setNotFound(true);
        } else {
          setProject(found);
        }
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : 'Erreur de chargement',
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void aload();
    return () => {
      cancelled = true;
    };
  }, [id]);

  function handleTabChange(tabId: string): void {
    const validTab = parseActiveTab(tabId);
    setActiveTab(validTab);
    sessionStorage.setItem(ACTIVE_TAB_STORAGE_KEY, validTab);
  }

  // Derived header title
  let headerTitle: string;
  if (loading) headerTitle = 'Chargement...';
  else if (notFound) headerTitle = 'Projet introuvable';
  else if (error) headerTitle = 'Erreur';
  else headerTitle = project?.name ?? '';

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {/* Header */}
      <header className="flex h-[60px] shrink-0 items-center gap-4 border-b border-gray-200 bg-white px-6">
        <Link
          to="/"
          className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
        >
          &larr; Retour
        </Link>
        <h1 className="text-lg font-semibold text-gray-900">{headerTitle}</h1>
      </header>

      {/* Body: zone centrale (gauche) + chat (droite) */}
      <div className="flex flex-1 overflow-hidden">
        {/* Zone centrale */}
        <main className="flex-1 overflow-auto p-6">
          {loading && (
            <p className="text-sm text-gray-500">Chargement du projet...</p>
          )}

          {!loading && error && <ErrorBox message={error} />}

          {!loading && notFound && (
            <div className="rounded border border-gray-200 bg-white p-6">
              <p className="text-sm text-gray-700">
                Ce projet n'existe pas ou a ete supprime.
              </p>
              <Link
                to="/"
                className="mt-3 inline-block text-sm text-blue-600 hover:underline"
              >
                Retour a l'accueil
              </Link>
            </div>
          )}

          {!loading && !error && !notFound && project && id && (
            <>
              {/* V1: global implementation run panel */}
              <div className="mb-6">
                <RunPanel
                  projectId={id}
                  onItemsChanged={() => setItemsVersion((v) => v + 1)}
                />
              </div>

              <Tabs
                tabs={[
                  { id: 'epics', label: 'Epics' },
                  { id: 'user_stories', label: 'User Stories' },
                  { id: 'tasks', label: 'Tasks' },
                ]}
                activeTab={activeTab}
                onChange={handleTabChange}
              />
              <div className="mt-4">
                {activeTab === 'epics' && (
                  <EpicsView
                    projectId={id}
                    onItemClick={(item) => setSelectedItemId(item.id)}
                    refreshVersion={itemsVersion}
                  />
                )}
                {activeTab === 'user_stories' && (
                  <UserStoriesView
                    projectId={id}
                    onItemClick={(item) => setSelectedItemId(item.id)}
                    refreshVersion={itemsVersion}
                  />
                )}
                {activeTab === 'tasks' && (
                  <TasksView
                    projectId={id}
                    onItemClick={(item) => setSelectedItemId(item.id)}
                    refreshVersion={itemsVersion}
                  />
                )}
              </div>
            </>
          )}
        </main>

        {/* Chat fixe a droite */}
        <aside className="w-[360px] shrink-0 border-l border-gray-200 bg-white">
          {!loading && !error && !notFound && project && id && (
            <Chat
              projectId={id}
              onItemsChanged={() => setItemsVersion((v) => v + 1)}
            />
          )}
        </aside>
      </div>

      {/* Item detail overlay (rendu au-dessus de tout, ferme -> null) */}
      <ItemDetail
        itemId={selectedItemId}
        projectId={id ?? null}
        onClose={() => setSelectedItemId(null)}
        onNavigate={(targetId) => setSelectedItemId(targetId)}
      />
    </div>
  );
}

export default ProjectView;
