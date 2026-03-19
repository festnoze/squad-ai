/**
 * AnalyticsScreen — Focus heatmap, tag breakdown, distraction patterns, session log, streaks.
 * Tab-based: Overview | Heatmap | Tags | Distractions | Streaks
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
import HeatmapCalendar from '../components/HeatmapCalendar';
import StreakBadge from '../components/StreakBadge';
import StatCard from '../components/StatCard';
import { useTheme } from '../contexts/ThemeContext';
import { getSessionStats, getSessions } from '../api/sessions';
import { getProfile } from '../api/profile';
import { getDistractionStats } from '../api/distractions';
import { formatMinutes } from '../utils/formatTime';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const TABS = ['OVERVIEW', 'HEATMAP', 'TAGS', 'DISTRACTIONS', 'STREAKS'];
const PERIODS = ['DAILY', 'WEEKLY', 'MONTHLY'];

/**
 * Compute date_from and date_to for a given period index.
 * Returns { date_from: 'YYYY-MM-DD', date_to: 'YYYY-MM-DD' }.
 */
const computeDateRange = (periodIndex) => {
  const today = new Date();
  const toDate = today.toISOString().split('T')[0];
  let fromDate;

  switch (periodIndex) {
    case 0: // DAILY
      fromDate = toDate;
      break;
    case 1: { // WEEKLY
      const weekAgo = new Date(today);
      weekAgo.setDate(weekAgo.getDate() - 7);
      fromDate = weekAgo.toISOString().split('T')[0];
      break;
    }
    case 2: { // MONTHLY
      const monthAgo = new Date(today);
      monthAgo.setDate(monthAgo.getDate() - 30);
      fromDate = monthAgo.toISOString().split('T')[0];
      break;
    }
    default: {
      const defaultWeekAgo = new Date(today);
      defaultWeekAgo.setDate(defaultWeekAgo.getDate() - 7);
      fromDate = defaultWeekAgo.toISOString().split('T')[0];
      break;
    }
  }

  return { date_from: fromDate, date_to: toDate };
};

const AnalyticsScreen = () => {
  const { theme } = useTheme();
  const { colors } = theme;

  const [activeTab, setActiveTab] = useState(0);
  const [activePeriod, setActivePeriod] = useState(1); // WEEKLY default
  const [stats, setStats] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [distractionData, setDistractionData] = useState(null);
  const [heatmapData, setHeatmapData] = useState({});
  const [profileData, setProfileData] = useState(null);
  const [streakHeatmapData, setStreakHeatmapData] = useState({});
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const dateRange = computeDateRange(activePeriod);

      const [statsRes, sessionsRes, distractionsRes, profileRes] = await Promise.all([
        getSessionStats(dateRange).catch(() => null),
        getSessions({ date_from: dateRange.date_from, date_to: dateRange.date_to, limit: 100 }).catch(() => []),
        getDistractionStats().catch(() => null),
        getProfile().catch(() => null),
      ]);
      if (statsRes) setStats(statsRes);
      if (Array.isArray(sessionsRes)) {
        setSessions(sessionsRes);
        // Build heatmap data from sessions (minutes per day)
        const hmap = {};
        // Build streak heatmap data (binary: 1 if any session that day)
        const smap = {};
        sessionsRes.forEach((s) => {
          const day = s.started_at?.split('T')[0];
          if (day) {
            hmap[day] = (hmap[day] || 0) + (s.duration_minutes || 0);
            smap[day] = 1;
          }
        });
        setHeatmapData(hmap);
        setStreakHeatmapData(smap);
      }
      if (distractionsRes) setDistractionData(distractionsRes);
      if (profileRes) setProfileData(profileRes);
    } catch (err) {
      // Silently fail
    }
  }, [activePeriod]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const renderOverview = () => (
    <View style={styles.tabContent}>
      {/* Period toggle */}
      <View style={styles.periodRow}>
        {PERIODS.map((p, i) => (
          <TouchableOpacity
            key={p}
            onPress={() => setActivePeriod(i)}
            style={[
              styles.periodButton,
              {
                borderColor: colors.border,
                backgroundColor:
                  activePeriod === i ? colors.primary : 'transparent',
              },
            ]}
          >
            <Text
              style={[
                styles.periodText,
                {
                  color:
                    activePeriod === i ? colors.buttonText : colors.textSecondary,
                },
              ]}
            >
              {p}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Stat cards */}
      <View style={styles.statRow}>
        <StatCard
          label="FOCUS TIME"
          value={formatMinutes(stats?.total_focus_minutes || 0)}
          accent
        />
        <StatCard
          label="SESSIONS"
          value={String(stats?.total_sessions || 0)}
        />
      </View>
      <View style={[styles.statRow, { marginTop: spacing.md }]}>
        <StatCard
          label="COMPLETED"
          value={String(stats?.completed_sessions || 0)}
        />
        <StatCard
          label="AVG LENGTH"
          value={formatMinutes(stats?.avg_duration || 0)}
        />
      </View>

      {/* Recent sessions */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>
        RECENT SESSIONS
      </Text>
      {sessions.slice(0, 5).map((s, i) => (
        <View
          key={s.id || i}
          style={[
            styles.sessionItem,
            { borderColor: colors.border, backgroundColor: colors.cardBg },
          ]}
        >
          <View style={styles.sessionRow}>
            <Text style={[styles.sessionTag, { color: colors.primary }]}>
              {(s.tag || 'UNTAGGED').toUpperCase()}
            </Text>
            <Text style={[styles.sessionDuration, { color: colors.text }]}>
              {s.duration_minutes}m
            </Text>
          </View>
          {s.intention && (
            <Text style={[styles.sessionIntention, { color: colors.textSecondary }]}>
              {s.intention}
            </Text>
          )}
          <Text style={[styles.sessionDate, { color: colors.textSecondary }]}>
            {s.started_at ? new Date(s.started_at).toLocaleDateString() : ''}
          </Text>
        </View>
      ))}
    </View>
  );

  const renderHeatmap = () => (
    <View style={styles.tabContent}>
      <HeatmapCalendar data={heatmapData} />
    </View>
  );

  const renderTags = () => {
    // Prefer tag_breakdown from API stats if available, fall back to client-side computation
    let tagMap;
    if (stats?.tag_breakdown && typeof stats.tag_breakdown === 'object' && Object.keys(stats.tag_breakdown).length > 0) {
      tagMap = { ...stats.tag_breakdown };
    } else {
      tagMap = {};
      sessions.forEach((s) => {
        const tag = s.tag || 'Untagged';
        tagMap[tag] = (tagMap[tag] || 0) + (s.duration_minutes || 0);
      });
    }

    const totalMinutes = Object.values(tagMap).reduce((a, b) => a + b, 0) || 1;
    const tagEntries = Object.entries(tagMap).sort((a, b) => b[1] - a[1]);

    return (
      <View style={styles.tabContent}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          TIME BY TAG
        </Text>
        {tagEntries.map(([tag, minutes]) => {
          const pct = (minutes / totalMinutes) * 100;
          return (
            <View key={tag} style={styles.tagBarContainer}>
              <View style={styles.tagBarLabel}>
                <Text style={[styles.tagBarName, { color: colors.text }]}>
                  {tag.toUpperCase()}
                </Text>
                <Text style={[styles.tagBarValue, { color: colors.textSecondary }]}>
                  {formatMinutes(minutes)}
                </Text>
              </View>
              <View
                style={[styles.tagBarTrack, { backgroundColor: colors.timerTrack, borderColor: colors.border }]}
              >
                <View
                  style={[
                    styles.tagBarFill,
                    {
                      width: `${pct}%`,
                      backgroundColor: colors.primary,
                    },
                  ]}
                />
              </View>
            </View>
          );
        })}
        {tagEntries.length === 0 && (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            NO DATA YET. COMPLETE SOME SESSIONS.
          </Text>
        )}
      </View>
    );
  };

  const renderDistractions = () => {
    const categories = distractionData?.categories || {};
    const entries = Object.entries(categories).sort((a, b) => b[1] - a[1]);
    const maxCount = entries.length > 0 ? entries[0][1] : 1;

    return (
      <View style={styles.tabContent}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          DISTRACTION PATTERNS
        </Text>
        {entries.map(([cat, count]) => (
          <View key={cat} style={styles.tagBarContainer}>
            <View style={styles.tagBarLabel}>
              <Text style={[styles.tagBarName, { color: colors.text }]}>
                {cat.toUpperCase()}
              </Text>
              <Text style={[styles.tagBarValue, { color: colors.textSecondary }]}>
                {count}x
              </Text>
            </View>
            <View
              style={[styles.tagBarTrack, { backgroundColor: colors.timerTrack, borderColor: colors.danger + '44' }]}
            >
              <View
                style={[
                  styles.tagBarFill,
                  {
                    width: `${(count / maxCount) * 100}%`,
                    backgroundColor: colors.danger,
                  },
                ]}
              />
            </View>
          </View>
        ))}
        {entries.length === 0 && (
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
            NO DISTRACTIONS LOGGED YET.
          </Text>
        )}
      </View>
    );
  };

  const renderStreaks = () => {
    const currentStreak = profileData?.current_streak || 0;
    const longestStreak = profileData?.longest_streak || 0;

    return (
      <View style={styles.tabContent}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          STREAK STATUS
        </Text>
        <StreakBadge
          currentStreak={currentStreak}
          longestStreak={longestStreak}
        />

        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          SESSION CALENDAR
        </Text>
        <HeatmapCalendar data={streakHeatmapData} />
      </View>
    );
  };

  const renderContent = () => {
    switch (activeTab) {
      case 0:
        return renderOverview();
      case 1:
        return renderHeatmap();
      case 2:
        return renderTags();
      case 3:
        return renderDistractions();
      case 4:
        return renderStreaks();
      default:
        return renderOverview();
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
        <Text style={[styles.pageTitle, { color: colors.text }]}>
          ANALYTICS
        </Text>

        {/* Tab bar */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.tabBar}
          contentContainerStyle={styles.tabBarContent}
        >
          {TABS.map((tab, i) => (
            <TouchableOpacity
              key={tab}
              onPress={() => setActiveTab(i)}
              style={[
                styles.tab,
                {
                  borderColor: colors.border,
                  borderBottomColor:
                    activeTab === i ? colors.primary : colors.border,
                  borderBottomWidth: activeTab === i ? 4 : 2,
                },
              ]}
            >
              <Text
                style={[
                  styles.tabText,
                  {
                    color:
                      activeTab === i ? colors.primary : colors.textSecondary,
                  },
                ]}
              >
                {tab}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {renderContent()}
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
  pageTitle: {
    ...typography.h1,
    marginBottom: spacing.md,
  },
  tabBar: {
    flexGrow: 0,
    marginBottom: spacing.lg,
  },
  tabBarContent: {
    gap: 0,
  },
  tab: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderWidth: 2,
  },
  tabText: {
    ...typography.caption,
    fontSize: 11,
  },
  tabContent: {
    flex: 1,
  },
  periodRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  periodButton: {
    flex: 1,
    borderWidth: 2,
    paddingVertical: spacing.sm,
    alignItems: 'center',
  },
  periodText: {
    ...typography.caption,
    fontSize: 11,
  },
  statRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  sectionTitle: {
    ...typography.h3,
    marginTop: spacing.sectionGap,
    marginBottom: spacing.md,
  },
  sessionItem: {
    borderWidth: 2,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  sessionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sessionTag: {
    ...typography.caption,
    fontSize: 12,
  },
  sessionDuration: {
    ...typography.mono,
    fontWeight: '700',
  },
  sessionIntention: {
    ...typography.body,
    fontSize: 13,
    marginTop: spacing.xs,
  },
  sessionDate: {
    ...typography.caption,
    fontSize: 10,
    marginTop: spacing.xs,
  },
  tagBarContainer: {
    marginBottom: spacing.md,
  },
  tagBarLabel: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  tagBarName: {
    ...typography.caption,
    fontSize: 12,
  },
  tagBarValue: {
    ...typography.caption,
    fontSize: 12,
  },
  tagBarTrack: {
    height: 20,
    borderWidth: 2,
    overflow: 'hidden',
  },
  tagBarFill: {
    height: '100%',
  },
  emptyText: {
    ...typography.body,
    textAlign: 'center',
    marginTop: spacing.xl,
  },
});

export default AnalyticsScreen;
