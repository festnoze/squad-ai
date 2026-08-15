// OWNED BY: frontend-editor agent.
// Pages list in the left sidebar: open, create, rename (inline), duplicate,
// delete, set home. All persistence goes through callbacks owned by EditorPage.

import { useState } from 'react'

export default function PagesSidebar({
  pages, currentPageId,
  onOpen, onCreate, onRename, onDuplicate, onDelete, onSetHome,
}) {
  const [newName, setNewName] = useState('')
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  function submitCreate(e) {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setNewName('')
    onCreate(name)
  }

  function startRename(page) {
    setRenamingId(page.id)
    setRenameValue(page.name)
  }

  function submitRename(e) {
    e.preventDefault()
    const name = renameValue.trim()
    if (name) onRename(renamingId, name)
    setRenamingId(null)
  }

  return (
    <div className="pages-sidebar">
      <div className="ed-side-title">Pages</div>
      {pages === null ? (
        <div className="muted pages-note">Loading...</div>
      ) : pages.length === 0 ? (
        <div className="muted pages-note">No pages yet.</div>
      ) : (
        <ul className="pages-list">
          {pages.map(page => (
            <li
              key={page.id}
              className={'pages-item' + (String(page.id) === String(currentPageId) ? ' pages-item-current' : '')}
            >
              {renamingId === page.id ? (
                <form onSubmit={submitRename} className="pages-rename">
                  <input
                    className="input"
                    value={renameValue}
                    autoFocus
                    onChange={e => setRenameValue(e.target.value)}
                    onBlur={submitRename}
                    onKeyDown={e => { if (e.key === 'Escape') setRenamingId(null) }}
                  />
                </form>
              ) : (
                <>
                  <button type="button" className="pages-name" onClick={() => onOpen(page)} title={page.slug}>
                    {page.is_home ? <span className="pages-home" title="Home page">★ </span> : null}
                    {page.name}
                  </button>
                  <span className="pages-actions">
                    <button type="button" className="pages-act" title="Rename" onClick={() => startRename(page)}>✎</button>
                    <button type="button" className="pages-act" title="Duplicate" onClick={() => onDuplicate(page)}>⧉</button>
                    {!page.is_home && (
                      <button type="button" className="pages-act" title="Set as home page" onClick={() => onSetHome(page)}>★</button>
                    )}
                    <button type="button" className="pages-act pages-act-danger" title="Delete" onClick={() => onDelete(page)}>✕</button>
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submitCreate} className="pages-create">
        <input
          className="input"
          placeholder="New page name"
          value={newName}
          onChange={e => setNewName(e.target.value)}
        />
        <button type="submit" className="btn btn-sm btn-primary" disabled={!newName.trim()}>Add</button>
      </form>
    </div>
  )
}
