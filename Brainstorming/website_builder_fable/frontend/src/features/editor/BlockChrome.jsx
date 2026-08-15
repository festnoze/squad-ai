// OWNED BY: frontend-editor agent.
// Edit-mode wrapper around every non-root block: sortable registration,
// click-to-select, hover highlight, selection outline, and the floating
// mini-toolbar (label, drag grip, duplicate, delete).

import { useState } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useEditorStore } from './editorStore.js'
import { BLOCK_DEFINITIONS } from './blockDefinitions.js'

export default function BlockChrome({ node, parentId, index, children }) {
  const selectedId = useEditorStore(s => s.selectedId)
  const select = useEditorStore(s => s.select)
  const removeBlock = useEditorStore(s => s.removeBlock)
  const duplicateBlock = useEditorStore(s => s.duplicateBlock)
  const [hovered, setHovered] = useState(false)

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: node.id,
    data: { kind: 'canvas', nodeId: node.id, parentId, index, type: node.type },
  })

  const selected = selectedId === node.id
  const def = BLOCK_DEFINITIONS[node.type] || { label: node.type }

  const wrapperStyle = {
    position: 'relative',
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : undefined,
  }
  // Columns are the flex children of a row: the weight lives on the wrapper.
  if (node.type === 'column') {
    const fraction = Number(node.props.widthFraction) || 1
    wrapperStyle.flex = fraction + ' 1 0'
    wrapperStyle.minWidth = 0
  }

  const className = 'blk-wrap'
    + (selected ? ' blk-selected' : '')
    + (!selected && hovered ? ' blk-hover' : '')

  return (
    <div
      ref={setNodeRef}
      style={wrapperStyle}
      className={className}
      onClick={e => { e.stopPropagation(); select(node.id) }}
      onMouseOver={e => { e.stopPropagation(); setHovered(true) }}
      onMouseOut={e => { e.stopPropagation(); setHovered(false) }}
      {...attributes}
    >
      {(selected || hovered) && (
        <div className="blk-toolbar" onClick={e => e.stopPropagation()}>
          <span className="blk-toolbar-label">{def.label}</span>
          <button type="button" className="blk-tool blk-grip" title="Drag to move" {...listeners}>⠿</button>
          <button type="button" className="blk-tool" title="Duplicate (Ctrl+D)" onClick={() => duplicateBlock(node.id)}>⧉</button>
          <button type="button" className="blk-tool" title="Delete (Del)" onClick={() => removeBlock(node.id)}>✕</button>
        </div>
      )}
      {children}
    </div>
  )
}
