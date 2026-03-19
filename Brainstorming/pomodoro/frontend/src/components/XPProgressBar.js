/**
 * XPProgressBar — Brutalist XP bar. No rounded corners. Stark fill.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import { calculateLevel, xpForLevel, levelProgress } from '../utils/formatTime';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const XPProgressBar = ({ xp = 0 }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  const level = calculateLevel(xp);
  const progress = levelProgress(xp);
  const currentLevelXp = xpForLevel(level);
  const nextLevelXp = xpForLevel(level + 1);

  return (
    <View style={styles.container}>
      <View style={styles.labelRow}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          LEVEL {level}
        </Text>
        <Text style={[styles.xpText, { color: colors.textSecondary }]}>
          {xp - currentLevelXp} / {nextLevelXp - currentLevelXp} XP
        </Text>
      </View>
      <View
        style={[
          styles.track,
          {
            backgroundColor: colors.timerTrack,
            borderColor: colors.border,
          },
        ]}
      >
        <View
          style={[
            styles.fill,
            {
              width: `${Math.min(progress * 100, 100)}%`,
              backgroundColor: colors.primary,
            },
          ]}
        />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  labelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  label: {
    ...typography.label,
  },
  xpText: {
    ...typography.caption,
  },
  track: {
    height: 16,
    borderWidth: 2,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
  },
});

export default XPProgressBar;
