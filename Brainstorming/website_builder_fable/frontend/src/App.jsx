// OWNED BY: scaffold (infrastructure). Module agents READ this file, never edit it.
// Feature pages are default exports at the paths below (see docs/CONTRACTS.md).
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import ProjectsPage from './features/projects/ProjectsPage.jsx'
import EditorPage from './features/editor/EditorPage.jsx'
import CmsPage from './features/cms/CmsPage.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/projects/:projectId/editor/:pageId?" element={<EditorPage />} />
        <Route path="/projects/:projectId/cms/*" element={<CmsPage />} />
      </Routes>
    </BrowserRouter>
  )
}
