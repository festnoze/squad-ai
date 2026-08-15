// OWNED BY: frontend-editor agent.
// Canvas preview of the collection list binding: fetches up to `limit` entries
// of the bound collection and repeats the item template (stub preview matching
// the server-rendered markup classes). Unbound or stale bindings never crash.

import { useEffect, useState } from 'react'
import { apiGet } from '../../../api/client.js'
import { useEditorStore } from '../editorStore.js'

function clampLimit(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 6
  return Math.max(1, Math.min(50, Math.round(n)))
}

export default function CollectionListBlock({ node, css }) {
  const projectId = useEditorStore(s => s.projectId)
  const { collectionId } = node.props
  const itemTemplate = node.props.itemTemplate || {}
  const limit = clampLimit(node.props.limit)
  const [entries, setEntries] = useState(null)
  const [assetUrls, setAssetUrls] = useState({})

  useEffect(() => {
    let alive = true
    if (!projectId || !collectionId) {
      setEntries(null)
      return undefined
    }
    apiGet(`/api/projects/${projectId}/collections/${collectionId}/entries?limit=${limit}&offset=0`)
      .then(res => { if (alive) setEntries(res && Array.isArray(res.items) ? res.items : []) })
      .catch(() => { if (alive) setEntries([]) })
    apiGet(`/api/projects/${projectId}/assets`)
      .then(list => {
        if (alive) setAssetUrls(Object.fromEntries((list || []).map(a => [a.id, a.url])))
      })
      .catch(() => {})
    return () => { alive = false }
  }, [projectId, collectionId, limit])

  if (!collectionId) {
    return <div className="blk-cl-empty" style={css}>Collection list: no collection bound</div>
  }
  if (entries === null) {
    return <div className="blk-cl-empty" style={css}>Loading entries...</div>
  }
  if (entries.length === 0) {
    return <div className="blk-cl-empty" style={css}>No entries</div>
  }

  const { gap, ...rest } = css
  return (
    <div
      className="collection-list"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: gap || '16px',
        ...rest,
      }}
    >
      {entries.map(entry => {
        const data = entry.data || {}
        const title = itemTemplate.title ? data[itemTemplate.title] : null
        const text = itemTemplate.text ? data[itemTemplate.text] : null
        let image = itemTemplate.image ? data[itemTemplate.image] : null
        if (typeof image === 'number') image = assetUrls[image] || null
        const textString = text === null || text === undefined
          ? ''
          : String(text).replace(/<[^>]*>/g, '')
        return (
          <div key={entry.id} className="cl-item">
            {image ? (
              <img
                className="cl-item-image"
                src={image}
                alt={title !== null && title !== undefined ? String(title) : ''}
                draggable={false}
              />
            ) : null}
            {title !== null && title !== undefined && title !== '' ? (
              <h3 className="cl-item-title">{String(title)}</h3>
            ) : null}
            {textString ? <div className="cl-item-text">{textString}</div> : null}
          </div>
        )
      })}
    </div>
  )
}
