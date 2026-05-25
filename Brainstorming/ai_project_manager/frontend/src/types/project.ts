// Types for Project entities returned by the backend.

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface CreateProjectPayload {
  name: string;
  description?: string;
}

export interface UpdateProjectPayload {
  name?: string;
  description?: string;
}
