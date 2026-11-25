# BIGBUTTONS: bigger, rearranged menu buttons on mobile (2026-11-25)

User request: "on mobile, make buttons bigger and rearrange them if needed to take more space (on main / pause / next
level or retry menus)". Mobile only; the PC layout stays exactly as it was.

## 1. The switch

- `TouchLayout.Active` (new, `Assets/Scripts/Runtime/TouchLayout.cs`) = `InputReader.TouchUIActive` (the touch UI's own
  switch: a test's `ForceTouchUI`, the `-touch` argument, or a finger was the last input) **or** a phone/tablet build
  (`Application.platform` Android or iPhonePlayer, never the editor). The platform part exists so the very first tap
  on the title of a phone session never lands on a layout that changes under the finger (`TouchUIActive` is false
  until a finger lands). Marker `MUTATION:TOUCH_LAYOUT_GATE`.
- `TouchLayout.Watch` (one per screen owner: Menu, Hud) is polled once a frame (`Menu.Update`, `Hud.Update`, and once at
  the end of each `Init`). It says "lay out again" when the wanted mode changes, but waits while a finger or the left
  mouse button is held (so the tap that turned touch on, on a Windows touchscreen, still clicks the button it pressed),
  and, in touch mode, when the screen size or `Screen.safeArea` changes (rotation to the other landscape side).
  It starts in PC mode, so a PC run without touch never lays anything out again.
- `TouchLayout.Memory` remembers the PC values (anchors, pivot, position, size of a rect; size and alignment of a
  label) the first time the touch layout changes them, and puts them back exactly when touch ends. The end panels'
  rows are computed for both modes instead (their PC row depends on the panel state).
- Safe area: `TouchLayout.SafeInsets()` converts `Screen.safeArea` to reference units (1920 x 1080, match 0.5). Left
  columns start at `max(PC margin, left inset + 40)`, bottom rows sit above the bottom inset, top-right items stay
  clear of the right and top insets. `TouchLayout.CanvasHeight()` and `FitRows` shrink a grid's rows (never under
  96 units) only when a screen is shorter than a 21:9 phone.
- Public probes: `Menu.TouchLayoutOn`, `Hud.TouchLayoutOn`, `RecordLine.TouchLayoutOn`, `ShopPage.TouchLayoutOn`.
- Names, labels, ids and the up/down navigation chains are unchanged everywhere; grids only add left/right links.

## 2. Sizes per screen (touch layout; reference units, 966 units = a 20:9 phone's height, about 69 mm)

| Screen | PC button (h, label) | Touch button (h, label) | Touch share of a 20:9 phone's height |
|---|---|---|---|
| Title page | 420 x 70, 44 | Jouer 884 x 126, 64; others 430 x 126, 56 | 13 % (about 9 mm) |
| Title Shop button | 320 x 72 | 420 x 116, 56 | 12 % |
| Pause menu | 420 x 78, 44 | 680 x 140, 60 | 14.5 % (about 10 mm) |
| Fail / win / end panels | 540 x 186 (50) and 450 x 170 (42) | 580 x 210 (64 bold) and 470 x 190 (54) | 22 % and 20 % (14 to 15 mm) |
| Options rows | 820 or 420 x 62, 34 / 42 | 716 x 112, 38 / 46, icons 60 (52) | 11.6 % |
| Credits Retour | 420 x 62, 42 | 480 x 112, 48 | 11.6 % |
| Shop products | 820 x 86, 34 / 22 / 34 | 940 x 108, 38 / 26 / 40 | 11 % |
| Shop Restore / privacy / Back | 420 x 62, 34 | 520 / 540 / 300 x 104, 40 | 10.8 % |

## 3. Layout per screen in touch mode

- **Title page** (`MenuTouchLayout.cs`): a grid under the tagline (top at y -20): Jouer across both columns, then
  Niveaux | Options, then Crédits | Quitter (rows 126 high, 20 apart, bottom at y -438, clear of a 21:9 phone's
  bottom at -471). Labels centred. The author line moves to the bottom right corner (its bottom-left place is under the
  grid now). The Shop button stays top right, bigger. Logo, title, rule and tagline unchanged. Navigation: up/down keep
  the PC cycle (Jouer, Niveaux, Options, Crédits, Quitter, Shop above Jouer); left/right now also cross each grid row
  (Niveaux <-> Options, Crédits <-> Quitter), the right column's right still goes to Shop.
- **Pause menu**: same single column and order (Reprendre, Recommencer, Menu principal / Choix du niveau, Options),
  680 x 140, 20 apart from y 190 down to -430; PAUSE and its rule moved up (y 318 and 228) to make room.
- **Fail / win / end panels** (`HudTouchLayout.cs`, `Hud.PlaceButtons`): each row becomes a bottom bar anchored to the
  bottom of the screen, 28 units above the bottom safe inset; same order and roles (primary first, larger, bold, red).
  Win row 580 + 470 + 470 + 2 x 32 = 1584 wide. All text lines keep their places (title y 120, time y -10, stars right
  of the time, hint y -110, win.next y -170), so the bar (top at most 238 above the bottom edge) is under all of them.
  Two moves: the record line ("Record : 12,3 s" and "Nouveau record !", `RecordLine.cs`) leaves its PC place under the
  buttons for the time's own row, right aligned left of the time (mirroring the stars on the right), "Nouveau record !"
  under it; the end screen's hint line goes from y -150 to -190 (under the new record and new stars lines).
- **Options**: two columns 716 wide, 28 apart: Sensibilité, Volume, Musique, Cône, Murs, Opacité on the left; Qualité,
  Difficulté, Langue, Par défaut, Retour on the right; rows 112 high, 16 apart, from y 350 down to -402 (clear of the
  music credits line). The band widens behind both columns. Up/down keep the PC chain; left/right cross to the row
  beside (the left column's last row goes to Retour).
- **Credits**: Retour 480 x 112 (centre y -392), the scroll view ends 14 above it.
- **Shop** (`ShopPage.SetTouchLayout`, called by Menu): product rows 940 x 108 from y 340 (up to five, down to -256);
  Restaurer les achats, Confidentialité des pubs (when offered) and Retour side by side in one bottom row (centre
  y -392), the status line between the two. Up/down keep the PC chain; left/right walk the bottom row.
- Not touched: the level select (another task), the in-game touch overlay, the HUD play band.

## 4. Fits checked (reasoning, CanvasScaler 1920 x 1080 at match 0.5)

Canvas sizes: 16:9 1920 x 1080; 19.5:9 2120 x 978; 20:9 2147 x 966; 21:9 2200 x 943 (the shortest); 16:10 1822 x 1138;
4:3 1663 x 1247 (the narrowest).

- Widths: title grid ends at x 1034 (band 1240); pause column at 830; Options right column at 1610 and the Shop bottom
  row at 1558, both inside 1663 - 16; the end bar 1584 centred (39 units to spare each side at 4:3, about 280 on a
  phone, more than a notch).
- Heights: every bottom row clears a 21:9 phone's bottom edge by 23 units or more; tops clear the titles above.
- Labels (DM Serif Display / LegacyRuntime advances measured with fontTools): longest French end label "Menu principal"
  at 64 bold about 460 for a 556 room (secondary at 54: 361 for 446); pause "Choix du niveau" at 60: 428 for 616;
  Options "Language / Langue : Français" at 38: 505 for 524; Shop description "Sans pub et tous les niveaux débloqués,
  pour moins cher." at 26: 668 for 704; "Confidentialité des pubs" at 40: 427 for 540.

## 5. Files

- New: `Assets/Scripts/Runtime/TouchLayout.cs`, `MenuTouchLayout.cs` (partial Menu), `HudTouchLayout.cs` (partial Hud).
- Edited: `Menu.cs` (`partial`, two `RefreshTouchLayout()` calls), `Hud.cs` (`partial`, `PlaceRow`/`PlaceButtons`
  per mode, `RefreshPanelLayout()` in `Init` and `Update`, the end hint height), `RecordLine.cs` (touch placement),
  `Monetization/ShopPage.cs` (touch layout), `Assets/Tests/PlayMode/ProbeTestsEndPanel.cs` (asserts the touch layout is
  on and every panel button is at least 15 % of the canvas height on touch).

## 6. How to check

- Compile: `SetupAndCompile` clean (Build/bigbuttons.log, Build/bigbuttons2.log).
- Tests to run: PlayMode `ProbeTestsEndPanel` (the touch bar at 20:9, 16:9 and 4:3, screenshots in
  Build/shots/endpanel), then the PC regressions `ProbeTestsM3Look|ProbeTestsM5Ui|ProbeTestsStars|ProbeTestsCredits|
  ProbeTestsM6Options|ProbeTestsOptionsIcons|ProbeTestsM7Walls|ProbeTestsAudioOverhaul|ProbeTestsM7Touch|
  ProbeTestsTouchTuto|ProbeTestsHeldStart|ProbeTestsBars`.
- By hand on PC: rebuild the player, then `Build/Play/OutOfSight.exe -touch` (title grid, pause, Options, Credits, a
  loss and a win). Without `-touch` everything is as before.
- Android: build the APK; the touch layout is on from the first frame.
