# Backend Tasks — Deep Focus API

## Phase 1: Project Setup
- [x] Initialize FastAPI project with folder structure
- [x] Set up SQLAlchemy with SQLite
- [x] Create database models (users, sessions, distractions, tags)
- [x] Set up Alembic or auto-create tables
- [x] Create Pydantic schemas for all endpoints
- [x] Set up JWT auth utilities (hashing, token creation/verification)

## Phase 2: Auth Endpoints
- [x] POST /api/auth/register — create user, hash password, return JWT
- [x] POST /api/auth/login — verify credentials, return JWT
- [x] GET /api/auth/me — return current user from JWT
- [x] Auth dependency for protected routes

## Phase 3: Core Session Endpoints
- [x] POST /api/sessions — log a completed session, calculate XP, update streak
- [x] GET /api/sessions — list sessions with date/tag filters
- [x] GET /api/sessions/stats — aggregated stats (total time, count, streaks, daily breakdown)
- [x] XP calculation logic with streak multipliers
- [x] Streak calculation (consecutive days detection, reset on miss)
- [x] Realm unlocking logic based on level thresholds

## Phase 4: Tags & Distractions
- [x] GET /api/tags — list user tags (include defaults)
- [x] POST /api/tags — create custom tag
- [x] POST /api/distractions — log distraction
- [x] GET /api/distractions/stats — category breakdown analytics

## Phase 5: Profile & Settings
- [x] GET /api/profile — full profile with XP, level, streak, realms
- [x] PUT /api/profile/settings — update timer config and active realm

## Phase 6: Tests
- [x] Test auth flow (register, login, protected routes)
- [x] Test session creation and XP/streak logic
- [x] Test analytics aggregation
- [x] Test tag and distraction CRUD
- [x] Test profile and settings

## Phase 7: Integration Verification
- [x] All 50 unit tests passing (pytest)
- [x] Live server starts on uvicorn
- [x] Register endpoint returns JWT
- [x] Login endpoint returns JWT
- [x] Session creation returns XP earned (15 XP with streak bonus)
- [x] Profile returns level, XP, streak, unlocked realms
- [x] Tags auto-seed 5 defaults on first GET
- [x] Stats aggregation returns daily breakdown
- [x] Swagger docs served at /docs

## Phase 8: PRD Gap Fixes (done)
- [x] Fix distraction stats field name: renamed `by_category` to `categories` in schema and router
- [x] Add `avg_duration` field to SessionStats (computed from completed sessions)
- [x] Add `tag_breakdown` dict to SessionStats (server-side tag-to-minutes aggregation)
- [x] Add `limit` query parameter to GET /api/sessions
- [x] Add `period` query parameter to GET /api/sessions/stats (daily/weekly/monthly date range)
- [x] Full-cycle XP bonus: +25 XP when completing N focus sessions per day (N = sessions_before_long_break)
- [x] POST /api/sessions/pause-penalty: deducts 2 XP on pause (minimum 0), re-evaluates realm locks
- [x] Realm locking: `_lock_realms` removes realms when user level drops below threshold (XP decrease via pause)
- [x] PausePenaltyOut response schema added
- [x] Updated distraction test assertions from `by_category` to `categories`
- [x] All 50 tests still green after changes

---
**STATUS: COMPLETE** — All phases done, 50/50 tests green, PRD gaps addressed.

## Project Structure
```
backend/
  app/
    __init__.py
    main.py          # FastAPI app, CORS, startup
    database.py      # SQLAlchemy engine, session, Base
    models.py        # ORM models
    schemas.py       # Pydantic models
    auth.py          # JWT + password utils
    dependencies.py  # get_current_user dependency
    routers/
      __init__.py
      auth.py
      sessions.py
      tags.py
      distractions.py
      profile.py
  tests/
    __init__.py
    conftest.py      # test client, test DB
    test_auth.py
    test_sessions.py
    test_tags.py
    test_distractions.py
    test_profile.py
  requirements.txt
```
