/**
 * Auth API — register, login, get current user.
 */

import client from './client';

export const register = async (email, password) => {
  const response = await client.post('/api/auth/register', { email, password });
  return response.data;
};

export const login = async (email, password) => {
  const response = await client.post('/api/auth/login', { email, password });
  return response.data;
};

export const getMe = async () => {
  const response = await client.get('/api/auth/me');
  return response.data;
};

export default { register, login, getMe };
