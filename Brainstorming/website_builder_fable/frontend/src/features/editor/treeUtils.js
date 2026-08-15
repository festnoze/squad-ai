// OWNED BY: frontend-editor agent.
// Pure tree operations over the block tree. Every mutating helper returns a
// NEW tree (structural sharing on untouched branches); nothing is mutated.

import { nanoid } from 'nanoid'

export function findNode(tree, id) {
  if (!tree || !id) return null
  if (tree.id === id) return tree
  for (const child of tree.children || []) {
    const found = findNode(child, id)
    if (found) return found
  }
  return null
}

export function findParent(tree, id, parent = null) {
  if (!tree || !id) return null
  if (tree.id === id) return parent
  for (const child of tree.children || []) {
    const found = findParent(child, id, tree)
    if (found) return found
  }
  return null
}

// Nodes from root to the target (inclusive); [] when not found.
export function findPath(tree, id) {
  if (!tree || !id) return []
  if (tree.id === id) return [tree]
  for (const child of tree.children || []) {
    const path = findPath(child, id)
    if (path.length) return [tree, ...path]
  }
  return []
}

export function insertNode(tree, parentId, index, node) {
  if (tree.id === parentId) {
    const children = [...tree.children]
    const at = Math.max(0, Math.min(index, children.length))
    children.splice(at, 0, node)
    return { ...tree, children }
  }
  let changed = false
  const children = tree.children.map(child => {
    const next = insertNode(child, parentId, index, node)
    if (next !== child) changed = true
    return next
  })
  return changed ? { ...tree, children } : tree
}

export function removeNode(tree, id) {
  let changed = false
  const children = []
  for (const child of tree.children) {
    if (child.id === id) {
      changed = true
      continue
    }
    const next = removeNode(child, id)
    if (next !== child) changed = true
    children.push(next)
  }
  return changed ? { ...tree, children } : tree
}

// Shallow patch of node fields (e.g. { props: {...} } or { children: [...] }).
export function updateNode(tree, id, patch) {
  if (tree.id === id) return { ...tree, ...patch }
  let changed = false
  const children = tree.children.map(child => {
    const next = updateNode(child, id, patch)
    if (next !== child) changed = true
    return next
  })
  return changed ? { ...tree, children } : tree
}

function arrayMove(arr, from, to) {
  const copy = [...arr]
  const [item] = copy.splice(from, 1)
  copy.splice(to, 0, item)
  return copy
}

export function moveNode(tree, id, newParentId, newIndex) {
  if (id === 'root') return tree
  const node = findNode(tree, id)
  const parent = findParent(tree, id)
  if (!node || !parent) return tree
  if (parent.id === newParentId) {
    const oldIndex = parent.children.findIndex(c => c.id === id)
    const target = Math.max(0, Math.min(newIndex, parent.children.length - 1))
    if (oldIndex === target) return tree
    return updateNode(tree, parent.id, { children: arrayMove(parent.children, oldIndex, target) })
  }
  // Never move a node into itself or its own subtree.
  if (isDescendant(tree, id, newParentId)) return tree
  const without = removeNode(tree, id)
  return insertNode(without, newParentId, newIndex, node)
}

export function cloneWithNewIds(node) {
  return {
    ...node,
    id: nanoid(10),
    props: JSON.parse(JSON.stringify(node.props || {})),
    style: { ...(node.style || {}) },
    children: (node.children || []).map(cloneWithNewIds),
  }
}

// True when otherId is ancestorId itself or lives inside its subtree.
export function isDescendant(tree, ancestorId, otherId) {
  const ancestor = findNode(tree, ancestorId)
  if (!ancestor) return false
  return !!findNode(ancestor, otherId)
}
