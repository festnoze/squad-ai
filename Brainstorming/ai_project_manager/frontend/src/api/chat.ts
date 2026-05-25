// API calls for chat messages (Epic 2).
// Paths are relative; the client wrapper prefixes them with /api.

import { apiGet, apiPost } from './client';
import type {
  ChatMessage,
  SendMessageRequest,
  SendMessageResponse,
} from '../types/chat';

export function listMessages(projectId: string): Promise<ChatMessage[]> {
  return apiGet<ChatMessage[]>(`/projects/${projectId}/messages`);
}

export function sendMessage(
  projectId: string,
  payload: SendMessageRequest,
): Promise<SendMessageResponse> {
  return apiPost<SendMessageResponse>(
    `/projects/${projectId}/messages`,
    payload,
  );
}
