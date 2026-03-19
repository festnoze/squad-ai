/**
 * SettingsScreen — Timer durations, auto-advance, realm selection, logout.
 * Brutalist sliders and toggles.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  StatusBar,
  Switch,
  Alert,
} from 'react-native';
import Slider from '@react-native-community/slider';
import RealmBackground from '../components/RealmBackground';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { useTimer } from '../contexts/TimerContext';
import { updateSettings } from '../api/profile';
import { getAllRealms } from '../theme/realms';
import { calculateLevel } from '../utils/formatTime';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const SettingsScreen = () => {
  const { theme, switchRealm, activeRealmId } = useTheme();
  const { colors } = theme;
  const { logout, user } = useAuth();
  const timer = useTimer();

  const [focusDuration, setFocusDuration] = useState(
    timer.settings.focusDuration
  );
  const [shortBreakDuration, setShortBreakDuration] = useState(
    timer.settings.shortBreakDuration
  );
  const [longBreakDuration, setLongBreakDuration] = useState(
    timer.settings.longBreakDuration
  );
  const [sessionsBeforeLongBreak, setSessionsBeforeLongBreak] = useState(
    timer.settings.sessionsBeforeLongBreak
  );
  const [autoAdvance, setAutoAdvance] = useState(
    timer.settings.autoAdvance
  );
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const newSettings = {
      focus_duration: focusDuration,
      short_break_duration: shortBreakDuration,
      long_break_duration: longBreakDuration,
      sessions_before_long_break: sessionsBeforeLongBreak,
      auto_advance: autoAdvance,
    };
    try {
      await updateSettings(newSettings);
      timer.setSettings({
        focusDuration,
        shortBreakDuration,
        longBreakDuration,
        sessionsBeforeLongBreak,
        autoAdvance,
      });
      Alert.alert('SAVED', 'Settings updated.');
    } catch (err) {
      // Save locally even if API fails
      timer.setSettings({
        focusDuration,
        shortBreakDuration,
        longBreakDuration,
        sessionsBeforeLongBreak,
        autoAdvance,
      });
      Alert.alert('SAVED LOCALLY', 'Will sync when connected.');
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('LOGOUT', 'Are you sure you want to leave?', [
      { text: 'CANCEL', style: 'cancel' },
      { text: 'LOGOUT', style: 'destructive', onPress: logout },
    ]);
  };

  const allRealms = getAllRealms();
  const level = calculateLevel(timer.profile?.xp || 0);

  return (
    <RealmBackground>
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text style={[styles.pageTitle, { color: colors.text }]}>
          SETTINGS
        </Text>

        {/* Timer settings */}
        <View style={[styles.section, { borderColor: colors.border }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            TIMER
          </Text>

          {/* Focus duration */}
          <View style={styles.sliderRow}>
            <View style={styles.sliderLabel}>
              <Text style={[styles.labelText, { color: colors.textSecondary }]}>
                FOCUS DURATION
              </Text>
              <Text style={[styles.labelValue, { color: colors.primary }]}>
                {focusDuration} MIN
              </Text>
            </View>
            <Slider
              value={focusDuration}
              onValueChange={(v) => setFocusDuration(Math.round(v))}
              minimumValue={1}
              maximumValue={90}
              step={1}
              minimumTrackTintColor={colors.primary}
              maximumTrackTintColor={colors.timerTrack}
              thumbTintColor={colors.primary}
              style={styles.slider}
            />
          </View>

          {/* Short break */}
          <View style={styles.sliderRow}>
            <View style={styles.sliderLabel}>
              <Text style={[styles.labelText, { color: colors.textSecondary }]}>
                SHORT BREAK
              </Text>
              <Text style={[styles.labelValue, { color: colors.primary }]}>
                {shortBreakDuration} MIN
              </Text>
            </View>
            <Slider
              value={shortBreakDuration}
              onValueChange={(v) => setShortBreakDuration(Math.round(v))}
              minimumValue={1}
              maximumValue={30}
              step={1}
              minimumTrackTintColor={colors.primary}
              maximumTrackTintColor={colors.timerTrack}
              thumbTintColor={colors.primary}
              style={styles.slider}
            />
          </View>

          {/* Long break */}
          <View style={styles.sliderRow}>
            <View style={styles.sliderLabel}>
              <Text style={[styles.labelText, { color: colors.textSecondary }]}>
                LONG BREAK
              </Text>
              <Text style={[styles.labelValue, { color: colors.primary }]}>
                {longBreakDuration} MIN
              </Text>
            </View>
            <Slider
              value={longBreakDuration}
              onValueChange={(v) => setLongBreakDuration(Math.round(v))}
              minimumValue={5}
              maximumValue={60}
              step={1}
              minimumTrackTintColor={colors.primary}
              maximumTrackTintColor={colors.timerTrack}
              thumbTintColor={colors.primary}
              style={styles.slider}
            />
          </View>

          {/* Sessions before long break */}
          <View style={styles.sliderRow}>
            <View style={styles.sliderLabel}>
              <Text style={[styles.labelText, { color: colors.textSecondary }]}>
                SESSIONS BEFORE LONG BREAK
              </Text>
              <Text style={[styles.labelValue, { color: colors.primary }]}>
                {sessionsBeforeLongBreak}
              </Text>
            </View>
            <Slider
              value={sessionsBeforeLongBreak}
              onValueChange={(v) =>
                setSessionsBeforeLongBreak(Math.round(v))
              }
              minimumValue={2}
              maximumValue={8}
              step={1}
              minimumTrackTintColor={colors.primary}
              maximumTrackTintColor={colors.timerTrack}
              thumbTintColor={colors.primary}
              style={styles.slider}
            />
          </View>

          {/* Auto-advance toggle */}
          <View style={styles.toggleRow}>
            <Text style={[styles.labelText, { color: colors.textSecondary }]}>
              AUTO-ADVANCE
            </Text>
            <Switch
              value={autoAdvance}
              onValueChange={setAutoAdvance}
              trackColor={{
                false: colors.timerTrack,
                true: colors.primary + '88',
              }}
              thumbColor={autoAdvance ? colors.primary : colors.textSecondary}
            />
          </View>
        </View>

        {/* Save button */}
        <TouchableOpacity
          onPress={handleSave}
          disabled={saving}
          style={[
            styles.saveButton,
            {
              backgroundColor: colors.buttonBg,
              opacity: saving ? 0.6 : 1,
            },
          ]}
        >
          <Text style={[styles.saveText, { color: colors.buttonText }]}>
            {saving ? 'SAVING...' : 'SAVE SETTINGS'}
          </Text>
        </TouchableOpacity>

        {/* Realm selection */}
        <View style={[styles.section, { borderColor: colors.border }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            ACTIVE REALM
          </Text>
          <View style={styles.realmList}>
            {allRealms.map((r) => {
              const isUnlocked = r.requiredLevel <= level;
              const isActive = activeRealmId === r.id;
              return (
                <TouchableOpacity
                  key={r.id}
                  onPress={() => isUnlocked && switchRealm(r.id)}
                  disabled={!isUnlocked}
                  style={[
                    styles.realmOption,
                    {
                      borderColor: isActive
                        ? r.colors.primary
                        : colors.border + '66',
                      backgroundColor: isActive
                        ? r.colors.primary + '22'
                        : 'transparent',
                      borderWidth: isActive ? 4 : 2,
                      opacity: isUnlocked ? 1 : 0.4,
                    },
                  ]}
                >
                  <View
                    style={[
                      styles.realmDot,
                      { backgroundColor: r.colors.primary },
                    ]}
                  />
                  <Text
                    style={[
                      styles.realmOptionName,
                      { color: isUnlocked ? colors.text : colors.textSecondary },
                    ]}
                  >
                    {r.name}
                  </Text>
                  {!isUnlocked && (
                    <Text style={[styles.lockText, { color: colors.textSecondary }]}>
                      LVL {r.requiredLevel}
                    </Text>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Account */}
        <View style={[styles.section, { borderColor: colors.border }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>
            ACCOUNT
          </Text>
          <Text style={[styles.accountEmail, { color: colors.textSecondary }]}>
            {user?.email || 'Unknown'}
          </Text>
          <TouchableOpacity
            onPress={handleLogout}
            style={[styles.logoutButton, { borderColor: colors.danger }]}
          >
            <Text style={[styles.logoutText, { color: colors.danger }]}>
              LOGOUT
            </Text>
          </TouchableOpacity>
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
    paddingBottom: spacing.xxxl,
  },
  pageTitle: {
    ...typography.h1,
    marginBottom: spacing.lg,
  },
  section: {
    borderWidth: 3,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.h3,
    marginBottom: spacing.md,
  },
  sliderRow: {
    marginBottom: spacing.lg,
  },
  sliderLabel: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  labelText: {
    ...typography.label,
  },
  labelValue: {
    ...typography.mono,
    fontWeight: '700',
    fontSize: 16,
  },
  slider: {
    width: '100%',
    height: 40,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  saveButton: {
    padding: spacing.lg,
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  saveText: {
    ...typography.button,
  },
  realmList: {
    gap: spacing.sm,
  },
  realmOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    gap: spacing.sm,
  },
  realmDot: {
    width: 16,
    height: 16,
  },
  realmOptionName: {
    ...typography.caption,
    fontSize: 13,
    flex: 1,
  },
  lockText: {
    ...typography.label,
    fontSize: 10,
  },
  accountEmail: {
    ...typography.body,
    marginBottom: spacing.md,
  },
  logoutButton: {
    borderWidth: 3,
    padding: spacing.md,
    alignItems: 'center',
  },
  logoutText: {
    ...typography.button,
  },
});

export default SettingsScreen;
