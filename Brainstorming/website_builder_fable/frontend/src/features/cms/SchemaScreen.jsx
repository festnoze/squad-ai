// OWNED BY: frontend-cms agent (src/features/cms/**).
// Schema builder at /projects/:projectId/cms/collections/:collectionId/schema
// (docs/decisions-cms.md 5.2). Add/remove/reorder fields; save is a single PUT
// with the full fields array. Reorder via up/down arrow buttons (the documented
// simple fallback; dnd is optional polish).

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getCollection, updateCollection } from './cmsApi.js'
import { FIELD_TYPES, keyFromLabel, newField, validateFields } from './fieldUtils.js'

let localIdCounter = 0
function nextLocalId() {
  localIdCounter += 1
  return `f${localIdCounter}`
}

function OptionsEditor({ options, onChange }) {
  const [draft, setDraft] = useState('')

  function addOption() {
    const value = draft.trim()
    if (!value || options.includes(value)) {
      setDraft('')
      return
    }
    onChange([...options, value])
    setDraft('')
  }

  return (
    <div className="options-editor">
      <span className="schema-mini-label" style={{ width: '100%' }}>
        Options
      </span>
      {options.map((option) => (
        <span key={option} className="option-chip">
          {option}
          <button
            type="button"
            title={`Remove ${option}`}
            onClick={() => onChange(options.filter((o) => o !== option))}
          >
            x
          </button>
        </span>
      ))}
      <input
        className="input"
        value={draft}
        placeholder="Add option"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            addOption()
          }
        }}
      />
      <button type="button" className="btn btn-sm" onClick={addOption}>
        Add
      </button>
    </div>
  )
}

export default function SchemaScreen({ projectId, reloadCollections }) {
  const { collectionId } = useParams()
  const navigate = useNavigate()

  const [collection, setCollection] = useState(null)
  const [name, setName] = useState('')
  // rows: field descriptors plus UI-only props (_localId for React keys, _saved
  // meaning the field existed on the server, so key edits are discouraged).
  const [rows, setRows] = useState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [clientErrors, setClientErrors] = useState([])

  useEffect(() => {
    let cancelled = false
    setCollection(null)
    setError(null)
    getCollection(projectId, collectionId)
      .then((data) => {
        if (cancelled) return
        setCollection(data)
        setName(data.name)
        setRows(
          data.fields.map((field) => ({ ...field, _localId: nextLocalId(), _saved: true }))
        )
        setDirty(false)
        setClientErrors([])
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [projectId, collectionId])

  // Warn on tab close with unsaved changes (in-app blocking would need a data
  // router, which the frozen App.jsx does not use; decision: beforeunload only).
  useEffect(() => {
    if (!dirty) return undefined
    const handler = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const errorsByIndex = useMemo(() => {
    const map = {}
    for (const err of clientErrors) {
      map[err.index] = map[err.index] ? `${map[err.index]}; ${err.message}` : err.message
    }
    return map
  }, [clientErrors])

  function patchRow(index, patch) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)))
    setDirty(true)
  }

  function handleLabelChange(index, label) {
    setRows((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row
        const patch = { label }
        // Typing the label updates the key suggestion only while the field is new.
        if (!row._saved) patch.key = keyFromLabel(label)
        return { ...row, ...patch }
      })
    )
    setDirty(true)
  }

  function moveRow(index, delta) {
    setRows((prev) => {
      const target = index + delta
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return next
    })
    setDirty(true)
  }

  function removeRow(index) {
    setRows((prev) => prev.filter((_, i) => i !== index))
    setDirty(true)
  }

  function addRow() {
    setRows((prev) => [...prev, { ...newField(), _localId: nextLocalId(), _saved: false }])
    setDirty(true)
  }

  async function handleSave() {
    const fields = rows.map(({ _localId, _saved, ...field }) => ({
      ...field,
      options: field.type === 'select' ? field.options : []
    }))
    const errors = validateFields(fields)
    setClientErrors(errors)
    if (errors.length > 0) return

    setSaving(true)
    setError(null)
    try {
      const payload = { fields }
      if (name.trim() && name.trim() !== collection.name) payload.name = name.trim()
      const updated = await updateCollection(projectId, collectionId, payload)
      setCollection(updated)
      setName(updated.name)
      setRows(updated.fields.map((field) => ({ ...field, _localId: nextLocalId(), _saved: true })))
      setDirty(false)
      await reloadCollections()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
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
        <div>
          <input
            className="input"
            style={{ fontSize: 20, fontWeight: 700, width: 320 }}
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              setDirty(true)
            }}
            aria-label="Collection name"
          />
          <div className="muted mono" style={{ marginTop: 4 }}>
            {collection.slug}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {dirty && <span className="muted">Unsaved changes</span>}
          <button
            type="button"
            className="btn"
            onClick={() =>
              navigate(`/projects/${projectId}/cms/collections/${collectionId}/entries`)
            }
          >
            Entries
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving || !dirty}
            onClick={handleSave}
          >
            {saving ? 'Saving...' : 'Save schema'}
          </button>
        </div>
      </div>

      {error && <div className="cms-error">{error}</div>}

      {rows.length === 0 && (
        <div className="panel" style={{ marginBottom: 12 }}>
          <div className="empty-state">No fields yet. Add the first field below.</div>
        </div>
      )}

      {rows.map((row, index) => (
        <div key={row._localId} className="schema-field-row">
          <div className="schema-order-buttons">
            <button
              type="button"
              className="btn btn-sm"
              title="Move up"
              disabled={index === 0}
              onClick={() => moveRow(index, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              className="btn btn-sm"
              title="Move down"
              disabled={index === rows.length - 1}
              onClick={() => moveRow(index, 1)}
            >
              ↓
            </button>
          </div>
          <div className="schema-field-main">
            <div>
              <span className="schema-mini-label">Label</span>
              <input
                className="input"
                value={row.label}
                placeholder="Title"
                onChange={(e) => handleLabelChange(index, e.target.value)}
              />
            </div>
            <div>
              <span className="schema-mini-label">Key</span>
              <input
                className="input mono"
                value={row.key}
                placeholder="title"
                title={
                  row._saved
                    ? 'Warning: changing keys orphans existing entry values'
                    : 'Machine key: [a-z][a-z0-9_]*'
                }
                onChange={(e) => patchRow(index, { key: e.target.value })}
              />
            </div>
            <div>
              <span className="schema-mini-label">Type</span>
              <select
                className="select"
                value={row.type}
                onChange={(e) =>
                  patchRow(index, {
                    type: e.target.value,
                    options: e.target.value === 'select' ? row.options : []
                  })
                }
              >
                {FIELD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            {row.type === 'select' && (
              <OptionsEditor
                options={row.options || []}
                onChange={(options) => patchRow(index, { options })}
              />
            )}
            {errorsByIndex[index] && (
              <div className="schema-field-error">{errorsByIndex[index]}</div>
            )}
          </div>
          <label className="schema-required">
            <input
              type="checkbox"
              checked={row.required}
              onChange={(e) => patchRow(index, { required: e.target.checked })}
            />
            Required
          </label>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            style={{ marginTop: 16 }}
            onClick={() => removeRow(index)}
          >
            Remove
          </button>
        </div>
      ))}

      <button type="button" className="btn" onClick={addRow}>
        Add field
      </button>
    </div>
  )
}
