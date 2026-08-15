// OWNED BY: frontend-cms agent (src/features/cms/**).
// Reusable Asset Picker modal (docs/decisions-cms.md 5.5a). Shows the project's
// image assets in a grid with an Upload button; clicking an asset calls
// onSelect(asset) with the full asset object {id, url, filename, ...} and the
// caller closes the modal. Also used by the editor's image block panel.

import { useEffect, useRef, useState } from 'react'
import { listAssets, uploadAsset } from './cmsApi.js'
import { formatBytes } from './fieldUtils.js'

export default function AssetPicker({ projectId, onSelect, onClose }) {
  const [assets, setAssets] = useState(null)
  const [error, setError] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
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

  async function handleFiles(event) {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
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

  return (
    <div className="cms-modal-backdrop" onClick={onClose}>
      <div className="cms-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cms-modal-header">
          <h2>Choose an image</h2>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
            <button type="button" className="btn btn-sm" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="cms-modal-body">
          {error && <div className="cms-error">{error}</div>}
          {assets === null && <div className="empty-state">Loading...</div>}
          {assets !== null && assets.length === 0 && (
            <div className="empty-state">No assets yet. Upload an image to get started.</div>
          )}
          {assets !== null && assets.length > 0 && (
            <div className="assets-grid">
              {assets.map((asset) => (
                <div
                  key={asset.id}
                  className="asset-card selectable"
                  onClick={() => onSelect(asset)}
                  title={`Select ${asset.filename}`}
                >
                  <img src={asset.url} alt={asset.filename} loading="lazy" />
                  <div className="asset-card-body">
                    <span className="asset-card-name">{asset.filename}</span>
                    <span className="muted">{formatBytes(asset.size)}</span>
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
          onChange={handleFiles}
        />
      </div>
    </div>
  )
}
