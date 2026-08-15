// OWNED BY: frontend-editor agent.
// WYSIWYG editor page. 3-pane layout: left (palette + pages), center (top bar,
// breadcrumb, canvas), right (properties panel). One DndContext wraps palette
// and canvas. Keyboard shortcuts and autosave flushing live here.

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DndContext, DragOverlay } from '@dnd-kit/core'
import { apiGet, apiPost, apiPut, apiDelete } from '../../api/client.js'
import { useEditorStore } from './editorStore.js'
import { useEditorDnd } from './useEditorDnd.js'
import { BLOCK_DEFINITIONS } from './blockDefinitions.js'
import Palette from './Palette.jsx'
import PagesSidebar from './PagesSidebar.jsx'
import Canvas from './Canvas.jsx'
import Breadcrumb from './Breadcrumb.jsx'
import PropertiesPanel from './PropertiesPanel.jsx'
import './editor.css'

const DEVICES = ['desktop', 'tablet', 'mobile']

export default function EditorPage() {
  const { projectId, pageId } = useParams()
  const navigate = useNavigate()
  const [pages, setPages] = useState(null)
  const dnd = useEditorDnd()

  const pastCount = useEditorStore(s => s.past.length)
  const futureCount = useEditorStore(s => s.future.length)
  const undo = useEditorStore(s => s.undo)
  const redo = useEditorStore(s => s.redo)
  const device = useEditorStore(s => s.device)
  const setDevice = useEditorStore(s => s.setDevice)
  const dirty = useEditorStore(s => s.dirty)
  const saving = useEditorStore(s => s.saving)
  const saveError = useEditorStore(s => s.saveError)

  const refreshPages = useCallback(async () => {
    const list = await apiGet(`/api/projects/${projectId}/pages`)
    setPages(list || [])
    return list || []
  }, [projectId])

  useEffect(() => {
    refreshPages().catch(() => setPages([]))
  }, [refreshPages])

  // No page in the URL: open the home page (or first page) once known.
  useEffect(() => {
    if (!pageId && pages && pages.length) {
      const home = pages.find(p => p.is_home) || pages[0]
      navigate(`/projects/${projectId}/editor/${home.id}`, { replace: true })
    }
  }, [pageId, pages, projectId, navigate])

  // Load the page block tree into the store.
  useEffect(() => {
    if (projectId && pageId) {
      useEditorStore.getState().loadPage(projectId, pageId).catch(() => {})
    }
  }, [projectId, pageId])

  // Global keyboard shortcuts (ignored while typing in a form control).
  useEffect(() => {
    function onKeyDown(e) {
      const el = document.activeElement
      if (
        el &&
        (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
      ) {
        return
      }
      const s = useEditorStore.getState()
      if (e.key === 'Escape') {
        s.select(null)
        return
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && s.selectedId) {
        e.preventDefault()
        s.removeBlock(s.selectedId)
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd' && s.selectedId) {
        e.preventDefault()
        s.duplicateBlock(s.selectedId)
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) s.redo()
        else s.undo()
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault()
        s.redo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Flush pending changes on tab close and on unmount.
  useEffect(() => {
    function flush() {
      const s = useEditorStore.getState()
      if (s.dirty) s.savePage()
    }
    window.addEventListener('beforeunload', flush)
    return () => {
      window.removeEventListener('beforeunload', flush)
      flush()
    }
  }, [])

  /* ---- pages sidebar operations ---- */

  async function handleCreate(name) {
    try {
      const page = await apiPost(`/api/projects/${projectId}/pages`, { name })
      await refreshPages()
      navigate(`/projects/${projectId}/editor/${page.id}`)
    } catch (err) {
      window.alert('Could not create page: ' + (err.message || 'unknown error'))
    }
  }

  async function handleRename(id, name) {
    try {
      await apiPut(`/api/projects/${projectId}/pages/${id}`, { name })
      await refreshPages()
    } catch (err) {
      window.alert('Could not rename page: ' + (err.message || 'unknown error'))
    }
  }

  async function handleDuplicate(page) {
    try {
      const copy = await apiPost(`/api/projects/${projectId}/pages/${page.id}/duplicate`)
      await refreshPages()
      navigate(`/projects/${projectId}/editor/${copy.id}`)
    } catch (err) {
      window.alert('Could not duplicate page: ' + (err.message || 'unknown error'))
    }
  }

  async function handleDelete(page) {
    if (!window.confirm(`Delete page "${page.name}"? This cannot be undone.`)) return
    try {
      await apiDelete(`/api/projects/${projectId}/pages/${page.id}`)
      const list = await refreshPages()
      if (String(page.id) === String(pageId)) {
        const next = list.find(p => p.is_home) || list[0]
        navigate(next ? `/projects/${projectId}/editor/${next.id}` : `/projects/${projectId}/editor`, { replace: true })
      }
    } catch (err) {
      window.alert('Could not delete page: ' + (err.message || 'unknown error'))
    }
  }

  async function handleSetHome(page) {
    try {
      await apiPut(`/api/projects/${projectId}/pages/${page.id}`, { is_home: true })
      await refreshPages()
    } catch (err) {
      window.alert('Could not set home page: ' + (err.message || 'unknown error'))
    }
  }

  const saveState = saving
    ? { text: 'Saving...', cls: 'save-busy' }
    : saveError
      ? { text: 'Save failed - retrying on next change', cls: 'save-error' }
      : dirty
        ? { text: 'Unsaved changes', cls: 'save-dirty' }
        : { text: 'Saved', cls: 'save-ok' }

  const dragDef = dnd.activeDrag ? BLOCK_DEFINITIONS[dnd.activeDrag.type] : null

  return (
    <div className="ed-root">
      <DndContext
        sensors={dnd.sensors}
        collisionDetection={dnd.collisionDetection}
        onDragStart={dnd.onDragStart}
        onDragEnd={dnd.onDragEnd}
        onDragCancel={dnd.onDragCancel}
      >
        <aside className="ed-left">
          <div className="ed-left-header">
            <Link to="/" className="ed-back">&larr; Projects</Link>
          </div>
          <Palette />
          <PagesSidebar
            pages={pages}
            currentPageId={pageId}
            onOpen={p => navigate(`/projects/${projectId}/editor/${p.id}`)}
            onCreate={handleCreate}
            onRename={handleRename}
            onDuplicate={handleDuplicate}
            onDelete={handleDelete}
            onSetHome={handleSetHome}
          />
        </aside>

        <main className="ed-center">
          <div className="ed-toolbar">
            <select
              className="select ed-page-select"
              value={pageId || ''}
              onChange={e => navigate(`/projects/${projectId}/editor/${e.target.value}`)}
              title="Current page"
            >
              {(pages || []).map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_home ? ' (home)' : ''}
                </option>
              ))}
            </select>

            <div className="ed-toolbar-group">
              {DEVICES.map(d => (
                <button
                  key={d}
                  type="button"
                  className={'btn btn-sm' + (device === d ? ' align-active' : '')}
                  onClick={() => setDevice(d)}
                >
                  {d[0].toUpperCase() + d.slice(1)}
                </button>
              ))}
            </div>

            <div className="ed-toolbar-group">
              <button type="button" className="btn btn-sm" disabled={pastCount === 0} title="Undo (Ctrl+Z)" onClick={undo}>
                ↶ Undo
              </button>
              <button type="button" className="btn btn-sm" disabled={futureCount === 0} title="Redo (Ctrl+Shift+Z)" onClick={redo}>
                ↷ Redo
              </button>
            </div>

            <span className={'ed-save-indicator ' + saveState.cls}>{saveState.text}</span>
          </div>

          <Breadcrumb />

          {pageId ? (
            <Canvas />
          ) : (
            <div className="ed-canvas">
              <div className="empty-state">
                {pages && pages.length === 0
                  ? 'No pages yet. Create one from the sidebar.'
                  : 'Loading...'}
              </div>
            </div>
          )}
        </main>

        <aside className="ed-right">
          <PropertiesPanel />
        </aside>

        <DragOverlay dropAnimation={null}>
          {dragDef ? (
            <div className="drag-chip">
              <span className="palette-icon">{dragDef.icon}</span>
              <span>{dragDef.label}</span>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  )
}
