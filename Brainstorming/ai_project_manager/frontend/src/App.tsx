import { Routes, Route } from 'react-router-dom';
import ProjectList from './pages/ProjectList';
import ProjectView from './pages/ProjectView';

function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectList />} />
      <Route path="/projects/:id" element={<ProjectView />} />
    </Routes>
  );
}

export default App;
