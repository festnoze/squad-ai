# M3 audio shortlist - free CC0 recordings

> Superseded for the shipped files on 2026-11-18 by the audio overhaul ([audio/AUDIO_REPORT.md](audio/AUDIO_REPORT.md)):
> the same picks plus new ones are now made by `tools/audio/audio_pipeline.py` (LUFS based loudness matching, true peak
> ceiling), and the game has music. The scouting and licence evidence below still applies to the M3 picks.

Status: scouting done on 2026-11-11, nothing imported into `Assets/`. Scope: PRD 7.3
("M3 brings CC0 recordings: wood scrape, footsteps, room tone") and the M3 line
"recorded audio" of section 11, measured against the seven sounds that
`Assets/Scripts/Runtime/Sfx.cs` synthesizes today (hop, hm, caught, creak, tension,
hein, thump).

Every licence below was read on the item's own OpenGameArt page on 2026-11-11
(the "License(s)" field, its link, and the "Copyright/Attribution Notice" field
when present). Every number was measured on the downloaded file itself
(`tools/assets/audio_measure.py`: ffprobe for the header, ffmpeg decode to float
PCM for the levels, the `wave` module for 16-bit WAV headers). Nobody listened to
these files: the "why it fits" notes come from the item descriptions, the file
names, and spectrograms read image by image (`tools/assets/audio_sheet.py`, see
section 7). **A listening pass by the product owner is still required before
import.**

Files:

- Originals: `ThirdParty_staging/audio/oga/<item slug>/` (archive as downloaded,
  unpacked into `x/`). `ThirdParty_staging/audio/manifest.json` has the URL,
  sha256 and size of each download; `ThirdParty_staging/audio/sources.json` has
  the licence facts read from each page.
- Import-ready clips: `ThirdParty_staging/audio/derived/*.wav` (21 files,
  1.9 MB, all mono 44.1 kHz 16-bit PCM), rebuilt by
  `python -I tools/assets/audio_derive.py`, with `derived/derived.json` (source,
  trim, fades, gain, sha256 per clip). The originals are never modified.

`ThirdParty_staging/` is gitignored.

---

## 1. Summary

| Wanted | Pick (derived clip) | Source file (under `oga/`) | Item page | Author (OGA) | Licence read |
|---|---|---|---|---|---|
| Chair hop on wood, 4 variants | `hop_01` to `hop_04` | `75-cc0-breaking-falling-hit-sfx/x/bfh1_wood_hit_01.ogg`, `bfh1_wood_hit_02.ogg`; `100-cc0-metal-and-wood-sfx/x/wood_hit_05.ogg`, `wood_hit_09.ogg` | [75 CC0 breaking / falling / hit sfx](https://opengameart.org/content/75-cc0-breaking-falling-hit-sfx), [100 CC0 metal and wood SFX](https://opengameart.org/content/100-cc0-metal-and-wood-sfx) | rubberduck | CC0 |
| Chair leg scrape, 3 variants | `scrape_01` to `scrape_03` | `saw-or-wood-impact/saw_-_starninjas_0.ogg` (3 strokes cut out) | [Saw or Wood Impact](https://opengameart.org/content/saw-or-wood-impact) | StarNinjas | CC0 |
| Long wood creak | `creak_long` | `100-cc0-sfx/x/door_02.ogg` | [100 CC0 SFX](https://opengameart.org/content/100-cc0-sfx) | rubberduck | CC0 |
| Short wood creak | `creak_short` | `50-rpg-sound-effects/x/OGG/creak3.ogg` | [50 RPG sound effects](https://opengameart.org/content/50-rpg-sound-effects) | Kenney | CC0 |
| Footsteps on wood, 5 variants | `footstep_01` to `footstep_05` | `50-rpg-sound-effects/x/OGG/footstep00.ogg`, `01`, `03`, `07`, `08` | [50 RPG sound effects](https://opengameart.org/content/50-rpg-sound-effects) | Kenney | CC0 |
| Room tone loop | `roomtone_airvent_loop` | `airvent-loop/airvent-large-loop.wav` | [Airvent Loop](https://opengameart.org/content/airvent-loop) | Longor | CC0 |
| Room tone layer (optional) | `roomtone_clock_loop` | `ticking-clock/ticking_clock.wav` | [Ticking clock.](https://opengameart.org/content/ticking-clock) | bart | CC0 |
| Put-down thump | `thump` | `door-open-door-close/x/door/door-05.flac` | [Door open, door close](https://opengameart.org/content/door-open-door-close) | qubodup | CC0 |
| Caught sting, two descending notes | `sting_caught` | `85-short-music-jingles/x/OGG/jingles_SAX/jingles_SAX05.ogg` | [85 Short music jingles](https://opengameart.org/content/85-short-music-jingles) | Kenney | CC0 |
| Caught sting, "wah wah wah waaah" (alternate) | `sting_caught_long` | `game-over-trumpet-sfx/losetrumpet.wav` | [Game Over Trumpet SFX](https://opengameart.org/content/game-over-trumpet-sfx) | 0new4y | CC0 |
| "huh ?" vocal | `vocal_huh` | `huh/huh.wav` | [huh?](https://opengameart.org/content/huh) | TinyWorlds | CC0 |
| UI menu click | `ui_click` | `interface-sounds/x/Audio/click_001.ogg` | [Interface Sounds](https://opengameart.org/content/interface-sounds) (Kenney) | Kenney | CC0 |

Licence as read on every page above: field "License(s): CC0", linked to
`http://creativecommons.org/publicdomain/zero/1.0/`, and no other licence
listed. The "50 RPG sound effects" and "85 Short music jingles" pages (Kenney)
show the attribution notice `Credit "Kenney.nl" or "www.kenney.nl", this is not
mandatory.`; the other picked pages, "Interface Sounds" included, show none. The Kenney archives
also ship a licence file: "License (CC0) http://creativecommons.org/publicdomain/zero/1.0/
... Credit (Kenney or www.kenney.nl) would be nice but is not mandatory."
("50 RPG sound effects": "RPG sounds by Kenney Vleugels"; "85 Short music jingles": "Short jingles by Kenney Vleugels") and "License: (Creative Commons Zero, CC0) ...
Support us by crediting Kenney or www.kenney.nl (this is not mandatory)"
(Interface Sounds, dated 11-02-2020).

**Keep synthesized:** the "hm ?" telegraph, the rising tension loop of the creak
warning, and (if the listening pass rejects `vocal_huh`) the "hein ?" discovery
sting. See section 4.

---

## 2. Per sound

Measurements of the original files. Peak, RMS and active RMS are in dBFS on the
decoded signal (active RMS = RMS of the 20 ms frames within 30 dB of the loudest
one, a better loudness figure for short clips). A peak above 0 is Vorbis decoder
overshoot of a file normalized to full scale.

| Original file (under `ThirdParty_staging/audio/oga/`) | Duration | Format | Peak | RMS | Active RMS | Size |
|---|---|---|---|---|---|---|
| `75-cc0-breaking-falling-hit-sfx/x/bfh1_wood_hit_01.ogg` | 0.248 s | vorbis 48 kHz stereo | -1.6 | -21.7 | -17.8 | 11 KB |
| `75-cc0-breaking-falling-hit-sfx/x/bfh1_wood_hit_02.ogg` | 0.281 s | vorbis 48 kHz stereo | -2.1 | -18.7 | -16.8 | 13 KB |
| `100-cc0-metal-and-wood-sfx/x/wood_hit_05.ogg` | 0.308 s | vorbis 48 kHz stereo | -0.5 | -24.5 | -20.4 | 9 KB |
| `100-cc0-metal-and-wood-sfx/x/wood_hit_09.ogg` | 0.258 s | vorbis 48 kHz stereo | 0.1 | -16.1 | -12.8 | 12 KB |
| `saw-or-wood-impact/saw_-_starninjas_0.ogg` | 5.609 s | vorbis 44.1 kHz mono | -3.6 | -24.8 | -23.2 | 49 KB |
| `100-cc0-sfx/x/door_02.ogg` | 2.643 s | vorbis 48 kHz stereo | -14.3 | -30.8 | -29.9 | 91 KB |
| `50-rpg-sound-effects/x/OGG/creak3.ogg` | 0.338 s | vorbis 48 kHz stereo | -7.4 | -21.7 | -19.4 | 10 KB |
| `50-rpg-sound-effects/x/OGG/footstep00.ogg` | 0.249 s | vorbis 48 kHz stereo | 0.3 | -19.7 | -17.2 | 9 KB |
| `50-rpg-sound-effects/x/OGG/footstep01.ogg` | 0.282 s | vorbis 48 kHz stereo | 0.2 | -18.3 | -16.3 | 10 KB |
| `50-rpg-sound-effects/x/OGG/footstep03.ogg` | 0.269 s | vorbis 48 kHz stereo | 0.4 | -20.0 | -18.8 | 10 KB |
| `50-rpg-sound-effects/x/OGG/footstep07.ogg` | 0.256 s | vorbis 48 kHz stereo | 0.1 | -21.6 | -18.3 | 10 KB |
| `50-rpg-sound-effects/x/OGG/footstep08.ogg` | 0.256 s | vorbis 48 kHz stereo | 0.7 | -17.0 | -14.4 | 9 KB |
| `airvent-loop/airvent-large-loop.wav` | 7.489 s | PCM 16-bit 44.1 kHz mono | -13.1 | -27.8 | -27.8 | 646 KB |
| `ticking-clock/ticking_clock.wav` | 8.000 s | PCM float 32-bit 44.1 kHz stereo | -5.4 | -33.4 | -31.7 | 2756 KB |
| `door-open-door-close/x/door/door-05.flac` | 0.391 s | FLAC 96 kHz stereo | -3.0 | -20.6 | -19.1 | 122 KB |
| `85-short-music-jingles/x/OGG/jingles_SAX/jingles_SAX05.ogg` | 0.462 s | vorbis 44.1 kHz stereo | -10.4 | -21.9 | -20.4 | 10 KB |
| `game-over-trumpet-sfx/losetrumpet.wav` | 1.112 s | PCM 16-bit 44.1 kHz stereo | -11.0 | -18.4 | -18.5 | 192 KB |
| `huh/huh.wav` | 0.352 s | PCM 16-bit 24 kHz mono | -20.1 | -30.4 | -29.7 | 17 KB |
| `interface-sounds/x/Audio/click_001.ogg` | 0.097 s | vorbis 44.1 kHz mono | -1.4 | -26.4 | -19.5 | 5 KB |

### 2.1 Hop (replaces the synthesized 45 ms tick)

- **Pick:** `hop_01` to `hop_04` (0.25 to 0.28 s each).
- **Why:** on the spectrograms these four are single compact knocks with their
  energy in the low mids and a short decay, the sound of a light wooden object
  landing, unlike the other wood hits of the same packs (which ring like wood
  blocks: Ogrebane "Wood and Metal vol. 2", `wood_hit_07`) or rattle. All four
  come from one author (rubberduck), so the recording chain is consistent.
  The packs' own descriptions: "i made 75 breaking, falling and hit sounds"
  and "wood: breaking, door closing, cracking, falling, wood hammer, hit, misc,
  slam and squeaking wood". Both are dual mono (L/R correlation 1.00).
- **Soft hop on a rug:** keep `Sfx.PlaySoftHop` as a volume scale (0.25) of the
  same clips; no separate recording needed.
- **Alternate:** `100-cc0-sfx-2/x/sfx100v2_wood_hit_01.ogg` (0.35 s, same author,
  [100 CC0 SFX #2](https://opengameart.org/content/100-cc0-sfx-2), CC0).

### 2.2 Chair leg scrape

- **Pick:** `scrape_01` to `scrape_03` (0.30 to 0.35 s), cut at 1.13-1.45 s,
  1.96-2.26 s and 2.75-3.10 s of the source, 15 ms fade in, 40 ms fade out.
- **Why:** the source is wood rubbed on wood ("a simple sound I made by rubbing to
  pieces of wood together, to me it sounds like a saw. It has over 10
  impacts, so might want to break up the sound into smaller sounds"). The
  envelope shows 12 separate friction strokes of 0.22 to 0.30 s; three clean
  mid-level ones were cut out. No CC0 recording of an actual chair leg on a
  floor was found (section 4).
- **Rejected:** "Scrapes" (AntumDeluge, CC0) is an object dragged on a cinder
  block, so concrete, not wood; "Stone, rock or wood moved sound" (pauliuw, CC0)
  is a 0.46 s MP3 with an edit click at both ends, and its "no_tick" fix is a
  5.6 KB MP3.

### 2.3 Creak (long and short)

- **Long pick:** `creak_long` (2.60 s), from `door_02.ogg`, one of the two
  "door squeak" files of "100 CC0 SFX" ("recorded with an android device").
  The spectrogram shows a sustained harmonic stack whose pitch glides, the
  classic creaking-door "crrreeeak", cleaner than the alternatives. It is a
  door, not a chair: if it reads too big for a chair, trim it (the PRD creak is
  a loud alert heard 7 m away, so a big creak is defensible).
- **Short pick:** `creak_short` (0.33 s), from Kenney `creak3.ogg`: one short burst
  with clear harmonics, a single "eek".
- **Alternates:** `100-cc0-sfx/x/door_01.ogg` (2.78 s, same family);
  Kenney `creak1.ogg` / `creak2.ogg` (0.66 / 0.83 s, two or three bursts);
  rubberduck `100-cc0-metal-and-wood-sfx/x/wood_squeak_01.ogg` / `_02` (0.48 /
  0.39 s, a stick-slip pulse train, less pitched).
- **Rejected:** "Tree Creaking" (AntumDeluge, CC0, 6.6 s): slow ratchet pulses
  over an outdoor noise floor, and the page says it is a cleaned-up copy of a
  sound "by Department64", a provenance chain not checked here.

### 2.4 Footsteps on wood (inhabitants, new in M3)

- **Pick:** `footstep_01` to `footstep_05` (0.24 to 0.27 s), Kenney "50 RPG sound
  effects" `footstep00`, `01`, `03`, `07`, `08`.
- **Why:** clean, normalized, consistent set; the spectrograms show heel-then-toe
  double hits with a 100 to 500 Hz body, consistent with hard shoes on boards.
  **The pack does not say what surface they were recorded on**: confirm by ear.
  True stereo (measured on `footstep00` and `08`: L/R correlation 0.55 and 0.81,
  left 4 dB louder); the mono downmix loses at most 1.3 dB, no cancellation.
- **Alternate, explicitly labelled wood:** `100-cc0-sfx-2/x/sfx100v2_footstep_wood_01.ogg`
  to `_04` (rubberduck, CC0): quieter and duller (active RMS -28 to -37 dBFS),
  would need about +12 dB.
- **Rejected:** "Steps in wood floor" (mikeask, CC0, 3.5 s, 8 steps): a constant
  hum line near 600 Hz runs under every step; "Different steps on wood..."
  (TinyWorlds, CC0): very quiet (peak -13 to -26 dBFS) and no clean decay.

### 2.5 Room tone

- **Pick:** `roomtone_airvent_loop` (6.49 s), from "Airvent Loop" ("Sort-of-looping
  sound of an airvent in my family home."). Smooth, stationary broadband air
  noise recorded in a house, mono 44.1 kHz. The original is only "sort of"
  looping (a 1.4 dB level step at the seam), so the derived clip folds its
  last 1.0 s into its first 1.0 s with an equal power crossfade: seam jump
  0.0009 and no visible seam when played twice (section 7). Normalized to -30
  dBFS RMS: play it at a low AudioSource volume, it is a bed, not a sound.
- **Optional layer:** `roomtone_clock_loop` (8.00 s), bart's "Ticking clock."
  ("Includes a loop (8 ticks, so it doesn't feel particularly repetitive)").
  One tick per second, evenly spaced across the seam (checked by playing it
  twice). Use it in one room only, quietly: a tick competes with the hop and
  footstep cues the player listens for.
- **Alternate:** "Fridge Loop 1" (Kresiek The Furry, CC0,
  `fridge-loop-1/amb_fridge_loop_1.wav`, 9.2 s, 22 kHz stereo, loops cleanly,
  quiet hum at -35 dBFS RMS); the author warns it is "not the best quality".
- **Rejected:** "The Shop" (LEGIT Audio, CC0 on OGA only): loud low rumble of a
  shop fridge with clinks inside, 96 kHz 24-bit, 19 MB; rubberduck ambient and
  machine loops (broadband hiss or pulsing machines).

### 2.6 Put-down thump

- **Pick:** `thump` (0.39 s), qubodup's own room door closing ("I recorded opening
  and closing of my room's door"), FLAC 96 kHz. Single event, the lowest and
  most compact thud of the candidates, no latch rattle.
- **Alternates:** rubberduck `100-cc0-metal-and-wood-sfx/x/wood_close_02.ogg`
  (0.44 s) and `100-cc0-sfx-2/x/sfx100v2_wood_hit_02.ogg` (0.36 s), same author
  as the hops, lighter.
- **Rejected:** Kenney `doorClose_1` to `_4` (latch and rattle before the thud).

### 2.7 Caught sting

- **Pick:** `sting_caught` (0.45 s), Kenney "85 Short music jingles" `jingles_SAX05`: exactly
  two descending sax notes. Pitch track (autocorrelation, 23 ms hop): 368 Hz
  then 220 Hz (about F#4 down to A3), the second longer, the "wah... wah" of the
  current synthesized sting (311 Hz then 262 Hz).
- **Alternate:** `sting_caught_long` (1.11 s), "Game Over Trumpet SFX": the full
  "wah wah wah waaah", pitch 197, 175, 165, 147 then 124 Hz held. It was
  "made using Bosca Ceoil", so it is a synthesized trumpet, not a recording.
  The original is cut while still sounding (last sample at -0.042 of peak, a
  click): the derived clip adds a 40 ms fade out.
- **Other two-note option:** `jingles_SAX00` (459 Hz then 315 Hz, 0.39 s).

### 2.8 "huh ?" vocal

- **Pick:** `vocal_huh` (0.35 s), TinyWorlds "huh?" ("A cute interaction effect I
  created for a Samorost-like prototype. Could be used as sound when
  interacting with NPC/monsters."). The spectrogram is a voiced vowel, and the
  pitch rises steadily from 230 Hz to 480 Hz: a clear question contour. Use it
  for the "hein ?" discovery (`Sfx.PlayHein`).
- **Caveats:** the page does not say whether it is a human recording or
  processed; it is a high, cartoonish voice (pitch it down, around 0.75, for
  an adult inhabitant); the source is 24 kHz mono and peaks at -20 dBFS, so the
  derived clip has +11.7 dB of gain and its noise floor rose with it; it
  starts abruptly (first sample at -0.052 of peak): the derived clip adds a
  5 ms fade in.
- **Alternate (human, female):** cicifyre "Voice Clip Packs for Visual Novels and
  RPGs" (CC0), `voice-clip-packs-for-visual-novels-and-rpgs/x/Free Voice Clips Pack - Mature Female/noises/anime_eh.wav`
  (0.74 s, 48 kHz float, dual mono): a real "eh", but its pitch falls (256 to
  216 Hz), so it reads "eh." rather than "eh ?". The same pack's
  `question_words/what2.wav` / `what3.wav` rise, but they are the English word.
- **No CC0 recorded male "huh ?" or French "hein ?" was found.**

### 2.9 UI click

- **Pick:** `ui_click` (0.097 s), Kenney Interface Sounds `click_001`: a soft, low
  click (zero crossing rate about 335 Hz; the other `click_00x` are brighter or
  only 7 to 22 ms long), already mono 44.1 kHz.
- **Alternate:** Kenney "51 UI sound effects" `click1.wav` (0.094 s, 16-bit WAV,
  very quiet at -34 dBFS active RMS).

---

## 3. Import-ready clips (`ThirdParty_staging/audio/derived/`)

All mono, 44.1 kHz, 16-bit PCM WAV, header checked with the `wave` module.
Loudness: one-shots matched on active RMS (target -16 dBFS for hops, thump and
stings, -18 dBFS for scrapes, creaks, footsteps and the vocal) with a -1 dBFS
peak ceiling that wins when they conflict; loops at -30 dBFS RMS; the UI click
peak-normalized to -1 dBFS.

| Clip | Duration | Peak dBFS | Active RMS dBFS | Gain applied | Notes |
|---|---|---|---|---|---|
| `hop_01` | 0.248 s | -1.0 | -17.1 | -2.3 dB | ceiling limited |
| `hop_02` | 0.281 s | -1.3 | -16.0 | -2.2 dB | |
| `hop_03` | 0.278 s | -1.0 | -20.1 | -3.5 dB | 30 ms lead trimmed, ceiling limited |
| `hop_04` | 0.248 s | -2.5 | -16.0 | -5.6 dB | 10 ms lead trimmed |
| `scrape_01` | 0.320 s | -3.2 | -18.0 | +5.1 dB | cut 1.13-1.45 s |
| `scrape_02` | 0.300 s | -3.9 | -18.0 | +5.0 dB | cut 1.96-2.26 s |
| `scrape_03` | 0.350 s | -2.0 | -18.0 | +5.2 dB | cut 2.75-3.10 s |
| `creak_long` | 2.603 s | -2.4 | -18.0 | +8.9 dB | 40 ms lead trimmed |
| `creak_short` | 0.328 s | -6.8 | -18.0 | -2.0 dB | |
| `footstep_01` | 0.239 s | -1.0 | -20.0 | -3.5 dB | ceiling limited |
| `footstep_02` | 0.272 s | -1.0 | -18.1 | -4.0 dB | |
| `footstep_03` | 0.269 s | -1.0 | -20.5 | -4.2 dB | ceiling limited |
| `footstep_04` | 0.256 s | -1.0 | -19.7 | -3.4 dB | ceiling limited |
| `footstep_05` | 0.256 s | -2.7 | -18.0 | -6.0 dB | |
| `thump` | 0.391 s | -1.0 | -17.1 | -1.0 dB | ceiling limited, 96 kHz resampled |
| `sting_caught` | 0.452 s | -6.1 | -16.0 | +1.3 dB | |
| `sting_caught_long` | 1.112 s | -8.6 | -16.0 | -0.6 dB | 40 ms fade out added (cut ending) |
| `vocal_huh` | 0.352 s | -8.4 | -18.0 | +11.7 dB | 5 ms fade in added, 24 kHz resampled |
| `ui_click` | 0.097 s | -1.0 | -19.2 | +0.4 dB | |
| `roomtone_airvent_loop` | 6.489 s | -15.4 | -30.0 | -2.3 dB | 1.0 s equal power loop crossfade, seam jump 0.0009 |
| `roomtone_clock_loop` | 8.000 s | -4.4 | -30.0 | +0.7 dB | source loop kept as is, seam jump 0.0001 |

Suggested Unity import settings: one-shots "Decompress On Load", PCM or ADPCM;
the two loops "Compressed In Memory", Vorbis; "Force To Mono" is not needed (the
clips are mono already). `Sfx.cs` AudioSource volumes were tuned for the
synthesized clips (peaks near 0.85 and very short): re-tune them by ear.

---

## 4. Gaps: what stays synthesized

| Sound | Decision | Why |
|---|---|---|
| "hm ?" telegraph (`Sfx.Hm`) | keep synthesized | No CC0 closed-mouth "hm ?" recording found. It is a gameplay-critical cue (it announces a head turn), so a synthesized, tunable, panned blip is an asset, not a stopgap. |
| Rising tension loop (`Sfx.Tension`) | keep synthesized | Its pitch and volume are driven by the creak gauge and it relies on a 1 s seamless loop of whole-cycle partials; no recording does that better. |
| "hein ?" discovery (`Sfx.Hein`) | `vocal_huh` if the listening pass accepts it, else keep synthesized | See 2.8: cartoon pitch, unknown whether human, no male or French take available. |
| Chair leg scrape | substitute | No CC0 recording of a chair leg on a floor; wood rubbed on wood is used instead (2.2). |
| Room tone | substitute | No CC0 "quiet house room tone" as such; an air vent recorded in a home is the closest (2.5). The "General Household Sound Effects" pack (bretbernhoft, CC0, https://opengameart.org/content/general-household-sound-effects) has in-home HEPA filter, air conditioner and computer fan takes, but each file is 40 to 90 MB, so it was not downloaded; an HTTP Range request of the first few MB of one WAV would give a 20 s excerpt if the vent loop is rejected. |
| Kenney "Impact Sounds" (impactWood, footstep_wood) | not available | Not mirrored on OpenGameArt; kenney.nl refuses scripted downloads (403, per the brief, not retried). |

---

## 5. Risks

1. **Nobody has listened.** Choices rest on descriptions, names, spectrograms and
   pitch tracks. The two weakest identifications: the surface of the Kenney
   footsteps (not stated by the pack) and whether `huh.wav` is a human voice.
2. **Mixed source formats.** 48 kHz stereo Vorbis (rubberduck, Kenney "50 RPG sound effects"), 96 kHz
   FLAC (qubodup), 32-bit float WAV (bart, cicifyre: the Python `wave` module
   cannot read those, ffprobe can; Unity imports them), 24 kHz and 22 kHz WAV
   (TinyWorlds, fridge). The derived set removes this by converting everything
   to mono 44.1 kHz 16-bit; nothing was lost in the mono downmix (no negative L/R
   correlation, worst loss 1.3 dB on `footstep00`, 2.0 dB on the clock).
3. **Loudness.** The originals range from +1.4 dBFS decoded peaks (Vorbis overshoot
   on files normalized to full scale, e.g. Kenney `doorClose_3`) to -30 dBFS
   (UI clicks). After matching, hop variants still spread 4 dB of active RMS
   (-16 to -20.1 dBFS) and footsteps 2.5 dB because the -1 dBFS ceiling wins on
   the spikiest takes; random pitch and volume per play will hide most of it.
   `vocal_huh` needed +11.7 dB, raising its noise floor.
4. **Loop seams.** The air vent original has a 1.4 dB level step at its seam: use
   the crossfaded derived loop, not the original. It is only 6.5 s long, so a
   patient ear may catch the repetition over a long level. The clock loop is
   clean but rhythmic and may mask gameplay cues.
5. **Clicks at the edges.** `losetrumpet.wav` ends while still sounding and
   `huh.wav` starts abruptly; fixed by fades in the derived clips only.
6. **Clip length vs cadence.** Hops fire every 0.224 s (CONTRACT_M2); the recorded
   hops last 0.25 to 0.28 s (sounding part about 0.11 to 0.2 s, the rest is a
   quiet tail), so tails overlap slightly where the 45 ms synthesized tick never
   did. If it smears, shorten the fade out in `audio_derive.py`.
7. **Character.** `creak_long` is a door squeak and `thump` a door closing:
   believable, but they are doors. `sting_caught_long` is synthesized (Bosca
   Ceoil), not recorded.
8. **Provenance.** rubberduck recorded "100 CC0 SFX" "with an android device"
   (lo-fi but his own); "Tree Creaking" (rejected) is a copy of another author's
   sound. Every pick was uploaded by the person who says they made it.

---

## 6. LICENSES draft block

To merge into the M3 licence file required by the M3 gate (PRD 11). CC0 needs no
attribution; the credits are a courtesy and keep provenance auditable.

```
AUDIO - all files CC0 1.0 Universal (public domain dedication)
https://creativecommons.org/publicdomain/zero/1.0/
Licences read on each item page on opengameart.org on 2026-11-11.

hop_01.wav, hop_02.wav
  "75 CC0 breaking / falling / hit sfx" by rubberduck - CC0
  https://opengameart.org/content/75-cc0-breaking-falling-hit-sfx
  (bfh1_wood_hit_01.ogg, bfh1_wood_hit_02.ogg)
hop_03.wav, hop_04.wav
  "100 CC0 metal and wood SFX" by rubberduck - CC0
  https://opengameart.org/content/100-cc0-metal-and-wood-sfx
  (wood_hit_05.ogg, wood_hit_09.ogg)
scrape_01.wav, scrape_02.wav, scrape_03.wav
  "Saw or Wood Impact" by StarNinjas - CC0
  https://opengameart.org/content/saw-or-wood-impact
  (saw_-_starninjas.ogg, three excerpts)
creak_long.wav
  "100 CC0 SFX" by rubberduck - CC0
  https://opengameart.org/content/100-cc0-sfx
  (door_02.ogg)
creak_short.wav, footstep_01.wav to footstep_05.wav
  "50 RPG sound effects" by Kenney (www.kenney.nl) - CC0
  https://opengameart.org/content/50-rpg-sound-effects
  (creak3.ogg; footstep00, 01, 03, 07, 08.ogg)
roomtone_airvent_loop.wav
  "Airvent Loop" by Longor - CC0
  https://opengameart.org/content/airvent-loop
  (airvent-large-loop.wav, loop crossfaded)
roomtone_clock_loop.wav
  "Ticking clock." by bart - CC0
  https://opengameart.org/content/ticking-clock
  (ticking_clock.wav)
thump.wav
  "Door open, door close" by qubodup - CC0
  https://opengameart.org/content/door-open-door-close
  (door-05.flac)
sting_caught.wav
  "85 Short music jingles" by Kenney (www.kenney.nl) - CC0
  https://opengameart.org/content/85-short-music-jingles
  (jingles_SAX05.ogg)
sting_caught_long.wav
  "Game Over Trumpet SFX" by 0new4y - CC0
  https://opengameart.org/content/game-over-trumpet-sfx
  (losetrumpet.wav)
vocal_huh.wav
  "huh?" by TinyWorlds - CC0
  https://opengameart.org/content/huh
  (huh.wav)
ui_click.wav
  "Interface Sounds" by Kenney (www.kenney.nl) - CC0
  https://opengameart.org/content/interface-sounds
  (click_001.ogg)

All clips were converted to mono 44.1 kHz 16-bit WAV, trimmed, faded and
level matched by tools/assets/audio_derive.py.
```

---

## 7. Method and tools

- **Search:** OpenGameArt advanced search restricted to art type "Sound Effect"
  (term 13) and licence "CC0" (term 4, checked in the form's own option list),
  44 keyword queries (wood, footstep, creak, chair, scrape, ambience, room tone,
  trombone, huh, click, thud, kenney, house, clock, kitchen, voice...).
  "chair", "furniture", "trombone", "wah" and "apartment" return nothing in CC0.
  Then each candidate item page was read for its licence, author, date,
  description and file list, and each downloaded URL was confirmed to be listed
  on that page. Pages with a second licence (for example "Random Sounds
  Samples", OGA-BY 3.0 and CC0) were not used.
- **Politeness:** at most one request per 1.2 s, generic user agent, no personal
  data, cached pages. The voice packs (11 to 16 MB) were inspected first by
  reading only the zip central directory with an HTTP Range request. Packs over
  20 MB per file were skipped (Owlish Media 139 MB, "68 Workshop Sounds" 24 MB,
  household pack 40 to 90 MB per file); The Shop (19 MB) is the largest download.
- **Safety:** archives listed before unpacking (no absolute or `..` paths); two
  `.url` shortcuts in Kenney Interface Sounds and the `.sfk` peak files of RPG
  Audio were deleted unopened; every Python run on downloaded data used `-I`.
- **Listening substitute:** `tools/assets/audio_sheet.py` stacks log-frequency
  spectrograms (50 Hz to 12 kHz) of candidates into one PNG, calibrated with
  100 Hz, 1 kHz and 5 kHz test tones (showspectrumpic sizes its FFT from the
  image height, so rows are rendered 1024 px tall then shrunk; a 90 px render
  put every tone in the same place). Pitch contours of the stings and vocals
  come from an autocorrelation tracker. Loops were checked by rendering each one
  played twice in a row.

Scripts (all stdlib Python plus ffmpeg/ffprobe from PATH, nothing installed):

| Script | Role |
|---|---|
| `tools/assets/audio_fetch.py` | rate-limited downloader, writes `ThirdParty_staging/audio/manifest.json` (URL, page, sha256) |
| `tools/assets/audio_measure.py` | duration, rate, channels, peak, RMS, active RMS, silences, transients, envelope, loop seam |
| `tools/assets/audio_sheet.py` | spectrogram contact sheet for review without listening |
| `tools/assets/audio_derive.py` | builds `ThirdParty_staging/audio/derived/` from the picks |
