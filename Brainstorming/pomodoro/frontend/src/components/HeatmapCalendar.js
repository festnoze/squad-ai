/**
 * HeatmapCalendar — Focus time heatmap as a grid of days.
 * Color intensity = focus minutes that day. Brutalist grid, no rounding.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const DAYS_TO_SHOW = 35; // 5 weeks
const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

const HeatmapCalendar = ({ data = {} }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  // Generate last N days
  const days = [];
  const today = new Date();
  for (let i = DAYS_TO_SHOW - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().split('T')[0];
    days.push({
      key,
      date: d,
      minutes: data[key] || 0,
    });
  }

  const maxMinutes = Math.max(...days.map((d) => d.minutes), 1);

  const getIntensity = (minutes) => {
    if (minutes === 0) return 0;
    return Math.max(0.15, minutes / maxMinutes);
  };

  // Arrange into weeks (columns)
  const weeks = [];
  let currentWeek = [];
  // Pad the first week
  const firstDayOfWeek = (days[0].date.getDay() + 6) % 7; // Monday=0
  for (let i = 0; i < firstDayOfWeek; i++) {
    currentWeek.push(null);
  }
  for (const day of days) {
    currentWeek.push(day);
    if (currentWeek.length === 7) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
  }
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) {
      currentWeek.push(null);
    }
    weeks.push(currentWeek);
  }

  return (
    <View style={styles.container}>
      <Text style={[styles.title, { color: colors.text }]}>FOCUS HEATMAP</Text>

      <View style={styles.grid}>
        {/* Day labels column */}
        <View style={styles.dayLabelsCol}>
          {DAY_LABELS.map((label, i) => (
            <View key={i} style={styles.cell}>
              <Text style={[styles.dayLabel, { color: colors.textSecondary }]}>
                {label}
              </Text>
            </View>
          ))}
        </View>

        {/* Week columns */}
        {weeks.map((week, wi) => (
          <View key={wi} style={styles.weekCol}>
            {week.map((day, di) => (
              <View
                key={di}
                style={[
                  styles.cell,
                  styles.heatCell,
                  {
                    borderColor: day ? colors.border + '44' : 'transparent',
                    backgroundColor: day
                      ? day.minutes > 0
                        ? colors.primary +
                          Math.round(getIntensity(day.minutes) * 255)
                            .toString(16)
                            .padStart(2, '0')
                        : colors.surface
                      : 'transparent',
                  },
                ]}
              />
            ))}
          </View>
        ))}
      </View>

      {/* Legend */}
      <View style={styles.legend}>
        <Text style={[styles.legendText, { color: colors.textSecondary }]}>
          LESS
        </Text>
        {[0, 0.25, 0.5, 0.75, 1].map((intensity, i) => (
          <View
            key={i}
            style={[
              styles.legendCell,
              {
                borderColor: colors.border + '44',
                backgroundColor:
                  intensity === 0
                    ? colors.surface
                    : colors.primary +
                      Math.round(intensity * 255)
                        .toString(16)
                        .padStart(2, '0'),
              },
            ]}
          />
        ))}
        <Text style={[styles.legendText, { color: colors.textSecondary }]}>
          MORE
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  title: {
    ...typography.h3,
    marginBottom: spacing.md,
  },
  grid: {
    flexDirection: 'row',
    gap: 3,
  },
  dayLabelsCol: {
    gap: 3,
    marginRight: 4,
  },
  weekCol: {
    gap: 3,
    flex: 1,
  },
  cell: {
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  heatCell: {
    borderWidth: 1,
  },
  dayLabel: {
    ...typography.label,
    fontSize: 9,
  },
  legend: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    marginTop: spacing.md,
  },
  legendCell: {
    width: 16,
    height: 16,
    borderWidth: 1,
  },
  legendText: {
    ...typography.label,
    fontSize: 9,
  },
});

export default HeatmapCalendar;
