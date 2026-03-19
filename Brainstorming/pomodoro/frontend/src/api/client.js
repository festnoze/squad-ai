/**
 * Axios client with JWT interceptor.
 * All API calls flow through this single instance.
 */

import axios from 'axios';
import { getToken } from '../utils/storage';

// Change this to your backend URL
// Web: http://localhost:8000 | Android emulator: http://10.0.2.2:8000 | Phone: http://<your-ip>:8000
import { Platform } from 'react-native';
const API_BASE_URL = Platform.OS === 'web' ? 'http://localhost:8000' : 'http://10.0.2.2:8000';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT to every request
client.interceptors.request.use(
  async (config) => {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle 401 globally
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Token expired or invalid — auth context will handle logout
    }
    return Promise.reject(error);
  }
);

export default client;
