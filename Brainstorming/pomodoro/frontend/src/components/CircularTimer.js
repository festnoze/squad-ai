/**
 * CircularTimer — SVG-based circular countdown.
 * Brutalist: thick stroke, sharp termination, monospace time display.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '../contexts/ThemeContext';
import { formatTime } from '../utils/formatTime';
import typography from '../theme/typography';

const CircularTimer = ({ secondsRemaining, totalSeconds, size = 280, strokeWidth = 10 }) => {
  const { theme } = useTheme();
  const { colors } = theme;

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = totalSeconds > 0 ? secondsRemaining / totalSeconds : 0;
  const strokeDashoffset = circumference * (1 - progress);

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      <Svg width={size} height={size} style={styles.svg}>
        {/* Track */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={colors.timerTrack}
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Progress */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={colors.timer}
          strokeWidth={strokeWidth + 2}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="butt"
          rotation="-90"
          origin={`${size / 2}, ${size / 2}`}
        />
      </Svg>
      <View style={styles.timeContainer}>
        <Text style={[styles.timeText, { color: colors.timer }]}>
          {formatTime(secondsRemaining)}
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  svg: {
    position: 'absolute',
  },
  timeContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  timeText: {
    ...typography.timer,
  },
});

export default CircularTimer;
