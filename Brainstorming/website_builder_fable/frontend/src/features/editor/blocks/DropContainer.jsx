// OWNED BY: frontend-editor agent.
// Shared wrapper for container blocks: registers a droppable zone covering the
// container body (so empty containers accept drops) and a SortableContext over
// the children. Highlights itself while a compatible block hovers over it.

import { useDroppable } from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  horizontalListSortingStrategy,
} from '@dnd-kit/sortable'
import { canDrop } from '../blockDefinitions.js'

export default function DropContainer({ node, horizontal = false, style, className, children }) {
  const { setNodeRef, isOver, active } = useDroppable({
    id: 'container-' + node.id,
    data: { kind: 'container', nodeId: node.id, type: node.type },
  })

  const activeData = active ? active.data.current : null
  const dragType = activeData
    ? (activeData.kind === 'palette' ? activeData.blockType : activeData.type)
    : null
  const validTarget = dragType ? canDrop(node.type, dragType) : false

  const classes = [
    className || '',
    isOver && validTarget ? 'blk-drop-target' : '',
    node.children.length === 0 ? 'blk-empty' : '',
  ].filter(Boolean).join(' ')

  return (
    <SortableContext
      items={node.children.map(c => c.id)}
      strategy={horizontal ? horizontalListSortingStrategy : verticalListSortingStrategy}
    >
      <div ref={setNodeRef} className={classes} style={style}>
        {node.children.length === 0
          ? <div className="blk-placeholder">Drop blocks here</div>
          : children}
      </div>
    </SortableContext>
  )
}
