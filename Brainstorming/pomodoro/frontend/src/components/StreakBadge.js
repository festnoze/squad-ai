/**
 * StreakBadge — Streak flame display. Brutalist, bold numbers.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const StreakBadge = ({ currentStreak = 0, longestStreak = 0, compact = false }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  const getStreakMultiplier = (streak) => {
    if (streak >= 14) return '3x';
    if (streak >= 7) return '2x';
    if (streak >= 3) return '1.5x';
    return '1x';
  };

  if (compact) {
    return (
      <View style={[styles.compactContainer, { borderColor: colors.border }]}>
        <Text style={[styles.flameIcon, { color: colors.primary }]}>
          {currentStreak > 0 ? '\u2593' : '\u2591'}
        </Text>
        <Text style={[styles.streakNumber, { color: colors.primary }]}>
          {currentStreak}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.streakBox, { borderColor: colors.border, backgroundColor: colors.cardBg }]}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          CURRENT STREAK
        </Text>
        <View style={styles.streakRow}>
          <Text style={[styles.bigNumber, { color: colors.primary }]}>
            {currentStreak}
          </Text>
          <Text style={[styles.unit, { color: colors.textSecondary }]}>
            DAYS
          </Text>
        </View>
        <Text style={[styles.multiplier, { color: colors.accent }]}>
          {getStreakMultiplier(currentStreak)} MULTIPLIER
        </Text>
      </View>
      <View style={[styles.streakBox, { borderColor: colors.border, backgroundColor: colors.cardBg }]}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          LONGEST STREAK
        </Text>
        <View style={styles.streakRow}>
          <Text style={[styles.bigNumber, { color: colors.text }]}>
            {longestStreak}
          </Text>
          <Text style={[styles.unit, { color: colors.textSecondary }]}>
            DAYS
          </Text>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 2,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    gap: spacing.xs,
  },
  flameIcon: {
    fontSize: 18,
    fontWeight: '900',
  },
  streakNumber: {
    ...typography.bodyBold,
  },
  streakBox: {
    flex: 1,
    borderWidth: 3,
    padding: spacing.md,
  },
  label: {
    ...typography.label,
    marginBottom: spacing.xs,
  },
  streakRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.xs,
  },
  bigNumber: {
    ...typography.stat,
  },
  unit: {
    ...typography.caption,
  },
  multiplier: {
    ...typography.caption,
    marginTop: spacing.xs,
  },
});

export default StreakBadge;
