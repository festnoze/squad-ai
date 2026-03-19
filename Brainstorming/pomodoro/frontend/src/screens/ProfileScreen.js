/**
 * ProfileScreen — Level badge, XP bar, streak, realm collection grid.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  StatusBar,
  RefreshControl,
} from 'react-native';
import RealmBackground from '../components/RealmBackground';
import XPProgressBar from '../components/XPProgressBar';
import StreakBadge from '../components/StreakBadge';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { getProfile } from '../api/profile';
import { calculateLevel } from '../utils/formatTime';
import { getAllRealms } from '../theme/realms';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const ProfileScreen = () => {
  const { theme, switchRealm, activeRealmId } = useTheme();
  const { colors } = theme;
  const { user } = useAuth();

  const [profile, setProfile] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadProfile = useCallback(async () => {
    try {
      const p = await getProfile();
      setProfile(p);
    } catch (err) {
      // Use cached data
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadProfile();
    setRefreshing(false);
  };

  const xp = profile?.xp || 0;
  const level = calculateLevel(xp);
  const allRealms = getAllRealms();
  const unlockedRealmIds = profile?.unlocked_realms
    ? JSON.parse(profile.unlocked_realms)
    : ['void', 'ember'];

  const handleSelectRealm = (realmId) => {
    if (unlockedRealmIds.includes(realmId)) {
      switchRealm(realmId);
    }
  };

  return (
    <RealmBackground>
      <StatusBar barStyle="light-content" backgroundColor={colors.background} />
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
        }
      >
        {/* Level Badge */}
        <View style={styles.levelSection}>
          <View style={[styles.levelBadge, { borderColor: colors.primary }]}>
            <Text style={[styles.levelNumber, { color: colors.primary }]}>
              {level}
            </Text>
          </View>
          <Text style={[styles.levelLabel, { color: colors.textSecondary }]}>
            LEVEL
          </Text>
          <Text style={[styles.email, { color: colors.textSecondary }]}>
            {user?.email || ''}
          </Text>
        </View>

        {/* XP Bar */}
        <View style={styles.xpSection}>
          <XPProgressBar xp={xp} />
          <Text style={[styles.totalXp, { color: colors.textSecondary }]}>
            {xp} TOTAL XP
          </Text>
        </View>

        {/* Streak */}
        <View style={styles.streakSection}>
          <StreakBadge
            currentStreak={profile?.current_streak || 0}
            longestStreak={profile?.longest_streak || 0}
          />
        </View>

        {/* Realm Collection */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          FOCUS REALMS
        </Text>
        <View style={styles.realmGrid}>
          {allRealms.map((r) => {
            const isUnlocked = unlockedRealmIds.includes(r.id);
            const isActive = activeRealmId === r.id;
            return (
              <TouchableOpacity
                key={r.id}
                onPress={() => handleSelectRealm(r.id)}
                disabled={!isUnlocked}
                style={[
                  styles.realmCard,
                  {
                    borderColor: isActive
                      ? r.colors.primary
                      : isUnlocked
                      ? r.colors.border + '88'
                      : colors.textSecondary + '33',
                    backgroundColor: isUnlocked
                      ? r.colors.background
                      : colors.surface + '44',
                    borderWidth: isActive ? 5 : 3,
                  },
                ]}
              >
                {/* Color swatch */}
                <View
                  style={[
                    styles.realmSwatch,
                    { backgroundColor: isUnlocked ? r.colors.primary : colors.textSecondary + '44' },
                  ]}
                />
                <Text
                  style={[
                    styles.realmName,
                    {
                      color: isUnlocked ? r.colors.primary : colors.textSecondary + '66',
                    },
                  ]}
                >
                  {r.name}
                </Text>
                {!isUnlocked && (
                  <Text style={[styles.realmLock, { color: colors.textSecondary + '88' }]}>
                    LVL {r.requiredLevel}
                  </Text>
                )}
                {isActive && (
                  <Text style={[styles.realmActive, { color: r.colors.primary }]}>
                    ACTIVE
                  </Text>
                )}
                <Text
                  style={[
                    styles.realmTagline,
                    {
                      color: isUnlocked
                        ? r.colors.text + 'AA'
                        : colors.textSecondary + '44',
                    },
                  ]}
                >
                  {r.tagline}
                </Text>
              </TouchableOpacity>
            );
          })}
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
  levelSection: {
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  levelBadge: {
    width: 100,
    height: 100,
    borderWidth: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  levelNumber: {
    ...typography.stat,
    fontSize: 48,
  },
  levelLabel: {
    ...typography.label,
    marginTop: spacing.sm,
  },
  email: {
    ...typography.caption,
    marginTop: spacing.xs,
    opacity: 0.5,
  },
  xpSection: {
    marginBottom: spacing.lg,
  },
  totalXp: {
    ...typography.caption,
    marginTop: spacing.xs,
    textAlign: 'right',
  },
  streakSection: {
    marginBottom: spacing.sectionGap,
  },
  sectionTitle: {
    ...typography.h2,
    marginBottom: spacing.md,
  },
  realmGrid: {
    gap: spacing.md,
  },
  realmCard: {
    padding: spacing.md,
  },
  realmSwatch: {
    width: 40,
    height: 6,
    marginBottom: spacing.sm,
  },
  realmName: {
    ...typography.h3,
    marginBottom: 2,
  },
  realmLock: {
    ...typography.label,
    fontSize: 10,
    marginTop: 2,
  },
  realmActive: {
    ...typography.label,
    fontSize: 10,
    marginTop: 2,
  },
  realmTagline: {
    ...typography.caption,
    fontSize: 10,
    marginTop: spacing.xs,
  },
});

export default ProfileScreen;
