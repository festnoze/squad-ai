/**
 * FocusRitual — 3-second breathing animation + intention display.
 * A ritualistic gateway into focus mode.
 */

import React, { useEffect, useState, useRef } from 'react';
import { View, Text, Animated, StyleSheet } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const FocusRitual = ({ intention, onComplete }) => {
  const { theme } = useTheme();
  const { colors } = theme;
  const [count, setCount] = useState(3);
  const scaleAnim = useRef(new Animated.Value(0.5)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Fade in
    Animated.timing(opacityAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();

    // Countdown
    const interval = setInterval(() => {
      setCount((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          setTimeout(() => {
            if (onComplete) onComplete();
          }, 500);
          return 0;
        }
        return prev - 1;
      });
    }, 1200);

    return () => clearInterval(interval);
  }, []);

  // Breathing pulse animation
  useEffect(() => {
    const breathe = Animated.loop(
      Animated.sequence([
        Animated.timing(scaleAnim, {
          toValue: 1.2,
          duration: 1200,
          useNativeDriver: true,
        }),
        Animated.timing(scaleAnim, {
          toValue: 0.8,
          duration: 1200,
          useNativeDriver: true,
        }),
      ])
    );
    breathe.start();
    return () => breathe.stop();
  }, []);

  return (
    <Animated.View style={[styles.container, { opacity: opacityAnim }]}>
      <Text style={[styles.breatheText, { color: colors.textSecondary }]}>
        BREATHE
      </Text>

      <Animated.View
        style={[
          styles.countCircle,
          {
            borderColor: colors.primary,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        <Text style={[styles.countText, { color: colors.primary }]}>
          {count > 0 ? count : '\u2713'}
        </Text>
      </Animated.View>

      {intention ? (
        <View style={[styles.intentionBox, { borderColor: colors.border }]}>
          <Text style={[styles.intentionLabel, { color: colors.textSecondary }]}>
            YOUR INTENTION
          </Text>
          <Text style={[styles.intentionText, { color: colors.text }]}>
            {intention}
          </Text>
        </View>
      ) : null}

      <Text style={[styles.tagline, { color: colors.textSecondary }]}>
        {theme.realm.tagline}
      </Text>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.screenPadding,
  },
  breatheText: {
    ...typography.h2,
    marginBottom: spacing.xxl,
  },
  countCircle: {
    width: 160,
    height: 160,
    borderWidth: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countText: {
    ...typography.timer,
    fontSize: 72,
  },
  intentionBox: {
    borderWidth: 3,
    padding: spacing.lg,
    marginTop: spacing.xxl,
    width: '100%',
  },
  intentionLabel: {
    ...typography.label,
    marginBottom: spacing.xs,
  },
  intentionText: {
    ...typography.body,
    fontSize: 18,
  },
  tagline: {
    ...typography.caption,
    marginTop: spacing.xxl,
    opacity: 0.6,
  },
});

export default FocusRitual;
