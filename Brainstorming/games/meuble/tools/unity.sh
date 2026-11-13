#!/usr/bin/env bash
# Runs the Unity CLI with an exclusive lock on this project.
#
# Unity refuses to open a project that another editor already has open, and several agents work
# on this project at the same time. Every Unity invocation (verify.sh, mutation.sh, agents) goes
# through this wrapper, which waits for its turn:
#
#   tools/unity.sh run . -- -executeMethod Meuble.Editor.Builder.SetupAndCompile -logFile x.log
#   tools/unity.sh test . --mode EditMode --filter "Meuble.Tests.CreakGaugeTests" --output r.xml
#
# The lock is a directory (mkdir is atomic on every file system). A lock older than 45 minutes,
# or held by a process that no longer exists, is considered stale and taken over.

set -uo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$PROJECT/.unity.lock"
export PATH="${LOCALAPPDATA:-}/Unity/bin:${PATH}"
export UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1

# Re-entrant: verify.sh takes the lock once and its own calls pass straight through.
if [ "${MEUBLE_UNITY_LOCK_HELD:-}" = "1" ]; then
  exec unity "$@"
fi

waited=0
while ! mkdir "$LOCK" 2>/dev/null; do
  holder="$(cat "$LOCK/owner" 2>/dev/null || true)"
  pid="${holder%% *}"
  age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || date +%s) ))
  # The owner line starts with the WINDOWS pid of the holder: each agent runs its own Git Bash, whose
  # MSYS pids are invisible to the others, so `kill -0` called a live lock stale (M3 incident).
  alive=1
  if [ -n "$pid" ] && [ "$age" -gt 30 ]; then
    if ! tasklist //FI "PID eq $pid" //NH 2>/dev/null | grep -q " $pid "; then
      alive=0
    fi
  fi
  if [ "$age" -gt 2700 ] || [ "$alive" -eq 0 ]; then
    echo "[unity.sh] stale lock (age ${age}s, holder '${holder}'), taking it over" >&2
    rm -rf "$LOCK"
    continue
  fi
  if [ $((waited % 60)) -eq 0 ]; then
    echo "[unity.sh] waiting for the Unity lock held by: ${holder:-unknown} (${waited}s)" >&2
  fi
  sleep 5
  waited=$((waited + 5))
done
WINPID="$(cat /proc/$$/winpid 2>/dev/null || echo $$)"
echo "$WINPID ${MEUBLE_AGENT:-shell} $*" > "$LOCK/owner"
trap 'rm -rf "$LOCK"' EXIT INT TERM

MEUBLE_UNITY_LOCK_HELD=1 unity "$@"
