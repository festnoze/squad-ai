// API calls for the /projects resource.
// Paths are relative; the client wrapper prefixes them with /api.

import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import type {
  Project,
  CreateProjectPayload,
  UpdateProjectPayload,
} from '../types/project';

export function listProjects(): Promise<Project[]> {
  return apiGet<Project[]>('/projects');
}

export function createProject(
  payload: CreateProjectPayload,
): Promise<Project> {
  return apiPost<Project>('/projects', payload);
}

export function updateProject(
  id: string,
  payload: UpdateProjectPayload,
): Promise<Project> {
  return apiPatch<Project>(`/projects/${id}`, payload);
}

export function deleteProject(id: string): Promise<void> {
  return apiDelete(`/projects/${id}`);
}
