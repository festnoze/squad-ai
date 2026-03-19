# DEEP FOCUS - Pomodoro Reimagined
## Product Requirements Document

---

## Vision
**Deep Focus** is not another Pomodoro timer. It's a ritualistic focus companion that turns deep work into an immersive, gamified experience. Think "Dark Souls meets a productivity app" — punishing breaks in focus, rewarding relentless streaks, and wrapping it all in a brutalist, bold UI that makes you *feel* like a productivity warrior.

---

## Core Concept: "Focus is a Muscle"

The app treats focus like a skill tree in an RPG. Every completed session earns XP. Consecutive days build streaks that unlock new "Focus Realms" (themed timer environments). Breaking a streak has consequences — your realm resets. The stakes are real. The dopamine is earned.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React Native (Expo) — Android target |
| Backend | FastAPI (Python 3.11+) |
| Database | SQLite via SQLAlchemy |
| Auth | JWT (simple email/password) |
| State | React Context + useReducer |

---

## Features

### 1. The Timer Engine (Core)
- **Focus Session**: Default 25 min, configurable 1-90 min
- **Short Break**: Default 5 min, configurable 1-30 min
- **Long Break**: Default 15 min, after every 4 sessions, configurable
- **Session States**: IDLE → FOCUSING → BREAK → FOCUSING → ... → LONG_BREAK
- **Auto-advance**: Option to auto-start next phase or wait for manual trigger
- **Background timer**: Runs via background task, push notification on completion
- **Haptic pulse**: Subtle vibration every 5 minutes as a "still here" nudge

### 2. Focus Realms (Themes)
Each realm is a full-screen immersive theme with:
- Animated gradient background
- Unique color palette
- Motivational tagline

**Starter Realms (unlocked by default):**
- **Void** — Pure black with a white timer. Minimal. Brutal.
- **Ember** — Deep reds and oranges. "Burn through the noise."

**Unlockable Realms (earned via XP):**
- **Glacier** — Icy blues and whites. Unlocked at Level 5.
- **Neon** — Cyberpunk pinks and purples. Unlocked at Level 10.
- **Forest** — Deep greens, earthy tones. Unlocked at Level 15.
- **Cosmos** — Star-field animation. Unlocked at Level 25.

### 3. XP & Leveling System
- **+10 XP** per completed focus session
- **+5 XP** bonus per session in an active streak
- **+25 XP** for completing a full cycle (4 focus + breaks)
- **Streak multiplier**: Day 3+ = 1.5x, Day 7+ = 2x, Day 14+ = 3x
- **Level thresholds**: Level = floor(sqrt(totalXP / 10))
- **Streak death**: Missing a day resets streak to 0. Realm locks if you drop below its required level (re-earn it).

### 4. Session Tagging & Intentions
Before each focus session, the user sets:
- **Tag**: Work, Study, Creative, Health, Side Project (custom tags allowed)
- **Intention** (optional): Free-text "What will you accomplish?" — shown during the session as a persistent reminder

### 5. Distraction Journal
During a break, the user can log:
- What broke their focus (predefined: Phone, Social Media, Noise, Hunger, Wandering Mind, Other)
- Free-text note
- The app tracks distraction patterns over time in analytics

### 6. Analytics Dashboard
- **Daily/Weekly/Monthly** views
- **Focus time heatmap**: Calendar grid showing daily focus minutes (color intensity)
- **Tag breakdown**: Pie chart of time per tag
- **Distraction patterns**: Bar chart of most common distractions
- **Streak history**: Longest streak, current streak, streak calendar
- **Session log**: Scrollable list of past sessions with tags, durations, intentions

### 7. Daily Rituals
- **Focus Ritual (session start)**: 3-second breathing animation + intention display
- **Break Ritual**: Random micro-challenge (stretch prompt, hydration reminder, eye rest 20-20-20 rule)
- **End-of-day summary**: Push notification with daily stats

### 8. User Account & Sync
- Email/password registration and login
- JWT-based auth
- All data synced to backend
- Offline-first: timer works offline, syncs when connected

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/register | Create account |
| POST | /api/auth/login | Login, get JWT |
| GET | /api/auth/me | Get current user profile |

### Sessions
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/sessions | Create a completed session |
| GET | /api/sessions | List sessions (with filters: date range, tag) |
| GET | /api/sessions/stats | Aggregated stats (total focus time, count, streaks) |

### Tags
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/tags | List user's tags |
| POST | /api/tags | Create custom tag |

### Distractions
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/distractions | Log a distraction |
| GET | /api/distractions/stats | Distraction analytics |

### User Profile & Progress
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/profile | XP, level, streak, unlocked realms |
| PUT | /api/profile/settings | Update timer settings |

---

## Database Schema

### users
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| email | TEXT UNIQUE | |
| password_hash | TEXT | bcrypt |
| created_at | DATETIME | |
| xp | INTEGER | Default 0 |
| current_streak | INTEGER | Default 0 |
| longest_streak | INTEGER | Default 0 |
| last_session_date | DATE | For streak calc |
| focus_duration | INTEGER | Default 25 (min) |
| short_break_duration | INTEGER | Default 5 |
| long_break_duration | INTEGER | Default 15 |
| sessions_before_long_break | INTEGER | Default 4 |
| auto_advance | BOOLEAN | Default false |
| unlocked_realms | TEXT | JSON array of realm IDs |
| active_realm | TEXT | Default "void" |

### sessions
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| tag | TEXT | |
| intention | TEXT | Nullable |
| duration_minutes | INTEGER | Actual duration |
| completed | BOOLEAN | Did they finish? |
| started_at | DATETIME | |
| ended_at | DATETIME | |
| session_type | TEXT | "focus", "short_break", "long_break" |

### distractions
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| session_id | INTEGER FK | Nullable |
| category | TEXT | Predefined categories |
| note | TEXT | Free text |
| created_at | DATETIME | |

### tags
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | |
| name | TEXT | |
| color | TEXT | Hex color |

---

## UI Screens

1. **Onboarding** — 3 swipe cards explaining the concept, then register/login
2. **Home (Timer)** — Full-screen realm background, large circular timer, tag selector, intention input, start button
3. **Active Session** — Immersive realm, timer countdown, intention text, pause button (pausing costs 2 XP)
4. **Break Screen** — Break timer, distraction log prompt, micro-challenge
5. **Profile** — Avatar/level badge, XP bar, streak flame, realm collection grid
6. **Analytics** — Tab-based: Overview, Focus Heatmap, Tags, Distractions
7. **Settings** — Timer durations, auto-advance toggle, realm selection, account

---

## Design Language
- **Typography**: Bold, monospace for timer. Sans-serif for everything else.
- **Colors**: Each realm defines the palette. Default (Void) is pure B&W.
- **Animations**: Smooth gradient transitions, pulse effects on timer, particle effects on level-up.
- **Philosophy**: Brutalist minimalism. No clutter. Every pixel earns its place.
