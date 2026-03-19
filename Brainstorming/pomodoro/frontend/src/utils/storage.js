/**
 * AsyncStorage helpers — JWT persistence and general KV store.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

const KEYS = {
  TOKEN: '@deepfocus_token',
  REALM: '@deepfocus_realm',
  SETTINGS: '@deepfocus_settings',
  PENDING_SESSIONS: '@deepfocus_pending_sessions',
};

export const storeToken = async (token) => {
  await AsyncStorage.setItem(KEYS.TOKEN, token);
};

export const getToken = async () => {
  return await AsyncStorage.getItem(KEYS.TOKEN);
};

export const removeToken = async () => {
  await AsyncStorage.removeItem(KEYS.TOKEN);
};

export const storeRealm = async (realmId) => {
  await AsyncStorage.setItem(KEYS.REALM, realmId);
};

export const getRealm = async () => {
  return await AsyncStorage.getItem(KEYS.REALM);
};

export const storeSettings = async (settings) => {
  await AsyncStorage.setItem(KEYS.SETTINGS, JSON.stringify(settings));
};

export const getSettings = async () => {
  const raw = await AsyncStorage.getItem(KEYS.SETTINGS);
  return raw ? JSON.parse(raw) : null;
};

// Offline-first: queue sessions to sync later
export const queueSession = async (session) => {
  const raw = await AsyncStorage.getItem(KEYS.PENDING_SESSIONS);
  const pending = raw ? JSON.parse(raw) : [];
  pending.push(session);
  await AsyncStorage.setItem(KEYS.PENDING_SESSIONS, JSON.stringify(pending));
};

export const getPendingSessions = async () => {
  const raw = await AsyncStorage.getItem(KEYS.PENDING_SESSIONS);
  return raw ? JSON.parse(raw) : [];
};

export const clearPendingSessions = async () => {
  await AsyncStorage.removeItem(KEYS.PENDING_SESSIONS);
};

export default {
  storeToken,
  getToken,
  removeToken,
  storeRealm,
  getRealm,
  storeSettings,
  getSettings,
  queueSession,
  getPendingSessions,
  clearPendingSessions,
};
