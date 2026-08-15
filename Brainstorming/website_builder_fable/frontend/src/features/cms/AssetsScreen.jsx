// OWNED BY: frontend-cms agent (src/features/cms/**).
// Asset library screen at /projects/:projectId/cms/assets (docs/decisions-cms.md 5.5;
// route placement per CONTRACTS.md reconciliation decision 6).

import { useEffect, useRef, useState } from 'react'
import { listAssets, uploadAsset, deleteAsset } from './cmsApi.js'
import { formatBytes, formatDate } from './fieldUtils.js'

export default function AssetsScreen({ projectId }) {
  const [assets, setAssets] = useState(null)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [copiedId, setCopiedId] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setAssets(null)
    listAssets(projectId)
      .then((items) => {
        if (!cancelled) setAssets(items)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  async function uploadAll(files) {
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      for (const file of files) {
        const asset = await uploadAsset(projectId, file)
        setAssets((prev) => [asset, ...(prev || [])])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  function handleFileInput(event) {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    uploadAll(files)
  }

  function handleDrop(event) {
    event.preventDefault()
    const files = Array.from(event.dataTransfer.files || []).filter((f) =>
      f.type.startsWith('image/')
    )
    uploadAll(files)
  }

  async function handleCopyUrl(asset) {
    const absolute = `${window.location.origin}${asset.url}`
    try {
      await navigator.clipboard.writeText(absolute)
    } catch {
      // Clipboard API can be unavailable (http, permissions); fall back to a prompt.
      window.prompt('Copy the asset URL:', absolute)
    }
    setCopiedId(asset.id)
    setTimeout(() => setCopiedId((current) => (current === asset.id ? null : current)), 1500)
  }

  async function handleDelete(asset) {
    if (!window.confirm(`Delete asset "${asset.filename}"? This cannot be undone.`)) return
    setError(null)
    try {
      await deleteAsset(projectId, asset.id)
      setAssets((prev) => (prev || []).filter((a) => a.id !== asset.id))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Assets</h1>
        <button
          type="button"
          className="btn btn-primary"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>

      {error && <div className="cms-error">{error}</div>}

      <div onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}>
        {assets === null && <div className="empty-state">Loading...</div>}
        {assets !== null && assets.length === 0 && (
          <div className="panel">
            <div className="empty-state">
              <p>No assets yet.</p>
              <p style={{ marginTop: 8 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload
                </button>
              </p>
            </div>
          </div>
        )}
        {assets !== null && assets.length > 0 && (
          <div className="assets-grid">
            {assets.map((asset) => (
              <div key={asset.id} className="asset-card">
                <img src={asset.url} alt={asset.filename} loading="lazy" />
                <div className="asset-card-body">
                  <span className="asset-card-name" title={asset.filename}>
                    {asset.filename}
                  </span>
                  <span className="muted">
                    {formatBytes(asset.size)} - {formatDate(asset.created_at)}
                  </span>
                </div>
                <div className="asset-card-actions">
                  <button type="button" className="btn btn-sm" onClick={() => handleCopyUrl(asset)}>
                    {copiedId === asset.id ? 'Copied!' : 'Copy URL'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => handleDelete(asset)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        style={{ display: 'none' }}
        onChange={handleFileInput}
      />
    </div>
  )
}
