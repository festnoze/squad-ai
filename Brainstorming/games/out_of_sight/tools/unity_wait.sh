# Sourced by tools/unity.sh: unity_acquire waits for the Unity lock in a fair, first come first served
# queue, then takes it.
#
# Why a queue: the lock is a directory taken with mkdir, polled every 5 s by every waiting agent. Without
# a queue, whoever polls first after a release wins, and an agent can lose its turn many times in a row
# (seen in M5: the core agent lost five turns while the audit and ui-save agents took them back and forth).
#
# Each waiter drops a ticket named <epoch nanoseconds>-<windows pid> in .unity.queue/ and may take the lock
# only when its ticket is the oldest. A ticket whose process is dead is dropped when it reaches the head.
# The holder refreshes the lock's timestamp every 30 s (a heartbeat), so a lock is stale only when its
# heartbeat is over 150 s old AND its holder looks dead: tasklist alone misread live holders as dead under
# load (two takeovers seen in M5). A 4 hour ceiling only recovers from a wedged process.
# Expects PROJECT and LOCK to be set.

unity_alive() {
  local pid="$1"
  [ -n "$pid" ] && tasklist //FI "PID eq $pid" //NH 2>/dev/null | grep -q " $pid "
}

# Touches the lock every 30 s while this script's process lives and the lock is still ours.
unity_heartbeat() {
  local me="$1" parent=$$
  while kill -0 "$parent" 2>/dev/null && [ -d "$LOCK" ]; do
    sleep 30
    case "$(cat "$LOCK/owner" 2>/dev/null)" in
      "$me "*) touch -c "$LOCK" 2>/dev/null ;;
      *) [ -f "$LOCK/owner" ] && return 0 ;;
    esac
  done
}

unity_acquire() {
  local queue="$PROJECT/.unity.queue" me ticket head hpid holder pid age waited=0
  me="$(cat /proc/$$/winpid 2>/dev/null || echo $$)"
  mkdir -p "$queue"
  ticket="$queue/$(date +%s%N)-$me"
  : > "$ticket"
  while :; do
    # A flaky tasklist may have pruned this live ticket: put it back, with its original place.
    [ -f "$ticket" ] || : > "$ticket"
    head="$(ls "$queue" 2>/dev/null | sort | head -1)"
    if [ "$queue/$head" = "$ticket" ]; then
      if mkdir "$LOCK" 2>/dev/null; then
        rm -f "$ticket"
        # Detached from stdout and stderr, or a caller piping unity.sh would wait for it.
        unity_heartbeat "$me" </dev/null >/dev/null 2>&1 &
        return 0
      fi
    elif [ -n "$head" ]; then
      hpid="${head##*-}"
      if ! unity_alive "$hpid"; then
        rm -f "$queue/$head"
        continue
      fi
    fi
    if [ -d "$LOCK" ]; then
      holder="$(cat "$LOCK/owner" 2>/dev/null || true)"
      pid="${holder%% *}"
      age=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || date +%s) ))
      if [ "$age" -gt 14400 ] || { [ "$age" -gt 150 ] && ! unity_alive "$pid"; }; then
        echo "[unity.sh] stale lock (age ${age}s, holder '${holder}'), taking it over" >&2
        rm -rf "$LOCK"
        continue
      fi
    fi
    if [ $((waited % 60)) -eq 0 ]; then
      echo "[unity.sh] waiting in the queue ($(ls "$queue" | wc -l) ticket(s)); lock held by: ${holder:-nobody} (${waited}s)" >&2
    fi
    sleep 5
    waited=$((waited + 5))
  done
}
