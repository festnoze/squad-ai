// OWNED BY: frontend-editor agent.
// Scrollable grey canvas area with a centered white sheet whose width follows
// the responsive device switch. Clicking the background clears the selection.

import { useEditorStore, DEVICE_WIDTHS } from './editorStore.js'
import BlockRenderer from './BlockRenderer.jsx'

export default function Canvas() {
  const tree = useEditorStore(s => s.tree)
  const device = useEditorStore(s => s.device)
  const select = useEditorStore(s => s.select)
  return (
    <div className="ed-canvas" onClick={() => select(null)}>
      <div className="ed-sheet" style={{ width: DEVICE_WIDTHS[device] + 'px' }}>
        <BlockRenderer node={tree} />
      </div>
    </div>
  )
}
