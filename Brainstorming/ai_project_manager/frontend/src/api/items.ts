// API calls for the /items resource (Epic 3).
// Paths are relative; the client wrapper prefixes them with /api.

import { apiGet } from './client';
import type { Item, ItemType } from '../types/chat';

export function listProjectItems(
  projectId: string,
  typeFilter?: ItemType,
): Promise<Item[]> {
  const qs = typeFilter ? `?type=${typeFilter}` : '';
  return apiGet<Item[]>(`/projects/${projectId}/items${qs}`);
}

export function getItem(itemId: string): Promise<Item> {
  return apiGet<Item>(`/items/${itemId}`);
}
