// API calls for the V1 /projects/{id}/runs endpoints.

import { apiGet, apiPost } from './client';
import type { ProjectRun, ProjectRunDetail } from '../types/project_run';

// POST → starts a new run (202 Accepted). The backend refuses with 409
// if one is already running for the project.
export function startProjectRun(projectId: string): Promise<ProjectRun> {
  return apiPost<ProjectRun>(`/projects/${projectId}/runs`, {});
}

// GET → returns the most recent run for the project (with its steps).
// The caller must handle 404 (no run has ever been started).
export function getCurrentProjectRun(
  projectId: string,
): Promise<ProjectRunDetail> {
  return apiGet<ProjectRunDetail>(`/projects/${projectId}/runs/current`);
}
