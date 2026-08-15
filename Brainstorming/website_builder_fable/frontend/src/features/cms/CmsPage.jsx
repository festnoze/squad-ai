// OWNED BY: frontend-cms agent (src/features/cms/**).
// CMS shell mounted at /projects/:projectId/cms/* (App.jsx wildcard route,
// docs/CONTRACTS.md section 5). Left sidebar lists the project's collections
// plus an Assets item; the main area renders the selected screen through
// nested routes (paths relative to the mount point).

import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useParams } from 'react-router-dom'
import { getProject, listCollections } from './cmsApi.js'
import CollectionsScreen from './CollectionsScreen.jsx'
import SchemaScreen from './SchemaScreen.jsx'
import EntriesScreen from './EntriesScreen.jsx'
import EntryFormScreen from './EntryFormScreen.jsx'
import AssetsScreen from './AssetsScreen.jsx'
import './cms.css'

export default function CmsPage() {
  const { projectId } = useParams()
  const [project, setProject] = useState(null)
  const [collections, setCollections] = useState(null)
  const [error, setError] = useState(null)

  const reloadCollections = useCallback(async () => {
    try {
      const items = await listCollections(projectId)
      setCollections(items)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    setProject(null)
    setCollections(null)
    getProject(projectId)
      .then((data) => {
        if (!cancelled) setProject(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    listCollections(projectId)
      .then((items) => {
        if (!cancelled) setCollections(items)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const cmsBase = `/projects/${projectId}/cms`

  return (
    <div className="cms-layout">
      <aside className="cms-sidebar">
        <div>
          <Link to="/" className="muted" style={{ fontSize: 13 }}>
            &larr; Projects
          </Link>
        </div>
        <div style={{ fontWeight: 700, marginTop: 4 }}>
          {project ? project.name : `Project ${projectId}`}
        </div>
        <NavLink
          to={cmsBase}
          end
          className={({ isActive }) => `cms-sidebar-link${isActive ? ' active' : ''}`}
        >
          All collections
        </NavLink>

        <div className="cms-sidebar-title">Collections</div>
        {collections === null && <div className="muted" style={{ fontSize: 13 }}>Loading...</div>}
        {collections !== null && collections.length === 0 && (
          <div className="muted" style={{ fontSize: 13 }}>None yet</div>
        )}
        {collections !== null &&
          collections.map((collection) => (
            <NavLink
              key={collection.id}
              to={`${cmsBase}/collections/${collection.id}/entries`}
              className={({ isActive }) => `cms-sidebar-link${isActive ? ' active' : ''}`}
            >
              {collection.name}
            </NavLink>
          ))}

        <div className="cms-sidebar-title">Library</div>
        <NavLink
          to={`${cmsBase}/assets`}
          className={({ isActive }) => `cms-sidebar-link${isActive ? ' active' : ''}`}
        >
          Assets
        </NavLink>
      </aside>

      <main className="cms-main">
        <div className="cms-breadcrumb">
          <Link to="/">{project ? project.name : `Project ${projectId}`}</Link>
          {' > '}
          <Link to={cmsBase}>CMS</Link>
        </div>
        {error && <div className="cms-error">{error}</div>}
        <Routes>
          <Route
            index
            element={
              <CollectionsScreen
                projectId={projectId}
                collections={collections}
                reloadCollections={reloadCollections}
              />
            }
          />
          <Route
            path="collections/:collectionId/schema"
            element={<SchemaScreen projectId={projectId} reloadCollections={reloadCollections} />}
          />
          <Route
            path="collections/:collectionId/entries"
            element={<EntriesScreen projectId={projectId} />}
          />
          <Route
            path="collections/:collectionId/entries/new"
            element={<EntryFormScreen projectId={projectId} />}
          />
          <Route
            path="collections/:collectionId/entries/:entryId"
            element={<EntryFormScreen projectId={projectId} />}
          />
          <Route path="assets" element={<AssetsScreen projectId={projectId} />} />
          <Route
            path="*"
            element={<div className="empty-state">Screen not found.</div>}
          />
        </Routes>
      </main>
    </div>
  )
}
