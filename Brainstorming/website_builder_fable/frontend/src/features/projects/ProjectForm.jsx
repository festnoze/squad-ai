// OWNED BY: frontend-projects agent (src/features/projects/**).
// Create / edit-settings form rendered inside a modal by ProjectsPage.

import { useState } from 'react'
import { apiPost, apiPut } from '../../api/client.js'

const DEFAULT_THEME = { primary_color: '#2563eb', font: 'system-ui', base_spacing: 16 }

const FONT_OPTIONS = [
  'system-ui',
  'Arial, sans-serif',
  'Georgia, serif',
  '"Times New Roman", serif',
  'Verdana, sans-serif',
  '"Courier New", monospace'
]

export function slugify(name) {
  // NFD-decompose, drop combining marks (U+0300..U+036F), keep [a-z0-9] runs.
  const decomposed = String(name).toLowerCase().normalize('NFD')
  let ascii = ''
  for (const ch of decomposed) {
    const code = ch.charCodeAt(0)
    if (code >= 0x0300 && code <= 0x036f) continue
    ascii += ch
  }
  return ascii.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

function errorText(err) {
  if (!err) return 'Unknown error'
  if (typeof err.detail === 'string') return err.detail
  if (Array.isArray(err.detail)) {
    return err.detail.map((d) => d.message || d.msg || JSON.stringify(d)).join('; ')
  }
  return err.message || 'Request failed'
}

// props: project (null for create), onSaved(project), onCancel()
export default function ProjectForm({ project, onSaved, onCancel }) {
  const isEdit = Boolean(project)
  const [name, setName] = useState(project ? project.name : '')
  const [slug, setSlug] = useState(project ? project.slug : '')
  const [slugTouched, setSlugTouched] = useState(isEdit)
  const [description, setDescription] = useState(project ? project.description || '' : '')
  const [theme, setTheme] = useState(() => ({ ...DEFAULT_THEME, ...(project ? project.theme : {}) }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  function handleNameChange(value) {
    setName(value)
    if (!slugTouched) setSlug(slugify(value))
  }

  function setThemeKey(key, value) {
    setTheme((t) => ({ ...t, [key]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    const spacing = Number(theme.base_spacing)
    const payload = {
      name: name.trim(),
      slug: slug.trim() || slugify(name),
      description: description,
      theme: {
        primary_color: theme.primary_color,
        font: theme.font,
        base_spacing: Number.isFinite(spacing) && spacing > 0 ? spacing : DEFAULT_THEME.base_spacing
      }
    }
    setSaving(true)
    setError(null)
    try {
      const saved = isEdit
        ? await apiPut(`/api/projects/${project.id}`, payload)
        : await apiPost('/api/projects', payload)
      onSaved(saved)
    } catch (err) {
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <div className="projects-modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <div className="panel projects-modal">
        <div className="panel-header">
          <h2>{isEdit ? 'Project settings' : 'New project'}</h2>
          <button className="btn btn-sm" type="button" onClick={onCancel}>Close</button>
        </div>
        <form className="panel-body" onSubmit={handleSubmit}>
          {error && <div className="projects-form-error">{error}</div>}

          <div className="field">
            <label className="field-label" htmlFor="project-name">Name</label>
            <input
              id="project-name"
              className="input"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="My Site"
              autoFocus
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="project-slug">Slug</label>
            <input
              id="project-slug"
              className="input mono"
              value={slug}
              onChange={(e) => { setSlugTouched(true); setSlug(e.target.value) }}
              onBlur={() => setSlug((s) => slugify(s))}
              placeholder="my-site"
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="project-description">Description</label>
            <textarea
              id="project-description"
              className="textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this website about?"
            />
          </div>

          <h3 style={{ marginBottom: 'var(--space-3)' }}>Theme</h3>
          <div className="projects-form-row">
            <div className="field">
              <label className="field-label" htmlFor="project-color">Primary color</label>
              <div className="projects-color-field">
                <input
                  id="project-color"
                  type="color"
                  className="projects-color-input"
                  value={theme.primary_color}
                  onChange={(e) => setThemeKey('primary_color', e.target.value)}
                />
                <span className="mono">{theme.primary_color}</span>
              </div>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="project-font">Font</label>
              <select
                id="project-font"
                className="select"
                value={FONT_OPTIONS.includes(theme.font) ? theme.font : 'system-ui'}
                onChange={(e) => setThemeKey('font', e.target.value)}
              >
                {FONT_OPTIONS.map((f) => (
                  <option key={f} value={f}>{f.split(',')[0].replace(/"/g, '')}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="project-spacing">Base spacing (px)</label>
              <input
                id="project-spacing"
                type="number"
                min="0"
                max="64"
                className="input"
                value={theme.base_spacing}
                onChange={(e) => setThemeKey('base_spacing', e.target.value)}
              />
            </div>
          </div>

          <div className="projects-modal-actions">
            <button className="btn" type="button" onClick={onCancel} disabled={saving}>Cancel</button>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? 'Saving...' : isEdit ? 'Save settings' : 'Create project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
