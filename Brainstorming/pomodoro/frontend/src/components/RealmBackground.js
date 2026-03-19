/**
 * RealmBackground — Full-screen immersive gradient background.
 * Each realm transforms the entire visual atmosphere.
 * Using LinearGradient from expo-linear-gradient.
 */

import React from 'react';
import { StyleSheet, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useTheme } from '../contexts/ThemeContext';

const RealmBackground = ({ children, style }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  return (
    <LinearGradient
      colors={colors.gradient}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[styles.gradient, style]}
    >
      {/* Subtle overlay for depth */}
      <View style={[styles.overlay, { backgroundColor: colors.background + '33' }]}>
        {children}
      </View>
    </LinearGradient>
  );
};

const styles = StyleSheet.create({
  gradient: {
    flex: 1,
  },
  overlay: {
    flex: 1,
  },
});

export default RealmBackground;
