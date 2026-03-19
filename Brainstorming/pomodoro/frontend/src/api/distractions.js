/**
 * Distractions API — log and get stats.
 */

import client from './client';

export const logDistraction = async (data) => {
  const response = await client.post('/api/distractions', data);
  return response.data;
};

export const getDistractionStats = async (params = {}) => {
  const response = await client.get('/api/distractions/stats', { params });
  return response.data;
};

export default { logDistraction, getDistractionStats };
