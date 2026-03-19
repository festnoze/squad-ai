/**
 * TimerScreen — The heart of the app. Full-screen realm background,
 * circular timer, tag selector, intention, start/pause/resume controls.
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
import TagSelector from '../components/TagSelector';
import IntentionInput from '../components/IntentionInput';
import FocusRitual from '../components/FocusRitual';
import StreakBadge from '../components/StreakBadge';
import { useTimer, PHASES } from '../contexts/TimerContext';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { getProfile } from '../api/profile';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const TimerScreen = ({ navigation }) => {
  const timer = useTimer();
  const { theme } = useTheme();
  const { colors } = theme;
  const { user } = useAuth();

  const [profile, setProfile] = useState(null);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const p = await getProfile();
      setProfile(p);
      timer.setProfile(p);
      if (p.focus_duration) {
        timer.setSettings({
          focusDuration: p.focus_duration,
          shortBreakDuration: p.short_break_duration,
          longBreakDuration: p.long_break_duration,
          sessionsBeforeLongBreak: p.sessions_before_long_break,
          autoAdvance: p.auto_advance,
        });
      }
    } catch (err) {
      // Offline — use defaults
    }
  };

  // Handle ritual completion
  const handleRitualComplete = () => {
    timer.startFocus();
  };

  // Handle phase complete — navigate to break screen
  useEffect(() => {
    if (
      (timer.phase === PHASES.SHORT_BREAK ||
        timer.phase === PHASES.LONG_BREAK) &&
      timer.secondsRemaining === timer.totalSeconds
    ) {
      navigation.navigate('Break');
    }
  }, [timer.phase]);

  const getPhaseLabel = () => {
    switch (timer.phase) {
      case PHASES.IDLE:
        return 'READY TO FOCUS';
      case PHASES.FOCUSING:
        return 'FOCUSING';
      case PHASES.SHORT_BREAK:
        return 'SHORT BREAK';
      case PHASES.LONG_BREAK:
        return 'LONG BREAK';
      case PHASES.RITUAL:
        return 'RITUAL';
      default:
        return '';
    }
  };

  const getSessionCount = () => {
    return `${timer.sessionsCompleted} / ${timer.settings.sessionsBeforeLongBreak}`;
  };

  // Ritual screen
  if (timer.phase === PHASES.RITUAL) {
    return (
      <RealmBackground>
        <StatusBar barStyle="light-content" backgroundColor={colors.background} />
        <FocusRitual
          intention={timer.intention}
          onComplete={handleRitualComplete}
        />
      </RealmBackground>
    );
  }

  return (
    <RealmBackground>
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Top bar with streak and session count */}
        <View style={styles.topBar}>
          <StreakBadge
            currentStreak={profile?.current_streak || 0}
            compact
          />
          <View style={[styles.sessionCounter, { borderColor: colors.border }]}>
            <Text style={[styles.sessionText, { color: colors.textSecondary }]}>
              SESSIONS {getSessionCount()}
            </Text>
          </View>
        </View>

        {/* Phase label */}
        <Text style={[styles.phaseLabel, { color: colors.textSecondary }]}>
          {getPhaseLabel()}
        </Text>

        {/* Realm tagline */}
        <Text style={[styles.tagline, { color: colors.textSecondary }]}>
          {theme.realm.tagline}
        </Text>

        {/* Circular Timer */}
        <View style={styles.timerContainer}>
          <CircularTimer
            secondsRemaining={timer.secondsRemaining}
            totalSeconds={timer.totalSeconds}
            size={300}
            strokeWidth={12}
          />
        </View>

        {/* Intention display during focus */}
        {timer.phase === PHASES.FOCUSING && timer.intention ? (
          <View style={[styles.intentionDisplay, { borderColor: colors.border }]}>
            <Text style={[styles.intentionLabel, { color: colors.textSecondary }]}>
              INTENTION
            </Text>
            <Text style={[styles.intentionText, { color: colors.text }]}>
              {timer.intention}
            </Text>
          </View>
        ) : null}

        {/* Controls */}
        <View style={styles.controls}>
          {timer.phase === PHASES.IDLE && (
            <>
              {/* Tag selector and intention — only when idle */}
              <TagSelector
                selectedTag={timer.currentTag}
                onSelectTag={timer.setTag}
              />

              <View style={styles.intentionSection}>
                <IntentionInput
                  value={timer.intention}
                  onChangeText={timer.setIntention}
                />
              </View>

              <TouchableOpacity
                onPress={timer.startRitual}
                style={[styles.mainButton, { backgroundColor: colors.buttonBg }]}
              >
                <Text style={[styles.mainButtonText, { color: colors.buttonText }]}>
                  START FOCUS
                </Text>
              </TouchableOpacity>
            </>
          )}

          {timer.phase === PHASES.FOCUSING && timer.isRunning && (
            <TouchableOpacity
              onPress={timer.pause}
              style={[styles.mainButton, { backgroundColor: 'transparent', borderColor: colors.border, borderWidth: 3 }]}
            >
              <Text style={[styles.mainButtonText, { color: colors.text }]}>
                PAUSE (-2 XP)
              </Text>
            </TouchableOpacity>
          )}

          {timer.phase === PHASES.FOCUSING && !timer.isRunning && timer.secondsRemaining > 0 && (
            <View style={styles.pausedControls}>
              <TouchableOpacity
                onPress={timer.resume}
                style={[styles.mainButton, { backgroundColor: colors.buttonBg, flex: 1 }]}
              >
                <Text style={[styles.mainButtonText, { color: colors.buttonText }]}>
                  RESUME
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={timer.reset}
                style={[styles.secondaryButton, { borderColor: colors.danger }]}
              >
                <Text style={[styles.secondaryButtonText, { color: colors.danger }]}>
                  QUIT
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Phase complete — waiting for manual advance */}
          {!timer.isRunning &&
            timer.secondsRemaining === 0 &&
            timer.phase === PHASES.FOCUSING && (
              <View style={styles.completeControls}>
                <Text style={[styles.completeText, { color: colors.success }]}>
                  SESSION COMPLETE
                </Text>
                <TouchableOpacity
                  onPress={timer.startNextPhase}
                  style={[styles.mainButton, { backgroundColor: colors.buttonBg }]}
                >
                  <Text style={[styles.mainButtonText, { color: colors.buttonText }]}>
                    START BREAK
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={timer.reset}
                  style={[styles.secondaryButton, { borderColor: colors.border, marginTop: spacing.sm }]}
                >
                  <Text style={[styles.secondaryButtonText, { color: colors.textSecondary }]}>
                    BACK TO IDLE
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
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  sessionCounter: {
    borderWidth: 2,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  sessionText: {
    ...typography.caption,
    fontSize: 11,
  },
  phaseLabel: {
    ...typography.h2,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
  tagline: {
    ...typography.caption,
    textAlign: 'center',
    marginBottom: spacing.lg,
    opacity: 0.6,
  },
  timerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: spacing.lg,
  },
  intentionDisplay: {
    borderWidth: 3,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  intentionLabel: {
    ...typography.label,
    marginBottom: spacing.xs,
  },
  intentionText: {
    ...typography.body,
    fontSize: 16,
  },
  controls: {
    marginTop: spacing.md,
  },
  intentionSection: {
    marginTop: spacing.lg,
  },
  mainButton: {
    padding: spacing.lg,
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  mainButtonText: {
    ...typography.button,
  },
  pausedControls: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  secondaryButton: {
    borderWidth: 3,
    padding: spacing.lg,
    alignItems: 'center',
  },
  secondaryButtonText: {
    ...typography.button,
    fontSize: 14,
  },
  completeControls: {
    alignItems: 'center',
  },
  completeText: {
    ...typography.h2,
    marginBottom: spacing.md,
  },
});

export default TimerScreen;
