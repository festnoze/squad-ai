/**
 * Sessions API — create, list, stats, pause-penalty.
 */

import client from './client';

export const createSession = async (sessionData) => {
  const response = await client.post('/api/sessions', sessionData);
  return response.data;
};

export const getSessions = async (params = {}) => {
  const response = await client.get('/api/sessions', { params });
  return response.data;
};

export const getSessionStats = async (params = {}) => {
  const response = await client.get('/api/sessions/stats', { params });
  return response.data;
};

export const pausePenalty = async () => {
  const response = await client.post('/api/sessions/pause-penalty');
  return response.data;
};

export default { createSession, getSessions, getSessionStats, pausePenalty };
