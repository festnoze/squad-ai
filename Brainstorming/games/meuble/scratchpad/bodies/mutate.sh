#!/usr/bin/env bash
# Bodies agent: one combined mutation run of the Step29 tests, under the project Unity lock taken here, so no
# other agent's Unity run ever compiles the mutated files. The files are restored on any exit.
set -uo pipefail
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT" || exit 2
LOCK="$PROJECT/.unity.lock"
SCRATCH="$PROJECT/scratchpad/bodies"
FC="Assets/Scripts/Runtime/FurnitureController.cs"
LL="Assets/Scripts/Runtime/LampLight.cs"

while ! mkdir "$LOCK" 2>/dev/null; do sleep 5; done
WINPID="$(cat /proc/$$/winpid 2>/dev/null || echo $$)"
echo "$WINPID bodies mutation run" > "$LOCK/owner"

cp "$FC" "$SCRATCH/fc.bak"
cp "$LL" "$SCRATCH/ll.bak"
restore() {
  cp "$SCRATCH/fc.bak" "$FC"
  cp "$SCRATCH/ll.bak" "$LL"
  rm -rf "$LOCK"
}
trap restore EXIT INT TERM

sed -i 's|bool tips = bodies \&\& Body.Tips; // MUTATION:STOOL_TIP|bool tips = false; // MUTATION:STOOL_TIP|' "$FC"
sed -i 's|bool glides = bodies \&\& Body.Glides; // MUTATION:GLIDE|bool glides = false; // MUTATION:GLIDE|' "$FC"
sed -i 's|public float RangeFactor => On ? 1f : Tuning.LampOffLight; // MUTATION:LAMP_RANGE|public float RangeFactor => 1f; // MUTATION:LAMP_RANGE|' "$LL"
grep -c "MUTATION" "$FC" "$LL"
grep -n "tips = false\|glides = false" "$FC"
grep -n "RangeFactor => 1f" "$LL"

rm -f TestResults/bodies_mut.xml
MEUBLE_UNITY_LOCK_HELD=1 MEUBLE_AGENT=bodies tools/unity.sh test . --mode PlayMode --filter "Step29" --report-format junit \
  --output TestResults/bodies_mut.xml --timeout 1500 > "$SCRATCH/mut.out" 2>&1
echo "mutation test exit $?"
