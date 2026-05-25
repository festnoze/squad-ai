import { useEffect, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import {
  listProjects,
  createProject,
  updateProject,
  deleteProject,
} from '../api/projects';
import type { Project } from '../types/project';
import ErrorBox from '../components/ErrorBox';

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

function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [newProjectName, setNewProjectName] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Inline rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const [renameError, setRenameError] = useState<string | null>(null);

  async function aloadProjects(): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void aloadProjects();
  }, []);

  async function ahandleCreate(): Promise<void> {
    const name = newProjectName.trim();
    if (!name) {
      setCreateError('Le nom est obligatoire');
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createProject({ name });
      setProjects((prev) => [...prev, created]);
      setNewProjectName('');
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : 'Erreur lors de la creation',
      );
    } finally {
      setCreating(false);
    }
  }

  function startRename(project: Project): void {
    setRenamingId(project.id);
    setRenameValue(project.name);
    setRenameError(null);
  }

  function cancelRename(): void {
    setRenamingId(null);
    setRenameValue('');
    setRenameError(null);
  }

  async function acommitRename(id: string): Promise<void> {
    const name = renameValue.trim();
    if (!name) {
      setRenameError('Le nom est obligatoire');
      return;
    }
    // If unchanged, just close the editor
    const current = projects.find((p) => p.id === id);
    if (current && current.name === name) {
      cancelRename();
      return;
    }
    try {
      const updated = await updateProject(id, { name });
      setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)));
      cancelRename();
    } catch (err) {
      setRenameError(
        err instanceof Error ? err.message : 'Erreur lors du renommage',
      );
    }
  }

  function handleRenameKeyDown(
    event: KeyboardEvent<HTMLInputElement>,
    id: string,
  ): void {
    if (event.key === 'Enter') {
      event.preventDefault();
      void acommitRename(id);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      cancelRename();
    }
  }

  async function ahandleDelete(project: Project): Promise<void> {
    const ok = window.confirm(`Supprimer le projet "${project.name}" ?`);
    if (!ok) return;
    try {
      await deleteProject(project.id);
      setProjects((prev) => prev.filter((p) => p.id !== project.id));
    } catch (err) {
      alert(
        err instanceof Error ? err.message : 'Erreur lors de la suppression',
      );
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-3xl font-bold text-gray-900">AI Project Manager</h1>

        {/* Creation form */}
        <section className="mt-8 rounded border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-800">
            Nouveau projet
          </h2>
          <div className="mt-3 flex items-start gap-3">
            <label htmlFor="new-project-name" className="sr-only">
              Nom du nouveau projet
            </label>
            <input
              id="new-project-name"
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void ahandleCreate();
                }
              }}
              placeholder="Nom du projet"
              disabled={creating}
              className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
            />
            <button
              type="button"
              onClick={() => void ahandleCreate()}
              disabled={creating || newProjectName.trim() === ''}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creating ? 'Creation...' : 'Creer'}
            </button>
          </div>
          {createError && (
            <p className="mt-2 text-sm text-red-600">{createError}</p>
          )}
        </section>

        {/* Project list */}
        <section className="mt-8">
          <h2 className="text-lg font-semibold text-gray-800">
            Liste des projets
          </h2>

          {loading && (
            <div className="mt-4 rounded border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
              Chargement...
            </div>
          )}

          {!loading && error && (
            <div className="mt-4">
              <ErrorBox
                message={error}
                onRetry={() => void aloadProjects()}
              />
            </div>
          )}

          {!loading && !error && projects.length === 0 && (
            <div className="mt-4 rounded border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
              Aucun projet - creez votre premier projet ci-dessus
            </div>
          )}

          {!loading && !error && projects.length > 0 && (
            <div className="mt-4 overflow-hidden rounded border border-gray-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-gray-100 text-xs uppercase text-gray-600">
                  <tr>
                    <th className="px-4 py-3">Nom</th>
                    <th className="px-4 py-3">Mis a jour</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project) => {
                    const isRenaming = renamingId === project.id;
                    return (
                      <tr
                        key={project.id}
                        className="border-t border-gray-100"
                      >
                        <td className="px-4 py-3">
                          {isRenaming ? (
                            <div>
                              <label
                                htmlFor={`rename-${project.id}`}
                                className="sr-only"
                              >
                                Nouveau nom du projet {project.name}
                              </label>
                              <input
                                id={`rename-${project.id}`}
                                type="text"
                                autoFocus
                                value={renameValue}
                                onChange={(e) =>
                                  setRenameValue(e.target.value)
                                }
                                onKeyDown={(e) =>
                                  handleRenameKeyDown(e, project.id)
                                }
                                onBlur={() => void acommitRename(project.id)}
                                className="w-full rounded border border-blue-400 px-2 py-1 text-sm focus:outline-none"
                              />
                              {renameError && (
                                <p className="mt-1 text-xs text-red-600">
                                  {renameError}
                                </p>
                              )}
                            </div>
                          ) : (
                            <Link
                              to={`/projects/${project.id}`}
                              className="font-medium text-blue-600 hover:underline"
                            >
                              {project.name}
                            </Link>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gray-600">
                          {formatDate(project.updated_at ?? project.created_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => startRename(project)}
                            disabled={isRenaming}
                            className="mr-2 rounded border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                          >
                            Renommer
                          </button>
                          <button
                            type="button"
                            onClick={() => void ahandleDelete(project)}
                            className="rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Supprimer
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default ProjectList;
