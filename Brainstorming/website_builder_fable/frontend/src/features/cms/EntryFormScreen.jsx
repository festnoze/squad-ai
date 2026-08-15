// OWNED BY: frontend-cms agent (src/features/cms/**).
// Entry form at /projects/:projectId/cms/collections/:collectionId/entries/:entryId
// and .../entries/new (docs/decisions-cms.md 5.4). The form is generated from the
// collection schema; 422 detail items map to inline errors per field key.

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  getCollection,
  getEntry,
  createEntry,
  updateEntry,
  deleteEntry,
  listAssets
} from './cmsApi.js'
import { emptyValueFor, resolveImageUrl, toApiValue } from './fieldUtils.js'
import RichTextEditor from './RichTextEditor.jsx'
import AssetPicker from './AssetPicker.jsx'

function ImageFieldInput({ projectId, value, onChange, assetUrlById }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [urlMode, setUrlMode] = useState(typeof value === 'string' && value !== '')

  const previewUrl = resolveImageUrl(value, assetUrlById)

  return (
    <div>
      {previewUrl && <img className="image-field-preview" src={previewUrl} alt="" />}
      <div className="image-field-actions">
        <button type="button" className="btn btn-sm" onClick={() => setPickerOpen(true)}>
          Choose image
        </button>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            const next = !urlMode
            setUrlMode(next)
            if (next && typeof value === 'number') onChange('')
          }}
        >
          {urlMode ? 'Hide URL input' : 'Use URL'}
        </button>
        {value != null && value !== '' && (
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              onChange(null)
              setUrlMode(false)
            }}
          >
            Clear
          </button>
        )}
        {typeof value === 'number' && <span className="muted mono">asset #{value}</span>}
      </div>
      {urlMode && (
        <input
          className="input"
          style={{ marginTop: 8 }}
          type="text"
          placeholder="https://... or /api/uploads/..."
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {pickerOpen && (
        <AssetPicker
          projectId={projectId}
          onSelect={(asset) => {
            onChange(asset.id)
            setUrlMode(false)
            setPickerOpen(false)
          }}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  )
}

function FieldInput({ projectId, field, value, onChange, assetUrlById }) {
  switch (field.type) {
    case 'text':
      return (
        <input
          className="input"
          type="text"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'richtext':
      return <RichTextEditor value={value ?? ''} onChange={onChange} />
    case 'number':
      return (
        <input
          className="input"
          type="number"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'boolean':
      return (
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span className="muted">{value ? 'Yes' : 'No'}</span>
        </label>
      )
    case 'date':
      return (
        <input
          className="input"
          type="date"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'image':
      return (
        <ImageFieldInput
          projectId={projectId}
          value={value}
          onChange={onChange}
          assetUrlById={assetUrlById}
        />
      )
    case 'select':
      return (
        <select className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
          {!field.required && <option value="">(none)</option>}
          {field.required && (value == null || value === '') && <option value="">Choose...</option>}
          {(field.options || []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )
    default:
      return null
  }
}

export default function EntryFormScreen({ projectId }) {
  const { collectionId, entryId } = useParams()
  const navigate = useNavigate()
  const isNew = entryId === undefined

  const [collection, setCollection] = useState(null)
  const [values, setValues] = useState({})
  const [assetUrlById, setAssetUrlById] = useState({})
  const [fieldErrors, setFieldErrors] = useState({})
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const tableUrl = `/projects/${projectId}/cms/collections/${collectionId}/entries`

  useEffect(() => {
    let cancelled = false
    setCollection(null)
    setError(null)
    setFieldErrors({})
    setDirty(false)

    async function load() {
      const coll = await getCollection(projectId, collectionId)
      let entry = null
      if (!isNew) {
        entry = await getEntry(projectId, collectionId, entryId)
      }
      if (cancelled) return
      const initial = {}
      for (const field of coll.fields) {
        const stored = entry ? entry.data[field.key] : null
        initial[field.key] = stored == null ? emptyValueFor(field.type) : stored
      }
      setCollection(coll)
      setValues(initial)
    }

    load().catch((err) => {
      if (!cancelled) setError(err.message)
    })
    return () => {
      cancelled = true
    }
  }, [projectId, collectionId, entryId, isNew])

  useEffect(() => {
    let cancelled = false
    listAssets(projectId)
      .then((assets) => {
        if (cancelled) return
        const map = {}
        for (const asset of assets) map[asset.id] = asset.url
        setAssetUrlById(map)
      })
      .catch(() => {
        // preview thumbnails only; not fatal
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  function setFieldValue(key, value) {
    setValues((prev) => ({ ...prev, [key]: value }))
    setDirty(true)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!collection) return
    const data = {}
    for (const field of collection.fields) {
      data[field.key] = toApiValue(field.type, values[field.key])
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      if (isNew) {
        await createEntry(projectId, collectionId, data)
      } else {
        await updateEntry(projectId, collectionId, entryId, data)
      }
      navigate(tableUrl)
    } catch (err) {
      if (err.status === 422 && Array.isArray(err.detail)) {
        const byField = {}
        for (const item of err.detail) {
          if (item && item.field) byField[item.field] = item.message || 'Invalid value'
        }
        setFieldErrors(byField)
        if (Object.keys(byField).length === 0) setError('Validation failed')
      } else {
        setError(err.message)
      }
    } finally {
      setSaving(false)
    }
  }

  function handleCancel() {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    navigate(tableUrl)
  }

  async function handleDelete() {
    if (!window.confirm('Delete this entry? This cannot be undone.')) return
    setError(null)
    try {
      await deleteEntry(projectId, collectionId, entryId)
      navigate(tableUrl)
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

  return (
    <div>
      <div className="page-header">
        <h1>
          {collection.name}: {isNew ? 'new entry' : `entry #${entryId}`}
        </h1>
      </div>

      {error && <div className="cms-error">{error}</div>}

      {collection.fields.length === 0 ? (
        <div className="panel">
          <div className="empty-state">
            This collection has no fields. Define its schema before adding entries.
          </div>
        </div>
      ) : (
        <form className="entry-form panel" onSubmit={handleSubmit}>
          <div className="panel-body">
            {collection.fields.map((field) => (
              <div className="field" key={field.key}>
                <label className="field-label">
                  {field.label}
                  {field.required ? ' *' : ''}
                </label>
                <FieldInput
                  projectId={projectId}
                  field={field}
                  value={values[field.key]}
                  onChange={(v) => setFieldValue(field.key, v)}
                  assetUrlById={assetUrlById}
                />
                {fieldErrors[field.key] && (
                  <div className="field-error">{fieldErrors[field.key]}</div>
                )}
              </div>
            ))}
          </div>
          <div className="cms-modal-footer" style={{ borderTop: '1px solid var(--color-border)' }}>
            {!isNew && (
              <button
                type="button"
                className="btn btn-danger"
                style={{ marginRight: 'auto' }}
                onClick={handleDelete}
              >
                Delete
              </button>
            )}
            <button type="button" className="btn" onClick={handleCancel}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
