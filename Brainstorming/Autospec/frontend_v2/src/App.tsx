import { ErrorBoundary } from "./components/ErrorBoundary";
import { ProjectView } from "./components/ProjectView";
import { ProjectsPage } from "./components/ProjectsPage";
import { navigate, routeHash, useHashRoute } from "./route";

export default function App() {
  const route = useHashRoute();
  return (
    <div className="app">
      <header className="topbar">
        <a href="#/" className="brand">
          Autospec <span>v2</span>
        </a>
        <span className="tagline">de la spécification au code vérifié</span>
      </header>
      <main className="content">
        {/* Keyed by the route: leaving a page that crashed clears the error. */}
        <ErrorBoundary key={routeHash(route)}>
          {route.name === "project" ? (
            <ProjectView projectId={route.id} onDeleted={() => navigate({ name: "list" })} />
          ) : (
            <ProjectsPage onCreated={(project) => navigate({ name: "project", id: project.id })} />
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
