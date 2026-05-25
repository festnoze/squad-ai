// Types for Chat messages and scoping items returned by the backend.

export type ChatMessageRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string; // UUID
  project_id: string; // UUID
  role: ChatMessageRole;
  content: string;
  meta_data: Record<string, unknown> | null;
  created_at: string; // ISO datetime
}

export type ItemType = 'epic' | 'user_story' | 'task';
export type ItemComplexity = 'simple' | 'medium' | 'complex';
export type ItemStatus =
  | 'todo'
  | 'in_progress'
  | 'in_test'
  | 'done'
  | 'proposed'
  | 'blocked';

export interface Item {
  id: string;
  project_id: string;
  parent_id: string | null;
  type: ItemType;
  title: string;
  description: string | null;
  complexity: ItemComplexity | null;
  status: ItemStatus;
  acceptance_criteria: string[] | null;
  order: number;
  // V1 fields: populated when an agent has produced something for the
  // item. null until then.
  deliverable_paths: string[] | null;
  deliverable_notes: string | null;
  blocked_reason: string | null;
  created_at: string;
  updated_at: string | null;
}

export type ScopingAction = 'propose_items' | 'ask_question' | 'confirm';

export interface SendMessageRequest {
  content: string;
}

export interface SendMessageResponse {
  message: ChatMessage;
  items_created: Item[];
  items_updated: Item[];
  action: ScopingAction;
}
