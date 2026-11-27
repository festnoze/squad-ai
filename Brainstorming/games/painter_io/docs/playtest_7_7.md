# Painter.io - device playtest record (brief 7.7)

Contract section 18.5. Template written by B6; **filled in by the user**. No agent may mark brief 7.7 as passed: until this
record is filled and signed below, Gate B reports 7.7 as `PENDING_HUMAN`.

What this playtest proves: that La Revanche is *readable and learnable* on a real phone. When a player's thread is cut,
they notice the spark (the retraction front), understand they must race home, and afterwards can say why they survived or
died. Since rule v1.4 (contract 24) a saved chased return keeps the player alive **but captures nothing**: the player should
also understand that the loop was lost.

---

## 1. Session

| Field | Value |
|---|---|
| Date | |
| Observer | |
| Player (first name or alias) | |
| Player profile (casual / regular mobile gamer / knows paper.io) | |
| Phone model and Android version | |
| Screen size and refresh rate (60 / 90 / 120 Hz) | |
| APK file and build date (`Build/Android/PainterIO.apk`) | |
| Language (FR / EN) | |
| Quality setting (Auto / Haute / Moyenne / Basse) | |
| `docs/verify_last.txt` OVERALL line of the build used | |

## 2. Setup

1. Build the APK (from the project root): `pwsh -NoProfile -File tools/verify.ps1 -Android -KeepGoing`
   (or only the Android step: `pwsh -NoProfile -File tools/verify.ps1 -Steps android`).
2. Install it: `adb install -r Build/Android/PainterIO.apk` (or copy the APK to the phone and open it).
3. Fresh start, so the tutorial shows: uninstall any previous build first, or clear the app data
   (Android settings > Apps > Painter.io > Storage > Clear data).
4. Sound and vibrations ON (Options). Phone in portrait, brightness normal, no battery saver.
5. Do **not** explain La Revanche, the spark or the lasso to the player. Only say: "Agrandis ton territoire, ne te fais pas
   avoir." The game's own tutorial bubbles are the only teaching.
6. The observer sits next to the player, watches the player's eyes and finger, and writes notes per round (section 4).

## 3. Protocol

- **Rounds 1 to 3: lasso OFF** (Options > Bonus lasso: off, the default). This is the first La Revanche trial the brief asks
  for (closing paragraph of the brief).
- **Rounds 4 to 6: lasso ON** (Options > Bonus lasso: on). Rings appear 15 s into the round, then 15 s after each pickup.
- Biome: Liquide for rounds 1 to 6 (the reference look). Optional extra rounds in Feu and Électricité (section 6).
- After each round, before the next one, ask question (c) (section 4) and write the answer **in the player's words**.
- If a round ends without the player's thread ever being cut, write "no cut" and keep going; add rounds until at least
  **3 rounds with a cut received** are recorded (rounds 1 to 6 still decide the lasso OFF / ON split).

### Observer checklist after the FIRST cut received in a round

- **(a) Look:** within 1 s of the cut, the player looks or points at the retraction front (the moving front of the
  retracting thread, with the droplet chain behind it) or at the spark edge chevron when the front is off screen.
- **(b) Turn home:** the player turns toward home (their own color) instead of continuing the loop.
- **(c) Explain:** after the round, the player explains why they survived or died, and the explanation matches the WHY line
  of the results screen:
  - saved: "Rentré 0,4 s avant l'étincelle : boucle perdue." / "Sauvé de justesse : boucle perdue." (the player should
    mention that the loop was lost);
  - caught: "<Couleur> t'a coupé : rattrapé à 2,3 m de chez toi.";
  - territory lost: "Ton dernier morceau de terrain a été pris.".

Score each item: **Y** (clearly yes), **P** (partly, hesitant or late), **N** (no).

## 4. Rounds

Copy one block per round.

### Round 1 (lasso OFF)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| v1.4: player understood the saved loop was lost (Y / P / N / not saved) | |
| Notes (hesitations, confusion, comments) | |

### Round 2 (lasso OFF)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| v1.4: player understood the saved loop was lost (Y / P / N / not saved) | |
| Notes | |

### Round 3 (lasso OFF)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| v1.4: player understood the saved loop was lost (Y / P / N / not saved) | |
| Notes | |

### Round 4 (lasso ON)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| Ring picked up? Pocket made? (count) | |
| Home stayed identifiable next to a pending pocket (Y / P / N) | |
| Notes | |

### Round 5 (lasso ON)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| Ring picked up? Pocket made? (count) | |
| Home stayed identifiable next to a pending pocket (Y / P / N) | |
| Notes | |

### Round 6 (lasso ON)

| Item | Value |
|---|---|
| Result rank and area | |
| Cut received? (time, by which color) | |
| (a) looked or pointed at the front within 1 s (Y / P / N) | |
| (b) turned toward home (Y / P / N) | |
| Outcome of the chase (saved / caught / no chase) | |
| WHY line shown on the results screen (copy it) | |
| (c) player's explanation, in their words | |
| (c) matches the WHY line (Y / P / N) | |
| Ring picked up? Pocket made? (count) | |
| Home stayed identifiable next to a pending pocket (Y / P / N) | |
| Notes | |

## 5. Lasso (after round 6, ask the player)

| Question | Answer |
|---|---|
| Did the lasso bonus make the trajectories more interesting? (Y / P / N + why) | |
| Did the player understand the lasso bubble ("Lasso ! Recroise ton fil pour enfermer une poche, puis rentre.")? | |
| Was home always identifiable with a pending pocket (stripes) on screen? | |
| Did a pocket get lost to a cut, and did the player understand why? | |

## 6. Biomes (optional extra rounds, contract 25)

Pick the biome on the menu cards. One round each is enough.

| Check | Feu | Électricité |
|---|---|---|
| The four player colors stay clearly distinguishable (Y / P / N) | | |
| Home, pending pocket and rival territory stay identifiable (Y / P / N) | | |
| During a chase, the spark / current packet is the brightest moving thing on screen (Y / P / N) | | |
| (a) after a cut, the player looked at the front within 1 s (Y / P / N) | | |
| The fill (fire spreading / electric discharge) reads as "I captured this" (Y / P / N) | | |
| Frame rate felt smooth (Y / P / N) | | |
| Notes | | |

## 7. Device checks (observer, any round)

| Check | Result (OK / problem + note) |
|---|---|
| Floating stick: steering feels responsive, no unwanted turns when lifting the finger | |
| Tapping the pause button or the rival label never steers the pearl | |
| Android back button: pauses in play, back to menu from results, "Quitter ?" in the menu | |
| Safe area: nothing hidden by the notch or the rounded corners | |
| Pause button and leaderboard toggle are easy to tap (96 px reference size) | |
| Vibrations: cut received, cut dealt, caught, saved return, capture | |
| Sounds: exit, return and fill, cut snap, spark tension rising, loop lost, ring chime | |
| Text is crisp and readable over every puddle color | |
| No stutter during fills and chases (or note when it happens) | |
| Battery / heat after 6 rounds (normal / warm / hot) | |
| App resumes correctly after switching away and back (pause panel shown) | |

## 8. Verdict (user)

Pass rule (the observer's judgement prevails; this is a guide): over the rounds with a cut received, (a) and (b) are Y in at
least 2 of 3 rounds, and (c) matches the WHY line in at least 2 of 3 rounds; with lasso ON, home stays identifiable.

| Item | Value |
|---|---|
| Rounds with a cut received | |
| (a) Y count / rounds with a cut | |
| (b) Y count / rounds with a cut | |
| (c) matches count / rounds with a cut | |
| Lasso enriches trajectories, home identifiable (Y / P / N) | |
| **Brief 7.7 verdict (PASS / FAIL / PENDING_HUMAN)** | PENDING_HUMAN |
| Main problems to fix (if any) | |
| Signed (user, date) | |
