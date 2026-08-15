// OWNED BY: frontend-editor agent.
// DndContext wiring: sensors, drag state for the overlay chip, and drop
// resolution per docs/decisions-editor.md section 3.4.

import { useState } from 'react'
import { PointerSensor, useSensor, useSensors, closestCenter } from '@dnd-kit/core'
import { useEditorStore } from './editorStore.js'
import { canDrop, createDefault } from './blockDefinitions.js'
import { findNode, findParent, isDescendant } from './treeUtils.js'

export function useEditorDnd() {
  const [activeDrag, setActiveDrag] = useState(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )

  function onDragStart(event) {
    const data = event.active.data.current
    if (!data) return
    if (data.kind === 'palette') {
      setActiveDrag({ kind: 'palette', type: data.blockType })
    } else {
      setActiveDrag({ kind: 'canvas', type: data.type, nodeId: data.nodeId })
    }
  }

  function onDragCancel() {
    setActiveDrag(null)
  }

  function onDragEnd(event) {
    setActiveDrag(null)
    const { active, over } = event
    if (!over) return
    const aData = active.data.current
    if (!aData) return

    const store = useEditorStore.getState()
    const tree = store.tree
    const dragType = aData.kind === 'palette' ? aData.blockType : aData.type

    // Resolve the target (parentId, index) from what we are over.
    let parentId = null
    let index = 0
    const oData = over.data.current
    if (oData && oData.kind === 'container') {
      const container = findNode(tree, oData.nodeId)
      if (!container) return
      parentId = container.id
      index = container.children.length
    } else {
      // Over a sortable canvas block: target its parent at its index.
      const overNode = findNode(tree, over.id)
      if (!overNode) return
      const parent = findParent(tree, over.id)
      if (!parent) return
      parentId = parent.id
      index = parent.children.findIndex(c => c.id === over.id)
    }

    const parentNode = findNode(tree, parentId)
    if (!parentNode || !canDrop(parentNode.type, dragType)) return

    if (aData.kind === 'palette') {
      const node = createDefault(aData.blockType)
      store.insertBlock(parentId, index, node)
      store.select(node.id)
      return
    }

    const dragId = aData.nodeId
    if (!dragId || dragId === over.id) return
    // Guard: never drop a node into itself or one of its descendants.
    if (isDescendant(tree, dragId, parentId)) return
    store.moveBlock(dragId, parentId, index)
  }

  return {
    sensors,
    collisionDetection: closestCenter,
    activeDrag,
    onDragStart,
    onDragEnd,
    onDragCancel,
  }
}
