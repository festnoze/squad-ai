// OWNED BY: frontend-cms agent (src/features/cms/**).
// Collections list screen at /projects/:projectId/cms (docs/decisions-cms.md 5.1).

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCollection, deleteCollection } from './cmsApi.js'
import { slugify, formatDate } from './fieldUtils.js'

export default function CollectionsScreen({ projectId, collections, reloadCollections }) {
  const navigate = useNavigate()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [slugTouched, setSlugTouched] = useState(false)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const cmsBase = `/projects/${projectId}/cms`

  function openDialog() {
    setName('')
    setSlug('')
    setSlugTouched(false)
    setError(null)
    setDialogOpen(true)
  }

  function handleNameChange(value) {
    setName(value)
    if (!slugTouched) setSlug(slugify(value))
  }

  async function handleCreate(event) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const payload = { name: name.trim() }
      if (slug.trim()) payload.slug = slug.trim()
      const created = await createCollection(projectId, payload)
      setDialogOpen(false)
      await reloadCollections()
      navigate(`${cmsBase}/collections/${created.id}/schema`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(collection) {
    const ok = window.confirm(
      `Delete collection "${collection.name}" and all its entries? This cannot be undone.`
    )
    if (!ok) return
    setError(null)
    try {
      await deleteCollection(projectId, collection.id)
      await reloadCollections()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Collections</h1>
        <button type="button" className="btn btn-primary" onClick={openDialog}>
          New collection
        </button>
      </div>

      {error && !dialogOpen && <div className="cms-error">{error}</div>}

      {collections !== null && collections.length === 0 && (
        <div className="panel">
          <div className="empty-state">
            <p>No collections yet.</p>
            <p style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-primary" onClick={openDialog}>
                New collection
              </button>
            </p>
          </div>
        </div>
      )}

      {collections !== null && collections.length > 0 && (
        <div className="panel">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Fields</th>
                <th>Entries</th>
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {collections.map((collection) => (
                <tr key={collection.id}>
                  <td>{collection.name}</td>
                  <td className="mono">{collection.slug}</td>
                  <td>{collection.fields.length}</td>
                  <td>{collection.entry_count}</td>
                  <td className="muted">{formatDate(collection.updated_at)}</td>
                  <td>
                    <div className="cms-row-actions">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() =>
                          navigate(`${cmsBase}/collections/${collection.id}/entries`)
                        }
                      >
                        Entries
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => navigate(`${cmsBase}/collections/${collection.id}/schema`)}
                      >
                        Schema
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => handleDelete(collection)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dialogOpen && (
        <div className="cms-modal-backdrop" onClick={() => setDialogOpen(false)}>
          <div className="cms-modal narrow" onClick={(e) => e.stopPropagation()}>
            <form onSubmit={handleCreate}>
              <div className="cms-modal-header">
                <h2>New collection</h2>
              </div>
              <div className="cms-modal-body">
                {error && <div className="cms-error">{error}</div>}
                <div className="field">
                  <label className="field-label">Name *</label>
                  <input
                    className="input"
                    value={name}
                    onChange={(e) => handleNameChange(e.target.value)}
                    placeholder="Blog Posts"
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label className="field-label">Slug</label>
                  <input
                    className="input mono"
                    value={slug}
                    onChange={(e) => {
                      setSlugTouched(true)
                      setSlug(e.target.value)
                    }}
                    placeholder="blog-posts"
                  />
                </div>
              </div>
              <div className="cms-modal-footer">
                <button type="button" className="btn" onClick={() => setDialogOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? 'Creating...' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
