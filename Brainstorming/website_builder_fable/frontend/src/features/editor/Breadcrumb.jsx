// OWNED BY: frontend-editor agent.
// Ancestor breadcrumb under the top bar. First chip is "Page" (clears the
// selection); each following chip selects that ancestor.

import { useEditorStore } from './editorStore.js'
import { findPath } from './treeUtils.js'
import { BLOCK_DEFINITIONS } from './blockDefinitions.js'

export default function Breadcrumb() {
  const tree = useEditorStore(s => s.tree)
  const selectedId = useEditorStore(s => s.selectedId)
  const select = useEditorStore(s => s.select)

  const path = selectedId ? findPath(tree, selectedId).filter(n => n.type !== 'page') : []

  return (
    <div className="ed-breadcrumb">
      <button type="button" className="crumb" onClick={() => select(null)}>Page</button>
      {path.map(node => (
        <span key={node.id} className="crumb-item">
          <span className="crumb-sep">/</span>
          <button
            type="button"
            className={'crumb' + (node.id === selectedId ? ' crumb-current' : '')}
            onClick={() => select(node.id)}
          >
            {(BLOCK_DEFINITIONS[node.type] || { label: node.type }).label}
          </button>
        </span>
      ))}
      {!selectedId && <span className="muted crumb-hint">No block selected</span>}
    </div>
  )
}
