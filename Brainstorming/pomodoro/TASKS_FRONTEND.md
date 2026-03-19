# Frontend Tasks — Deep Focus React Native App

## Phase 1: Project Setup
- [x] Initialize Expo React Native project
- [x] Install dependencies (react-navigation, axios, async-storage, etc.)
- [x] Set up folder structure
- [x] Configure navigation (Stack + Bottom Tabs)
- [x] Set up theme system with realm-based palettes
- [x] Create API client with JWT interceptor

## Phase 2: Auth Screens
- [x] Login screen (email, password, submit, link to register)
- [x] Register screen (email, password, confirm password, submit)
- [x] Auth context (store JWT, auto-login from storage)
- [x] Protected navigation (auth stack vs main stack)

## Phase 3: Timer Engine (Core)
- [x] Timer state machine (IDLE → FOCUSING → BREAK → cycle)
- [x] Countdown component with circular progress
- [x] Tag selector before session start
- [x] Intention input (optional)
- [x] Focus ritual animation (breathing countdown)
- [x] Background timer support
- [x] Session completion → POST to API
- [x] Auto-advance option

## Phase 4: Focus Realms
- [x] Realm definitions (colors, gradients, taglines)
- [x] Full-screen animated gradient backgrounds
- [x] Realm selector in profile/settings
- [x] Lock/unlock indicators based on level
- [x] Realm-aware theming across the app

## Phase 5: Profile & XP
- [x] Profile screen with level badge, XP progress bar
- [x] Streak display with flame icon
- [x] Realm collection grid (locked/unlocked)
- [x] Level-up celebration animation

## Phase 6: Analytics
- [x] Daily/Weekly/Monthly toggle
- [x] Focus time heatmap (calendar grid)
- [x] Tag breakdown (colored bars)
- [x] Distraction patterns chart
- [x] Session history list

## Phase 7: Settings
- [x] Timer duration sliders (focus, short break, long break)
- [x] Sessions before long break picker
- [x] Auto-advance toggle
- [x] Realm selection
- [x] Logout

## Phase 8: Distraction Journal
- [x] Break screen distraction prompt
- [x] Category picker (predefined + custom)
- [x] Free-text note
- [x] Submit to API

## Phase 9: Build Verification
- [x] npm install completes (876 packages)
- [x] Expo web export succeeds (563 modules bundled, 0 errors)
- [x] All 34 source files written
- [x] All 42 total files (including config) created

## Phase 10: PRD Gap Fixes (done)
- [x] Create OnboardingScreen with 3 swipeable cards (Focus Is A Muscle, Earn Your Realms, Track Your Growth)
- [x] Add OnboardingScreen as initial route in AuthNavigator (flow: Onboarding → Login ↔ Register)
- [x] Fix DistractionLogger sessionId: store lastSessionId in TimerContext, pass to BreakScreen
- [x] TagSelector now fetches custom tags from API on mount, merges with defaults (persists across restarts)
- [x] Wire offline session queueing: catch block in TimerContext calls queueSession(), syncPendingSessions on mount
- [x] Pause button calls POST /api/sessions/pause-penalty (fire-and-forget) to deduct 2 XP
- [x] Analytics period toggle now computes actual date_from/date_to and passes to API
- [x] Analytics tag breakdown uses server-side tag_breakdown from stats API (with client-side fallback)
- [x] Added STREAKS tab to Analytics with StreakBadge, longest streak, and session calendar heatmap
- [x] Expo web export succeeds (565 modules bundled, 0 errors) after all changes

---
**STATUS: COMPLETE** — All phases done, PRD gaps addressed, Expo build verified.

## Project Structure
```
frontend/
  App.js
  app.json
  package.json
  src/
    api/
      client.js        # Axios instance with JWT
      auth.js           # Auth API calls
      sessions.js       # Session API calls
      tags.js           # Tag API calls
      distractions.js   # Distraction API calls
      profile.js        # Profile API calls
    contexts/
      AuthContext.js     # Auth state + JWT management
      TimerContext.js    # Timer state machine
      ThemeContext.js    # Realm-based theming
    screens/
      LoginScreen.js
      RegisterScreen.js
      TimerScreen.js
      BreakScreen.js
      ProfileScreen.js
      AnalyticsScreen.js
      SettingsScreen.js
    components/
      CircularTimer.js
      RealmBackground.js
      XPProgressBar.js
      StreakBadge.js
      TagSelector.js
      IntentionInput.js
      DistractionLogger.js
      FocusRitual.js
      HeatmapCalendar.js
      StatCard.js
    theme/
      realms.js          # Realm definitions
      typography.js
      spacing.js
    navigation/
      AppNavigator.js
      AuthNavigator.js
      MainNavigator.js
    utils/
      storage.js         # AsyncStorage helpers
      formatTime.js
```
