// OWNED BY: frontend-editor agent.
// Zustand editor store. Shape and action names follow docs/CONTRACTS.md section 3
// exactly (plus one UI-only flag, saveError, driving the red toolbar note asked
// for by decisions-editor.md 4.3). Autosave: debounced 1500 ms PUT {"content": tree}.
// History: snapshot stacks capped at 50; prop/style edits coalesced within 800 ms.

import { create } from 'zustand'
import { apiGet, apiPut } from '../../api/client.js'
import {
  findNode, findParent, findPath, insertNode, removeNode,
  moveNode, updateNode, cloneWithNewIds,
} from './treeUtils.js'

export const DEVICE_WIDTHS = { desktop: 1200, tablet: 768, mobile: 375 }

export function emptyRoot() {
  return { id: 'root', type: 'page', props: {}, style: {}, children: [] }
}

// Module-level autosave debounce + history coalescing marker.
let saveTimer = null
let lastPush = { key: null, at: 0 }

function scheduleAutosave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    useEditorStore.getState().savePage()
  }, 1500)
}

export const useEditorStore = create((set, get) => {
  // Structural commits: push one undo snapshot, clear redo, mark dirty.
  function commit(nextTree) {
    set(s => ({
      tree: nextTree,
      past: [...s.past.slice(-49), s.tree],
      future: [],
      dirty: true,
    }))
    lastPush = { key: null, at: 0 }
    scheduleAutosave()
  }

  // Prop/style commits from continuous inputs: coalesce history pushes so a
  // color drag or typing burst produces one snapshot per 800 ms window.
  function commitCoalesced(nextTree, key) {
    const now = Date.now()
    if (lastPush.key === key && now - lastPush.at < 800) {
      set({ tree: nextTree, future: [], dirty: true })
    } else {
      set(s => ({
        tree: nextTree,
        past: [...s.past.slice(-49), s.tree],
        future: [],
        dirty: true,
      }))
      lastPush = { key, at: now }
    }
    scheduleAutosave()
  }

  return {
    // data
    projectId: null,
    pageId: null,
    tree: emptyRoot(),
    selectedId: null,
    // history
    past: [],
    future: [],
    // persistence
    dirty: false,
    saving: false,
    saveError: false,
    lastSavedAt: null,
    // ui
    device: 'desktop',

    async loadPage(projectId, pageId) {
      // Best-effort flush of the page we are leaving.
      const prev = get()
      if (prev.dirty && prev.projectId && prev.pageId && String(prev.pageId) !== String(pageId)) {
        apiPut(`/api/projects/${prev.projectId}/pages/${prev.pageId}`, { content: prev.tree }).catch(() => {})
      }
      if (saveTimer) {
        clearTimeout(saveTimer)
        saveTimer = null
      }
      lastPush = { key: null, at: 0 }
      set({
        projectId, pageId,
        tree: emptyRoot(), selectedId: null,
        past: [], future: [],
        dirty: false, saving: false, saveError: false, lastSavedAt: null,
      })
      const page = await apiGet(`/api/projects/${projectId}/pages/${pageId}`)
      if (String(get().pageId) !== String(pageId)) return
      const content =
        page && page.content && page.content.type === 'page' && Array.isArray(page.content.children)
          ? page.content
          : emptyRoot()
      set({ tree: content, lastSavedAt: page.updated_at || null })
    },

    select(id) {
      set({ selectedId: id })
    },

    insertBlock(parentId, index, node) {
      if (!node) return
      const next = insertNode(get().tree, parentId, index, node)
      if (next === get().tree) return
      commit(next)
    },

    removeBlock(id) {
      if (!id || id === 'root') return
      const s = get()
      const next = removeNode(s.tree, id)
      if (next === s.tree) return
      commit(next)
      const sel = get().selectedId
      if (sel && !findNode(next, sel)) set({ selectedId: null })
    },

    moveBlock(id, newParentId, newIndex) {
      const next = moveNode(get().tree, id, newParentId, newIndex)
      if (next === get().tree) return
      commit(next)
    },

    duplicateBlock(id) {
      if (!id || id === 'root') return
      const s = get()
      const node = findNode(s.tree, id)
      const parent = findParent(s.tree, id)
      if (!node || !parent) return
      const index = parent.children.findIndex(c => c.id === id)
      const clone = cloneWithNewIds(node)
      commit(insertNode(s.tree, parent.id, index + 1, clone))
      set({ selectedId: clone.id })
    },

    updateBlockProps(id, patch) {
      const s = get()
      const node = findNode(s.tree, id)
      if (!node) return
      const next = updateNode(s.tree, id, { props: { ...node.props, ...patch } })
      commitCoalesced(next, id + '|props|' + Object.keys(patch)[0])
    },

    updateBlockStyle(id, patch) {
      const s = get()
      const node = findNode(s.tree, id)
      if (!node) return
      const next = updateNode(s.tree, id, { style: { ...node.style, ...patch } })
      commitCoalesced(next, id + '|style|' + Object.keys(patch)[0])
    },

    undo() {
      const s = get()
      if (!s.past.length) return
      const prevTree = s.past[s.past.length - 1]
      set({
        tree: prevTree,
        past: s.past.slice(0, -1),
        future: [s.tree, ...s.future],
        dirty: true,
        selectedId: s.selectedId && findNode(prevTree, s.selectedId) ? s.selectedId : null,
      })
      lastPush = { key: null, at: 0 }
      scheduleAutosave()
    },

    redo() {
      const s = get()
      if (!s.future.length) return
      const nextTree = s.future[0]
      set({
        tree: nextTree,
        past: [...s.past.slice(-49), s.tree],
        future: s.future.slice(1),
        dirty: true,
        selectedId: s.selectedId && findNode(nextTree, s.selectedId) ? s.selectedId : null,
      })
      lastPush = { key: null, at: 0 }
      scheduleAutosave()
    },

    setDevice(d) {
      set({ device: d })
    },

    async savePage() {
      const s = get()
      if (!s.dirty || s.saving || !s.projectId || !s.pageId) return
      set({ saving: true })
      const treeAtSave = s.tree
      try {
        await apiPut(`/api/projects/${s.projectId}/pages/${s.pageId}`, { content: treeAtSave })
        set({
          saving: false,
          saveError: false,
          dirty: get().tree !== treeAtSave,
          lastSavedAt: new Date().toISOString(),
        })
        if (get().dirty) scheduleAutosave()
      } catch (err) {
        // Keep dirty; the next mutation reschedules the autosave (retry).
        set({ saving: false, saveError: true })
      }
    },

    markSaved() {
      set({ dirty: false, saving: false, saveError: false, lastSavedAt: new Date().toISOString() })
    },
  }
})

// Convenience re-export for components that need path lookups with the store tree.
export { findPath }
