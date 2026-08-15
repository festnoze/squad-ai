// OWNED BY: frontend-editor agent.
// Modal listing the project's uploaded images (GET /api/projects/{pid}/assets).
// Picking one hands the asset back to the caller (used by the image block).

import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client.js'

export default function AssetPicker({ projectId, onPick, onClose }) {
  const [assets, setAssets] = useState(null)

  useEffect(() => {
    let alive = true
    apiGet(`/api/projects/${projectId}/assets`)
      .then(list => { if (alive) setAssets(list || []) })
      .catch(() => { if (alive) setAssets([]) })
    return () => { alive = false }
  }, [projectId])

  return (
    <div className="ed-modal-backdrop" onClick={onClose}>
      <div className="ed-modal" onClick={e => e.stopPropagation()}>
        <div className="ed-modal-header">
          <h3>Choose an asset</h3>
          <button type="button" className="btn btn-sm" onClick={onClose}>Close</button>
        </div>
        <div className="ed-modal-body">
          {assets === null ? (
            <div className="empty-state">Loading assets...</div>
          ) : assets.length === 0 ? (
            <div className="empty-state">
              No assets yet. Upload images from the CMS asset library.
            </div>
          ) : (
            <div className="asset-grid">
              {assets.map(asset => (
                <button
                  key={asset.id}
                  type="button"
                  className="asset-cell"
                  onClick={() => onPick(asset)}
                  title={asset.filename}
                >
                  <img src={asset.url} alt={asset.filename} />
                  <span className="asset-name">{asset.filename}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
