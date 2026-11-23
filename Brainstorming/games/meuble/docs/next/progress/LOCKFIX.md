# LOCKFIX progress (tools/unity.ps1 lock)

Agent LOCKFIX, 2026-11-22. Only `tools/unity.ps1` changed (replaced in one atomic Move-Item while other agents were
running). CLI unchanged: `-Agent`, `-UnityArgs`, exit code of Unity, Unity output untouched, nothing extra printed.

## Bugs in the old version

- Staleness of an ownerless lock was judged from the lock folder's creation time (wrong when Windows keeps an old
  creation time on a re-created name; on this machine tunneling showed up on files, not on folders, but the date is
  unreliable anyway).
- `New-Item -ItemType Directory` checks then creates: two waiters could both "win" and run Unity together.
- The owner file was written after the folder existed and not atomically, so a waiter could read it empty.
- The release removed the lock without checking it was still its own.

## New design

- Acquire: the lock folder is built with its owner file under `Logs/` then renamed to `.unity.lock` in one step
  (the rename fails when the lock exists). A lock is never seen without its owner.
- Owner file: first line unchanged `<pid> <agent> <args>` (read by tools/unity.sh and older copies), then
  `format=2`, `token`, `pid`, `start` (process start time, UTC ticks), `host`, `heartbeat`, `children` (Unity
  processes launched by the holder, `pid:start`). Always rewritten through a temp file and an atomic rename.
- Pin: the holder keeps `.unity.lock/pin` open without delete sharing, so Windows refuses to rename or delete a live
  lock folder, whatever the waiter (new, old copy, tools/unity.sh).
- Heartbeat thread (background runspace): every 20 s (first after 3 s) refreshes `heartbeat` and `children`;
  restores the owner if an old waiter deleted it; stops if another token appears.
- Waiter verdict, from the owner file only: live while the owner pid runs with the same start time, or one of its
  Unity children does, or the heartbeat is under 90 s old. Other host: heartbeat only. Old format owner: live while
  its pid runs or the folder was written in the last 150 s. No owner: 60 s grace on the waiter's own clock.
- Takeover: stale verdict twice in a row on the same owner text, re-read just before, rename to `Logs/`, give it
  back if it changed hands. Logged in `Logs/unity-lock.log` (takeovers and anomalies only).
- Release: only if the owner token is still ours.

## Tests (isolated, scratch lock folder, fake Unity, short timings, 33/33 pass)

Single run (exit code, output, clean release), heartbeat and children refresh, 5 concurrent copies without overlap,
mixed old and new copies without overlap, dead owner, dead owner with fresh heartbeat, pid reused, live owner with a
2020 creation time, ownerless lock with a 2020 creation time, old format live and dead, owner dead but Unity child
alive, wrapper killed while its Unity runs, rename and delete blocked on a live lock, overwritten owner left alone,
owner on another host. Scripts kept in the session scratchpad (`lockfix/test.ps1`), not in the repo.

## A VERIFIER

- Next real Unity runs through `tools/unity.ps1`: owner file has the `format=2` lines and `children=` fills in after
  a few seconds; `.unity.lock` disappears at the end and no `Logs/unity-lock-*` folder is left behind.
- `Logs/unity-lock.log` stays empty in normal use; any "took over" line must match a really dead holder.
- Jobs started before the swap still run the old code in memory until they end (an old waiter can still misjudge an
  ownerless lock, but cannot delete a pinned new lock).
- tools/unity.sh and tools/unity_wait.sh were not changed: bash holders still use the old format (recognised).
