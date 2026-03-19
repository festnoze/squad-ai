/**
 * OnboardingScreen — 3 swipe cards. Brutalist. Bold. No hand-holding.
 * Explains the concept, then sends you to login.
 */

import React, { useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
} from 'react-native';
import RealmBackground from '../components/RealmBackground';
import { useTheme } from '../contexts/ThemeContext';
import typography from '../theme/typography';
import spacing from '../theme/spacing';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

const SLIDES = [
  {
    id: '1',
    title: 'FOCUS IS\nA MUSCLE',
    description:
      'Train your focus with timed sessions. 25 minutes of deep work, then a short break. Repeat. Level up.',
  },
  {
    id: '2',
    title: 'EARN YOUR\nREALMS',
    description:
      'Every session earns XP. Build streaks. Unlock immersive Focus Realms as you level up.',
  },
  {
    id: '3',
    title: 'TRACK YOUR\nGROWTH',
    description:
      'See your focus patterns, identify distractions, and watch your productivity transform over time.',
  },
];

const OnboardingScreen = ({ navigation }) => {
  const { theme } = useTheme();
  const { colors } = theme;
  const flatListRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const goToLogin = useCallback(() => {
    navigation.replace('Login');
  }, [navigation]);

  const onViewableItemsChanged = useRef(({ viewableItems }) => {
    if (viewableItems.length > 0) {
      setActiveIndex(viewableItems[0].index);
    }
  }).current;

  const viewabilityConfig = useRef({
    viewAreaCoveragePercentThreshold: 50,
  }).current;

  const renderSlide = ({ item, index }) => {
    const isLast = index === SLIDES.length - 1;

    return (
      <View style={[styles.slide, { width: SCREEN_WIDTH }]}>
        <View style={styles.slideContent}>
          {/* Step indicator */}
          <Text style={[styles.stepLabel, { color: colors.textSecondary }]}>
            {`0${index + 1} / 0${SLIDES.length}`}
          </Text>

          {/* Title */}
          <Text style={[styles.title, { color: colors.primary }]}>
            {item.title}
          </Text>

          {/* Accent bar */}
          <View style={[styles.accentBar, { backgroundColor: colors.primary }]} />

          {/* Description */}
          <Text style={[styles.description, { color: colors.textSecondary }]}>
            {item.description}
          </Text>

          {/* GET STARTED button — only on last card */}
          {isLast && (
            <TouchableOpacity
              onPress={goToLogin}
              style={[styles.button, { backgroundColor: colors.buttonBg }]}
              activeOpacity={0.8}
            >
              <Text style={[styles.buttonText, { color: colors.buttonText }]}>
                GET STARTED
              </Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  };

  return (
    <RealmBackground>
      <View style={styles.container}>
        {/* Skip button */}
        <TouchableOpacity
          onPress={goToLogin}
          style={styles.skipButton}
          activeOpacity={0.7}
        >
          <Text style={[styles.skipText, { color: colors.textSecondary }]}>
            SKIP
          </Text>
        </TouchableOpacity>

        {/* Swipeable cards */}
        <FlatList
          ref={flatListRef}
          data={SLIDES}
          renderItem={renderSlide}
          keyExtractor={(item) => item.id}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          bounces={false}
          onViewableItemsChanged={onViewableItemsChanged}
          viewabilityConfig={viewabilityConfig}
        />

        {/* Dot indicators */}
        <View style={styles.pagination}>
          {SLIDES.map((_, index) => (
            <View
              key={index}
              style={[
                styles.dot,
                {
                  backgroundColor:
                    index === activeIndex ? colors.primary : colors.textSecondary + '44',
                  width: index === activeIndex ? 24 : 8,
                },
              ]}
            />
          ))}
        </View>
      </View>
    </RealmBackground>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  skipButton: {
    position: 'absolute',
    top: spacing.xxl,
    right: spacing.screenPadding,
    zIndex: 10,
    padding: spacing.sm,
  },
  skipText: {
    ...typography.label,
    letterSpacing: 3,
  },
  slide: {
    flex: 1,
    justifyContent: 'center',
  },
  slideContent: {
    paddingHorizontal: spacing.screenPadding,
  },
  stepLabel: {
    ...typography.mono,
    marginBottom: spacing.lg,
    letterSpacing: 2,
  },
  title: {
    ...typography.h1,
    fontSize: 42,
    lineHeight: 48,
    marginBottom: spacing.md,
  },
  accentBar: {
    height: spacing.borderWidthHeavy,
    width: 60,
    marginBottom: spacing.xl,
  },
  description: {
    ...typography.body,
    lineHeight: 26,
    marginBottom: spacing.xxl,
  },
  button: {
    padding: spacing.lg,
    alignItems: 'center',
    marginTop: spacing.md,
  },
  buttonText: {
    ...typography.button,
  },
  pagination: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingBottom: spacing.xxl,
    gap: spacing.sm,
  },
  dot: {
    height: 4,
    borderRadius: 0,
  },
});

export default OnboardingScreen;
