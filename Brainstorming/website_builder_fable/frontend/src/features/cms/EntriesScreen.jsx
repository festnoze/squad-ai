// OWNED BY: frontend-cms agent (src/features/cms/**).
// Entries table at /projects/:projectId/cms/collections/:collectionId/entries
// (docs/decisions-cms.md 5.3). Columns are the first 4 schema fields plus
// Updated; Prev/Next pagination over limit/offset.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getCollection, listEntries, deleteEntry, listAssets } from './cmsApi.js'
import { formatDate, resolveImageUrl, stripTags, truncate } from './fieldUtils.js'

const PAGE_SIZE = 50

function CellValue({ field, value, assetUrlById }) {
  if (value == null || value === '') return <span className="muted">-</span>
  switch (field.type) {
    case 'richtext':
      return <span>{truncate(stripTags(value))}</span>
    case 'boolean':
      return <span>{value ? '✓' : '✕'}</span>
    case 'image': {
      const url = resolveImageUrl(value, assetUrlById)
      if (!url) return <span className="muted">missing</span>
      return <img className="entry-thumb" src={url} alt="" loading="lazy" />
    }
    case 'number':
    case 'date':
      return <span>{String(value)}</span>
    default:
      return <span>{truncate(String(value))}</span>
  }
}

export default function EntriesScreen({ projectId }) {
  const { collectionId } = useParams()
  const navigate = useNavigate()

  const [collection, setCollection] = useState(null)
  const [entriesPage, setEntriesPage] = useState(null)
  const [offset, setOffset] = useState(0)
  const [assetUrlById, setAssetUrlById] = useState({})
  const [error, setError] = useState(null)

  const columns = useMemo(
    () => (collection ? collection.fields.slice(0, 4) : []),
    [collection]
  )
  const hasImageColumn = columns.some((f) => f.type === 'image')

  useEffect(() => {
    let cancelled = false
    setCollection(null)
    setOffset(0)
    getCollection(projectId, collectionId)
      .then((data) => {
        if (!cancelled) setCollection(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, collectionId])

  useEffect(() => {
    let cancelled = false
    setEntriesPage(null)
    listEntries(projectId, collectionId, PAGE_SIZE, offset)
      .then((page) => {
        if (!cancelled) setEntriesPage(page)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, collectionId, offset])

  useEffect(() => {
    if (!hasImageColumn) return undefined
    let cancelled = false
    listAssets(projectId)
      .then((assets) => {
        if (cancelled) return
        const map = {}
        for (const asset of assets) map[asset.id] = asset.url
        setAssetUrlById(map)
      })
      .catch(() => {
        // thumbnails degrade to "missing"; not fatal
      })
    return () => {
      cancelled = true
    }
  }, [projectId, hasImageColumn])

  async function handleDelete(event, entry) {
    event.stopPropagation()
    if (!window.confirm('Delete this entry? This cannot be undone.')) return
    setError(null)
    try {
      await deleteEntry(projectId, collectionId, entry.id)
      const page = await listEntries(projectId, collectionId, PAGE_SIZE, offset)
      setEntriesPage(page)
    } catch (err) {
      setError(err.message)
    }
  }

  if (error && !collection) {
    return <div className="cms-error">{error}</div>
  }
  if (!collection) {
    return <div className="empty-state">Loading...</div>
  }

  const base = `/projects/${projectId}/cms/collections/${collectionId}`
  const total = entriesPage ? entriesPage.total : 0
  const items = entriesPage ? entriesPage.items : []
  const from = total === 0 ? 0 : offset + 1
  const to = offset + items.length

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>{collection.name}</h1>
          <div className="muted" style={{ marginTop: 4 }}>
            {total} entries
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn" onClick={() => navigate(`${base}/schema`)}>
            Schema
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate(`${base}/entries/new`)}
          >
            New entry
          </button>
        </div>
      </div>

      {error && <div className="cms-error">{error}</div>}

      {collection.fields.length === 0 && (
        <div className="panel">
          <div className="empty-state">
            This collection has no fields yet. Define its schema first.
          </div>
        </div>
      )}

      {collection.fields.length > 0 && entriesPage === null && (
        <div className="empty-state">Loading entries...</div>
      )}

      {collection.fields.length > 0 && entriesPage !== null && items.length === 0 && (
        <div className="panel">
          <div className="empty-state">No entries yet.</div>
        </div>
      )}

      {collection.fields.length > 0 && entriesPage !== null && items.length > 0 && (
        <div className="panel">
          <table className="table">
            <thead>
              <tr>
                {columns.map((field) => (
                  <th key={field.key}>{field.label}</th>
                ))}
                <th>Updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((entry) => (
                <tr
                  key={entry.id}
                  className="entries-row"
                  onClick={() => navigate(`${base}/entries/${entry.id}`)}
                >
                  {columns.map((field) => (
                    <td key={field.key}>
                      <CellValue
                        field={field}
                        value={entry.data[field.key]}
                        assetUrlById={assetUrlById}
                      />
                    </td>
                  ))}
                  <td className="muted">{formatDate(entry.updated_at)}</td>
                  <td>
                    <div className="cms-row-actions">
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={(e) => handleDelete(e, entry)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="entries-pagination">
            <span className="muted">
              {from}-{to} of {total}
            </span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
