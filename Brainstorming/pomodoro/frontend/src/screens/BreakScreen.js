/**
 * BreakScreen — Break timer, distraction log, micro-challenges.
 * Appears after a focus session completes.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  StatusBar,
} from 'react-native';
import RealmBackground from '../components/RealmBackground';
import CircularTimer from '../components/CircularTimer';
import DistractionLogger from '../components/DistractionLogger';
import { useTimer, PHASES } from '../contexts/TimerContext';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const MICRO_CHALLENGES = [
  { text: 'STAND UP AND STRETCH FOR 30 SECONDS', icon: '\u2195' },
  { text: 'DRINK A GLASS OF WATER', icon: '\u25CF' },
  { text: '20-20-20: LOOK 20FT AWAY FOR 20 SECONDS', icon: '\u25C9' },
  { text: 'TAKE 5 DEEP BREATHS', icon: '\u2261' },
  { text: 'ROLL YOUR SHOULDERS 10 TIMES', icon: '\u21BB' },
  { text: 'CLOSE YOUR EYES FOR 15 SECONDS', icon: '\u2500' },
];

const BreakScreen = ({ navigation }) => {
  const timer = useTimer();
  const { theme } = useTheme();
  const { colors } = theme;

  const [challenge] = useState(
    () => MICRO_CHALLENGES[Math.floor(Math.random() * MICRO_CHALLENGES.length)]
  );

  const isLongBreak = timer.phase === PHASES.LONG_BREAK;

  // Navigate back when break ends or user returns to idle
  useEffect(() => {
    if (timer.phase === PHASES.IDLE || timer.phase === PHASES.RITUAL || timer.phase === PHASES.FOCUSING) {
      navigation.navigate('Timer');
    }
  }, [timer.phase]);

  const handleSkipBreak = () => {
    timer.startRitual();
  };

  const handleStartNextFocus = () => {
    timer.startRitual();
  };

  return (
    <RealmBackground>
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Break type label */}
        <Text style={[styles.breakLabel, { color: colors.primary }]}>
          {isLongBreak ? 'LONG BREAK' : 'SHORT BREAK'}
        </Text>
        <Text style={[styles.breakSubtext, { color: colors.textSecondary }]}>
          {isLongBreak
            ? 'FULL CYCLE COMPLETE. YOU EARNED THIS.'
            : 'REST. RECHARGE. RETURN.'}
        </Text>

        {/* Timer */}
        <View style={styles.timerContainer}>
          <CircularTimer
            secondsRemaining={timer.secondsRemaining}
            totalSeconds={timer.totalSeconds}
            size={220}
            strokeWidth={8}
          />
        </View>

        {/* Micro-challenge */}
        <View style={[styles.challengeBox, { borderColor: colors.border, backgroundColor: colors.cardBg }]}>
          <Text style={[styles.challengeIcon, { color: colors.primary }]}>
            {challenge.icon}
          </Text>
          <Text style={[styles.challengeLabel, { color: colors.textSecondary }]}>
            MICRO-CHALLENGE
          </Text>
          <Text style={[styles.challengeText, { color: colors.text }]}>
            {challenge.text}
          </Text>
        </View>

        {/* Distraction Logger */}
        <View style={styles.distractionSection}>
          <DistractionLogger sessionId={timer.lastSessionId} onLogged={() => {}} />
        </View>

        {/* Controls */}
        <View style={styles.controls}>
          {timer.isRunning ? (
            <TouchableOpacity
              onPress={handleSkipBreak}
              style={[styles.skipButton, { borderColor: colors.border }]}
            >
              <Text style={[styles.skipText, { color: colors.textSecondary }]}>
                SKIP BREAK
              </Text>
            </TouchableOpacity>
          ) : (
            <View style={styles.completeControls}>
              <Text style={[styles.breakDoneText, { color: colors.success }]}>
                BREAK OVER
              </Text>
              <TouchableOpacity
                onPress={handleStartNextFocus}
                style={[styles.mainButton, { backgroundColor: colors.buttonBg }]}
              >
                <Text style={[styles.mainButtonText, { color: colors.buttonText }]}>
                  NEXT FOCUS SESSION
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={timer.reset}
                style={[styles.skipButton, { borderColor: colors.border, marginTop: spacing.sm }]}
              >
                <Text style={[styles.skipText, { color: colors.textSecondary }]}>
                  END SESSION
                </Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </ScrollView>
    </RealmBackground>
  );
};

const styles = StyleSheet.create({
  scrollContent: {
    flexGrow: 1,
    padding: spacing.screenPadding,
    paddingTop: spacing.xxl,
  },
  breakLabel: {
    ...typography.h1,
    textAlign: 'center',
  },
  breakSubtext: {
    ...typography.caption,
    textAlign: 'center',
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  timerContainer: {
    alignItems: 'center',
    marginVertical: spacing.lg,
  },
  challengeBox: {
    borderWidth: 3,
    padding: spacing.lg,
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  challengeIcon: {
    fontSize: 32,
    marginBottom: spacing.sm,
  },
  challengeLabel: {
    ...typography.label,
    marginBottom: spacing.xs,
  },
  challengeText: {
    ...typography.bodyBold,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  distractionSection: {
    marginBottom: spacing.lg,
  },
  controls: {
    marginTop: spacing.md,
  },
  skipButton: {
    borderWidth: 3,
    padding: spacing.md,
    alignItems: 'center',
  },
  skipText: {
    ...typography.button,
    fontSize: 14,
  },
  completeControls: {
    alignItems: 'center',
  },
  breakDoneText: {
    ...typography.h3,
    marginBottom: spacing.md,
  },
  mainButton: {
    padding: spacing.lg,
    alignItems: 'center',
    width: '100%',
  },
  mainButtonText: {
    ...typography.button,
  },
});

export default BreakScreen;
