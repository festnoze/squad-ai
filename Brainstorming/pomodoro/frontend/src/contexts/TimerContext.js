/**
 * TimerContext — The heart of the app.
 * State machine: IDLE -> FOCUSING -> BREAK -> FOCUSING -> ... -> LONG_BREAK
 * Manages countdown, session tracking, XP, and API sync.
 */

import React, {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useRef,
  useCallback,
} from 'react';
import { Vibration, AppState } from 'react-native';
import { createSession, pausePenalty } from '../api/sessions';
import { queueSession, getPendingSessions, clearPendingSessions } from '../utils/storage';
import { useAuth } from './AuthContext';

const TimerContext = createContext(null);

// Timer phases
export const PHASES = {
  IDLE: 'IDLE',
  FOCUSING: 'FOCUSING',
  SHORT_BREAK: 'SHORT_BREAK',
  LONG_BREAK: 'LONG_BREAK',
  RITUAL: 'RITUAL',
};

const initialState = {
  phase: PHASES.IDLE,
  secondsRemaining: 25 * 60,
  totalSeconds: 25 * 60,
  isRunning: false,
  sessionsCompleted: 0,
  currentTag: 'Work',
  intention: '',
  lastSessionId: null,
  settings: {
    focusDuration: 25,
    shortBreakDuration: 5,
    longBreakDuration: 15,
    sessionsBeforeLongBreak: 4,
    autoAdvance: false,
  },
  profile: null,
  sessionStartedAt: null,
};

const timerReducer = (state, action) => {
  switch (action.type) {
    case 'SET_SETTINGS':
      return { ...state, settings: { ...state.settings, ...action.payload } };
    case 'SET_PROFILE':
      return { ...state, profile: action.payload };
    case 'SET_TAG':
      return { ...state, currentTag: action.payload };
    case 'SET_INTENTION':
      return { ...state, intention: action.payload };
    case 'SET_LAST_SESSION_ID':
      return { ...state, lastSessionId: action.payload };
    case 'START_RITUAL': {
      return {
        ...state,
        phase: PHASES.RITUAL,
        isRunning: false,
      };
    }
    case 'START_FOCUS': {
      const totalSec = state.settings.focusDuration * 60;
      return {
        ...state,
        phase: PHASES.FOCUSING,
        secondsRemaining: totalSec,
        totalSeconds: totalSec,
        isRunning: true,
        sessionStartedAt: new Date().toISOString(),
      };
    }
    case 'START_SHORT_BREAK': {
      const totalSec = state.settings.shortBreakDuration * 60;
      return {
        ...state,
        phase: PHASES.SHORT_BREAK,
        secondsRemaining: totalSec,
        totalSeconds: totalSec,
        isRunning: true,
        sessionsCompleted: state.sessionsCompleted + 1,
      };
    }
    case 'START_LONG_BREAK': {
      const totalSec = state.settings.longBreakDuration * 60;
      return {
        ...state,
        phase: PHASES.LONG_BREAK,
        secondsRemaining: totalSec,
        totalSeconds: totalSec,
        isRunning: true,
        sessionsCompleted: 0,
      };
    }
    case 'TICK':
      if (state.secondsRemaining <= 0) return state;
      return { ...state, secondsRemaining: state.secondsRemaining - 1 };
    case 'PAUSE':
      return { ...state, isRunning: false };
    case 'RESUME':
      return { ...state, isRunning: true };
    case 'RESET':
      return {
        ...initialState,
        settings: state.settings,
        profile: state.profile,
        currentTag: state.currentTag,
      };
    case 'SET_SECONDS':
      return { ...state, secondsRemaining: action.payload };
    default:
      return state;
  }
};

export const TimerProvider = ({ children }) => {
  const [state, dispatch] = useReducer(timerReducer, initialState);
  const intervalRef = useRef(null);
  const backgroundTimeRef = useRef(null);
  const stateRef = useRef(state);
  const { refreshUser } = useAuth();

  // Keep stateRef in sync
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Derived boolean for whether timer should be ticking
  const shouldTick = state.isRunning && state.secondsRemaining > 0;

  // Tick logic
  useEffect(() => {
    if (shouldTick) {
      intervalRef.current = setInterval(() => {
        dispatch({ type: 'TICK' });
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [shouldTick]);

  // Haptic pulse every 5 minutes during focus
  useEffect(() => {
    if (
      state.phase === PHASES.FOCUSING &&
      state.isRunning &&
      state.secondsRemaining > 0 &&
      state.secondsRemaining % 300 === 0 &&
      state.secondsRemaining !== state.totalSeconds
    ) {
      Vibration.vibrate(200);
    }
  }, [state.secondsRemaining, state.phase, state.isRunning, state.totalSeconds]);

  // Sync pending sessions on mount
  const syncPendingSessions = useCallback(async () => {
    try {
      const pending = await getPendingSessions();
      if (pending.length === 0) return;
      for (const sessionData of pending) {
        await createSession(sessionData);
      }
      await clearPendingSessions();
    } catch (err) {
      // Still offline or API error — keep sessions queued
    }
  }, []);

  useEffect(() => {
    syncPendingSessions();
  }, [syncPendingSessions]);

  // Phase completion — uses ref to avoid stale closure
  const handlePhaseComplete = useCallback(async () => {
    const s = stateRef.current;
    const { phase, sessionsCompleted, settings } = s;

    if (phase === PHASES.FOCUSING) {
      // Post completed session to API
      const sessionData = {
        tag: s.currentTag,
        intention: s.intention || null,
        duration_minutes: settings.focusDuration,
        completed: true,
        started_at: s.sessionStartedAt,
        ended_at: new Date().toISOString(),
        session_type: 'focus',
      };
      try {
        const response = await createSession(sessionData);
        dispatch({ type: 'SET_LAST_SESSION_ID', payload: response.id });
        await refreshUser();
        // We're online — flush any previously queued sessions
        await syncPendingSessions();
      } catch (err) {
        // Offline — queue session for later sync
        await queueSession(sessionData);
      }

      // Decide next phase
      if (sessionsCompleted + 1 >= settings.sessionsBeforeLongBreak) {
        if (settings.autoAdvance) {
          dispatch({ type: 'START_LONG_BREAK' });
        } else {
          dispatch({ type: 'PAUSE' });
        }
      } else {
        if (settings.autoAdvance) {
          dispatch({ type: 'START_SHORT_BREAK' });
        } else {
          dispatch({ type: 'PAUSE' });
        }
      }
    } else if (
      phase === PHASES.SHORT_BREAK ||
      phase === PHASES.LONG_BREAK
    ) {
      if (settings.autoAdvance) {
        dispatch({ type: 'START_FOCUS' });
      } else {
        dispatch({ type: 'PAUSE' });
      }
    }
  }, [refreshUser, syncPendingSessions]);

  // Detect phase completion
  useEffect(() => {
    if (state.secondsRemaining === 0 && state.isRunning) {
      Vibration.vibrate([0, 500, 200, 500]);
      handlePhaseComplete();
    }
  }, [state.secondsRemaining, state.isRunning, handlePhaseComplete]);

  // Background timer support
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'background' || nextAppState === 'inactive') {
        backgroundTimeRef.current = Date.now();
      } else if (nextAppState === 'active' && backgroundTimeRef.current) {
        const elapsed = Math.floor(
          (Date.now() - backgroundTimeRef.current) / 1000
        );
        backgroundTimeRef.current = null;
        const s = stateRef.current;
        if (s.isRunning && elapsed > 0) {
          const newRemaining = Math.max(0, s.secondsRemaining - elapsed);
          dispatch({ type: 'SET_SECONDS', payload: newRemaining });
        }
      }
    });

    return () => subscription.remove();
  }, []);

  const startRitual = useCallback(() => dispatch({ type: 'START_RITUAL' }), []);
  const startFocus = useCallback(() => dispatch({ type: 'START_FOCUS' }), []);
  const startShortBreak = useCallback(() => dispatch({ type: 'START_SHORT_BREAK' }), []);
  const startLongBreak = useCallback(() => dispatch({ type: 'START_LONG_BREAK' }), []);
  const pause = useCallback(() => {
    const s = stateRef.current;
    if (s.phase === PHASES.FOCUSING) {
      try {
        pausePenalty();
      } catch (err) {
        // Fire and forget — ignore errors
      }
    }
    dispatch({ type: 'PAUSE' });
  }, []);
  const resume = useCallback(() => dispatch({ type: 'RESUME' }), []);
  const reset = useCallback(() => dispatch({ type: 'RESET' }), []);
  const setTag = useCallback((tag) => dispatch({ type: 'SET_TAG', payload: tag }), []);
  const setIntention = useCallback(
    (text) => dispatch({ type: 'SET_INTENTION', payload: text }),
    []
  );
  const setSettings = useCallback(
    (s) => dispatch({ type: 'SET_SETTINGS', payload: s }),
    []
  );
  const setProfile = useCallback(
    (p) => dispatch({ type: 'SET_PROFILE', payload: p }),
    []
  );

  const startNextPhase = useCallback(() => {
    const s = stateRef.current;
    const { phase, sessionsCompleted, settings } = s;
    if (phase === PHASES.IDLE) {
      dispatch({ type: 'START_RITUAL' });
    } else if (phase === PHASES.FOCUSING) {
      if (sessionsCompleted + 1 >= settings.sessionsBeforeLongBreak) {
        dispatch({ type: 'START_LONG_BREAK' });
      } else {
        dispatch({ type: 'START_SHORT_BREAK' });
      }
    } else {
      dispatch({ type: 'START_RITUAL' });
    }
  }, []);

  return (
    <TimerContext.Provider
      value={{
        ...state,
        dispatch,
        startRitual,
        startFocus,
        startShortBreak,
        startLongBreak,
        startNextPhase,
        pause,
        resume,
        reset,
        setTag,
        setIntention,
        setSettings,
        setProfile,
      }}
    >
      {children}
    </TimerContext.Provider>
  );
};

export const useTimer = () => {
  const context = useContext(TimerContext);
  if (!context) {
    throw new Error('useTimer must be used within a TimerProvider');
  }
  return context;
};

export default TimerContext;
