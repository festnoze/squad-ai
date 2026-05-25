// Types for the V1 /api/projects/{id}/runs endpoints.

export type ProjectRunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed';

export type ProjectRunStepRole = 'orchestrator' | 'dev' | 'qa';

export type ProjectRunStepStatus =
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'rejected';

export interface ProjectRun {
  id: string;
  project_id: string;
  status: ProjectRunStatus;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  total_tasks: number;
  done_tasks: number;
  blocked_tasks: number;
  created_at: string;
  updated_at: string | null;
}

export interface ProjectRunStep {
  id: string;
  run_id: string;
  item_id: string | null;
  role: ProjectRunStepRole;
  status: ProjectRunStepStatus;
  iteration: number;
  summary: string;
  detail: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ProjectRunDetail {
  run: ProjectRun;
  steps: ProjectRunStep[];
}
