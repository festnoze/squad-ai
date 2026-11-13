#!/usr/bin/env bash
# Retries the compile until other agents' errors are gone, then runs the Step29 PlayMode tests once.
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
OUT=scratchpad/bodies/retry.out
: > "$OUT"
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  MEUBLE_AGENT=bodies ./verify.sh compile > scratchpad/bodies/compile_retry.out 2>&1
  code=$?
  echo "attempt $attempt compile exit $code $(date +%H:%M:%S)" >> "$OUT"
  if [ $code -eq 0 ]; then
    rm -f TestResults/bodies.xml
    MEUBLE_AGENT=bodies tools/unity.sh test . --mode PlayMode --filter "Step29" --report-format junit \
      --output TestResults/bodies.xml --timeout 1500 > scratchpad/bodies/test_retry.out 2>&1
    echo "test exit $?" >> "$OUT"
    exit 0
  fi
  grep -E "error CS" scratchpad/bodies/compile_retry.out | sed 's/(.*//' | sort | uniq -c >> "$OUT"
  sleep 150
done
echo "gave up" >> "$OUT"
