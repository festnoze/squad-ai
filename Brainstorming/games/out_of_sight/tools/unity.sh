#!/usr/bin/env bash
# Runs the Unity CLI with an exclusive lock on this project.
#
# Unity refuses to open a project that another editor already has open, and several agents work
# on this project at the same time. Every Unity invocation (verify.sh, mutation.sh, agents) goes
# through this wrapper, which waits for its turn:
#
#   tools/unity.sh run . -- -executeMethod OutOfSight.Editor.Builder.SetupAndCompile -logFile x.log
#   tools/unity.sh test . --mode EditMode --filter "OutOfSight.Tests.CreakGaugeTests" --output r.xml
#
# The lock is a directory (mkdir is atomic on every file system). A lock older than 45 minutes,
# or held by a process that no longer exists, is considered stale and taken over.

set -uo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$PROJECT/.unity.lock"
export PATH="${LOCALAPPDATA:-}/Unity/bin:${PATH}"
export UNITY_NO_BANNER=1 UNITY_NO_PAGER=1 UNITY_NON_INTERACTIVE=1

# Re-entrant: verify.sh takes the lock once and its own calls pass straight through.
if [ "${OUTOFSIGHT_UNITY_LOCK_HELD:-}" = "1" ]; then
  exec unity "$@"
fi

# M5: a fair first come first served queue (tools/unity_wait.sh) replaces the bare mkdir loop.
. "$PROJECT/tools/unity_wait.sh"
unity_acquire
###################################################################################################
###################################################################################################
###################################################################################################
###################################################################################################
###################################################################################################
###################################################################################################
###################################################################################################
################################################################
WINPID="$(cat /proc/$$/winpid 2>/dev/null || echo $$)"
echo "$WINPID ${OUTOFSIGHT_AGENT:-shell} $*" > "$LOCK/owner"
trap 'rm -rf "$LOCK"' EXIT INT TERM

OUTOFSIGHT_UNITY_LOCK_HELD=1 unity "$@"
