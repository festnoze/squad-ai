/**
 * AuthContext — JWT management, login/register/logout, auto-login from storage.
 */

import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { storeToken, getToken, removeToken } from '../utils/storage';
import * as authApi from '../api/auth';

const AuthContext = createContext(null);

const initialState = {
  user: null,
  token: null,
  isLoading: true,
  error: null,
};

const authReducer = (state, action) => {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'LOGIN_SUCCESS':
      return {
        ...state,
        user: action.payload.user,
        token: action.payload.token,
        isLoading: false,
        error: null,
      };
    case 'SET_USER':
      return { ...state, user: action.payload, isLoading: false };
    case 'LOGOUT':
      return { ...initialState, isLoading: false };
    case 'SET_ERROR':
      return { ...state, error: action.payload, isLoading: false };
    case 'CLEAR_ERROR':
      return { ...state, error: null };
    default:
      return state;
  }
};

export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // Auto-login on mount
  useEffect(() => {
    const tryAutoLogin = async () => {
      try {
        const token = await getToken();
        if (token) {
          const user = await authApi.getMe();
          dispatch({
            type: 'LOGIN_SUCCESS',
            payload: { user, token },
          });
        } else {
          dispatch({ type: 'SET_LOADING', payload: false });
        }
      } catch (err) {
        await removeToken();
        dispatch({ type: 'SET_LOADING', payload: false });
      }
    };
    tryAutoLogin();
  }, []);

  const login = async (email, password) => {
    try {
      dispatch({ type: 'SET_LOADING', payload: true });
      dispatch({ type: 'CLEAR_ERROR' });
      const data = await authApi.login(email, password);
      await storeToken(data.access_token);
      const user = await authApi.getMe();
      dispatch({
        type: 'LOGIN_SUCCESS',
        payload: { user, token: data.access_token },
      });
    } catch (err) {
      const message =
        err.response?.data?.detail || 'Login failed. Check your credentials.';
      dispatch({ type: 'SET_ERROR', payload: message });
      throw err;
    }
  };

  const register = async (email, password) => {
    try {
      dispatch({ type: 'SET_LOADING', payload: true });
      dispatch({ type: 'CLEAR_ERROR' });
      await authApi.register(email, password);
      // Auto-login after register
      await login(email, password);
    } catch (err) {
      const message =
        err.response?.data?.detail || 'Registration failed. Try again.';
      dispatch({ type: 'SET_ERROR', payload: message });
      throw err;
    }
  };

  const logout = async () => {
    await removeToken();
    dispatch({ type: 'LOGOUT' });
  };

  const refreshUser = async () => {
    try {
      const user = await authApi.getMe();
      dispatch({ type: 'SET_USER', payload: user });
    } catch (err) {
      // Silently fail
    }
  };

  const clearError = () => {
    dispatch({ type: 'CLEAR_ERROR' });
  };

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        register,
        logout,
        refreshUser,
        clearError,
        isAuthenticated: !!state.token,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;
