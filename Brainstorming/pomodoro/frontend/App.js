/**
 * Deep Focus — App entry point.
 * Wraps everything in providers: Auth, Theme, Timer.
 */

import React from 'react';
import { StatusBar } from 'react-native';
import { AuthProvider } from './src/contexts/AuthContext';
import { ThemeProvider } from './src/contexts/ThemeContext';
import { TimerProvider } from './src/contexts/TimerContext';
import AppNavigator from './src/navigation/AppNavigator';

export default function App() {
  return (
    <AuthProvider>
      <ThemeProvider>
        <TimerProvider>
          <StatusBar barStyle="light-content" />
          <AppNavigator />
        </TimerProvider>
      </ThemeProvider>
    </AuthProvider>
  );
}
