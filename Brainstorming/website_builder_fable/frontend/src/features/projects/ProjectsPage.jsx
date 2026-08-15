// OWNED BY: frontend-projects agent (src/features/projects/**).
// Projects dashboard: grid of project cards with open editor / open CMS /
// preview / settings / delete actions, plus create and edit-settings modals.

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiGet, apiDelete } from '../../api/client.js'
import ProjectForm from './ProjectForm.jsx'
import './projects.css'

function errorText(err) {
  if (!err) return 'Unknown error'
  if (typeof err.detail === 'string') return err.detail
  return err.message || 'Request failed'
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Returns the home page (or first page) of a project, or null when it has none.
async function afindHomePage(projectId) {
  const pages = await apiGet(`/api/projects/${projectId}/pages`)
  if (!Array.isArray(pages) || pages.length === 0) return null
  return pages.find((p) => p.is_home) || pages[0]
}

function ProjectCard({ project, onEdit, onDeleted, onError }) {
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleOpenEditor() {
    setBusy(true)
    try {
      const home = await afindHomePage(project.id)
      navigate(home ? `/projects/${project.id}/editor/${home.id}` : `/projects/${project.id}/editor`)
    } catch (err) {
      onError(`Could not open the editor for "${project.name}": ${errorText(err)}`)
      setBusy(false)
    }
  }

  async function handlePreview() {
    setBusy(true)
    try {
      const home = await afindHomePage(project.id)
      if (!home) {
        onError(`"${project.name}" has no page to preview yet. Open the editor to create one.`)
      } else {
        window.open(`/api/projects/${project.id}/pages/${home.id}/preview`, '_blank', 'noopener')
      }
    } catch (err) {
      onError(`Could not preview "${project.name}": ${errorText(err)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    setBusy(true)
    try {
      await apiDelete(`/api/projects/${project.id}`)
      onDeleted(project.id)
    } catch (err) {
      onError(`Could not delete "${project.name}": ${errorText(err)}`)
      setBusy(false)
      setConfirming(false)
    }
  }

  const theme = project.theme || {}

  return (
    <div className="card project-card">
      <div className="project-card-title">
        <h3>
          <span
            className="project-swatch"
            style={{ backgroundColor: theme.primary_color || 'transparent', marginRight: 8 }}
          />
          {project.name}
        </h3>
        <span className="mono muted">{project.slug}</span>
      </div>
      <div className="project-card-desc">
        {project.description ? project.description : <span className="muted">No description</span>}
      </div>
      <div className="project-card-meta">Updated {formatDate(project.updated_at)}</div>
      <div className="project-card-actions">
        <button className="btn btn-primary btn-sm" type="button" onClick={handleOpenEditor} disabled={busy}>
          Open editor
        </button>
        <Link className="btn btn-sm" to={`/projects/${project.id}/cms`}>
          Open CMS
        </Link>
        <button className="btn btn-sm" type="button" onClick={handlePreview} disabled={busy}>
          Preview
        </button>
        <button className="btn btn-sm" type="button" onClick={() => onEdit(project)} disabled={busy}>
          Settings
        </button>
        {!confirming && (
          <button className="btn btn-danger btn-sm" type="button" onClick={() => setConfirming(true)} disabled={busy}>
            Delete
          </button>
        )}
      </div>
      {confirming && (
        <div className="project-card-confirm">
          <span>Delete this project and all its pages, content and assets?</span>
          <button className="btn btn-danger btn-sm" type="button" onClick={handleDelete} disabled={busy}>
            {busy ? 'Deleting...' : 'Yes, delete'}
          </button>
          <button className="btn btn-sm" type="button" onClick={() => setConfirming(false)} disabled={busy}>
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [modal, setModal] = useState(null) // null | {mode:'create'} | {mode:'edit', project}

  const aloadProjects = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const list = await apiGet('/api/projects')
      setProjects(Array.isArray(list) ? list : [])
    } catch (err) {
      setLoadError(errorText(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    aloadProjects()
  }, [aloadProjects])

  function handleSaved(saved) {
    setProjects((prev) => {
      const exists = prev.some((p) => p.id === saved.id)
      return exists ? prev.map((p) => (p.id === saved.id ? saved : p)) : [...prev, saved]
    })
    setModal(null)
  }

  function handleDeleted(projectId) {
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
  }

  return (
    <>
      <div className="topbar">
        <span className="topbar-brand">Website Builder Fable</span>
      </div>
      <div className="page">
        <div className="page-header">
          <h1>Projects</h1>
          <button className="btn btn-primary" type="button" onClick={() => setModal({ mode: 'create' })}>
            New project
          </button>
        </div>

        {actionError && (
          <div className="projects-page-error">
            <span>{actionError}</span>
            <button className="btn btn-sm" type="button" onClick={() => setActionError(null)}>
              Dismiss
            </button>
          </div>
        )}

        {loading && (
          <div className="panel">
            <div className="empty-state">Loading projects...</div>
          </div>
        )}

        {!loading && loadError && (
          <div className="panel">
            <div className="empty-state">
              <p style={{ marginBottom: 'var(--space-4)' }}>Failed to load projects: {loadError}</p>
              <button className="btn" type="button" onClick={aloadProjects}>
                Retry
              </button>
            </div>
          </div>
        )}

        {!loading && !loadError && projects.length === 0 && (
          <div className="panel">
            <div className="empty-state">
              <p style={{ marginBottom: 'var(--space-4)' }}>
                No projects yet. Create your first website project to get started.
              </p>
              <button className="btn btn-primary" type="button" onClick={() => setModal({ mode: 'create' })}>
                Create a project
              </button>
            </div>
          </div>
        )}

        {!loading && !loadError && projects.length > 0 && (
          <div className="projects-grid">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onEdit={(p) => setModal({ mode: 'edit', project: p })}
                onDeleted={handleDeleted}
                onError={setActionError}
              />
            ))}
          </div>
        )}
      </div>

      {modal && (
        <ProjectForm
          project={modal.mode === 'edit' ? modal.project : null}
          onSaved={handleSaved}
          onCancel={() => setModal(null)}
        />
      )}
    </>
  )
}
