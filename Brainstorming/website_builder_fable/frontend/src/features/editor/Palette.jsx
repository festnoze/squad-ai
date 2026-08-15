// OWNED BY: frontend-editor agent.
// Draggable block palette. Items are drag sources only (never removed);
// dropping one on a valid container inserts a fresh default node.

import { useDraggable } from '@dnd-kit/core'
import { PALETTE_TYPES, BLOCK_DEFINITIONS } from './blockDefinitions.js'

function PaletteItem({ type }) {
  const def = BLOCK_DEFINITIONS[type]
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: 'palette-' + type,
    data: { kind: 'palette', blockType: type },
  })
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={'palette-item' + (isDragging ? ' palette-item-dragging' : '')}
      title={'Drag "' + def.label + '" onto the canvas'}
    >
      <span className="palette-icon">{def.icon}</span>
      <span className="palette-label">{def.label}</span>
    </div>
  )
}

export default function Palette() {
  return (
    <div className="palette">
      <div className="ed-side-title">Blocks</div>
      <div className="palette-grid">
        {PALETTE_TYPES.map(type => <PaletteItem key={type} type={type} />)}
      </div>
    </div>
  )
}
