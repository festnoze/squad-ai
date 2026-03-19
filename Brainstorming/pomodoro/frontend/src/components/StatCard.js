/**
 * StatCard — Brutalist stat display. No border-radius. Heavy borders.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const StatCard = ({ label, value, unit, accent = false }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  return (
    <View
      style={[
        styles.card,
        {
          borderColor: accent ? colors.primary : colors.border,
          backgroundColor: colors.cardBg,
        },
      ]}
    >
      <Text style={[styles.label, { color: colors.textSecondary }]}>
        {label}
      </Text>
      <Text
        style={[
          styles.value,
          { color: accent ? colors.primary : colors.text },
        ]}
      >
        {value}
      </Text>
      {unit && (
        <Text style={[styles.unit, { color: colors.textSecondary }]}>
          {unit}
        </Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderWidth: 3,
    padding: spacing.md,
    flex: 1,
    minWidth: 100,
  },
  label: {
    ...typography.label,
    marginBottom: spacing.xs,
  },
  value: {
    ...typography.stat,
  },
  unit: {
    ...typography.caption,
    marginTop: 2,
  },
});

export default StatCard;
