/**
 * Profile API — XP, level, streak, settings.
 */

import client from './client';

export const getProfile = async () => {
  const response = await client.get('/api/profile');
  return response.data;
};

export const updateSettings = async (settings) => {
  const response = await client.put('/api/profile/settings', settings);
  return response.data;
};

export default { getProfile, updateSettings };
