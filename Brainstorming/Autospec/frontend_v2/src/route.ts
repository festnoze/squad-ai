// Hash routing: "#/" is the project list, "#/projects/<id>" a project view.
import { useEffect, useState } from "react";

export type Route = { name: "list" } | { name: "project"; id: string };

/**
 * The server's rule for project ids. It also rejects "." and "..", which the URL parser
 * would collapse (`/projects/..` is `/api/v2/`), so a crafted hash cannot reach another route.
 */
export const PROJECT_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;

export function parseHash(hash: string): Route {
  const match = /^#\/projects\/([^/]+)\/?$/.exec(hash);
  if (!match) return { name: "list" };
  let id: string;
  try {
    id = decodeURIComponent(match[1]);
  } catch {
    return { name: "list" };
  }
  return PROJECT_ID.test(id) ? { name: "project", id } : { name: "list" };
}

export function routeHash(route: Route): string {
  return route.name === "project" ? `#/projects/${encodeURIComponent(route.id)}` : "#/";
}

export function navigate(route: Route): void {
  window.location.hash = routeHash(route);
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
