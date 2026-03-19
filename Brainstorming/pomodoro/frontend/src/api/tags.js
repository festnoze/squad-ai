/**
 * Tags API — list and create tags.
 */

import client from './client';

export const getTags = async () => {
  const response = await client.get('/api/tags');
  return response.data;
};

export const createTag = async (name, color) => {
  const response = await client.post('/api/tags', { name, color });
  return response.data;
};

export default { getTags, createTag };
