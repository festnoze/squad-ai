# Audio overhaul - report

Date: 2026-11-18. Scope: the product owner's request "do a real job on the sounds: identify the needs, rework them or
use tools to get a better sound quality, and think of an ambient music, royalty free or other, suited to the game".

Tools: `tools/audio/audio_pipeline.py` (Python venv in `tools/audio/.venv`: numpy, scipy, soundfile, pyloudnorm; ffmpeg
6.1.1 on PATH). Everything below is reproducible from the downloads under `ThirdParty_staging/audio` (gitignored) with
`python tools/audio/audio_pipeline.py all`; the full numbers are in `tools/audio/audio_report.json`.

**Nobody listened.** As in M3 (docs/M3_AUDIO.md), every choice rests on item descriptions, measurements, onset and
pitch tracks and loop correlations. A listening pass by the product owner is still the last word (section 8).

---

## 1. Needs: every sound event of the game

Audit of `Sfx.cs`, `FootstepAudio.cs`, `GameState.PlaySounds`, `Menu.cs` and every `AudioSource` of the runtime.

| Event | Before | Now |
|---|---|---|
| Furniture hop, hard floor | 4 recorded wood knocks (rubberduck) | same picks, re-cut tighter, loudness matched (they spread 6 dB before) |
| Furniture hop, rug or soft room, or masked by the robot | the hard hop at 25 % volume | **4 muffled variants** (the same knocks low passed at 700 Hz): a felt thud |
| Pivot on the spot, pick up by an inhabitant | 3 recorded scrapes | same, loudness matched |
| Creak (the alert) | recorded door squeak | same, high passed at 120 Hz (handling rumble), tail trimmed |
| Creak gauge warning | short recorded creak + synthesized tension loop | unchanged (the loop is driven by the gauge, M3_AUDIO 4) |
| Put-down thump | recorded door thud | same, re-normalised |
| Inhabitant footsteps (3D) | 5 recorded steps (Kenney) | same, re-normalised |
| Dog patter | synthesized | unchanged, its gain corrected for the new footstep mix |
| "hm ?" telegraph, dog sniff | synthesized | unchanged (no CC0 recording, gameplay-critical and tunable) |
| "hein ?" discovery | synthesized (recorded vocal_huh off) | unchanged; vocal_huh re-made (DC, 150 Hz high pass) for the listening pass |
| Dog bark | synthesized | unchanged: the only CC0 dog pack found ("Dog sounds", pauliuw, OGA) has 8 kHz barks with DC offset; rejected |
| Robot vacuum hum | synthesized seamless loop | unchanged (distance driven, already clean) |
| Rocking chair creak, robot bump, pratfall, office chair roll, stool rattle | synthesized | unchanged |
| Room door opening | synthesized latch and hinge | **recorded wooden door** (Kenney doorOpen_1) |
| Stool topple | synthesized clatter | **recorded wooden fall** (rubberduck wood_falling_02) |
| Fallen load (vase, pot) | synthesized knock and shards | **recorded breaking dishes** (rubberduck dishes_01) |
| Floor lamp switch | synthesized click | **recorded switch** (rubberduck switch_02) |
| Wardrobe: doors open, hide, leave, doors shut | **silent** | **new**: a wooden lid opening when the action starts, a light wooden close when it ends |
| Caught (seen moving / suspicion) | 2 recorded stings | same, re-normalised (the long one had a 0.015 DC offset, removed) |
| Win | **silent** | **new**: rising pizzicato jingle (Kenney jingles_PIZZA10: D E F# G, G held) |
| Level start | silent | the level music fading in is the cue (no sting over the intro card) |
| UI click | recorded click | same, trimmed |
| UI hover / keyboard and D-pad navigation | **silent** | **new**: soft tick (Kenney tick_001) on mouse enter and on navigation, never on touch |
| Title page | **silent** | **new**: title music |
| In level ambience | air vent room tone (+ optional clock) | same, plus the level music under it |

## 2. Sources and picks

All new effects come from packs already downloaded and licence-checked for M3 (`ThirdParty_staging/audio/sources.json`,
every page CC0): Kenney "50 RPG sound effects", "85 Short music jingles", "Interface Sounds"; rubberduck "100 CC0 SFX" and
"100 CC0 metal and wood SFX". Picks were made on measurements: no source clipping (wood_falling_01 has 26 clipped
samples, _02 none), duration close to the animation it covers (wardrobe action 0.5 s, door swing 0.6 s), and for the
win jingle a pitch track of the 17 pizzicato jingles (PIZZA02 is a whole tone run, magic rather than victory; PIZZA10
rises to the tonic and holds it). Files: `Assets/ThirdParty/Audio/*.wav`, rows in docs/LICENSES.md.

## 3. Processing (`tools/audio/audio_pipeline.py sfx`)

For every effect, from the original download: decode to 44.1 kHz float, mono downmix (every effect is positional or
panned), optional cut, 30 Hz high pass (DC and rumble; 120 Hz for the creak, 150 Hz for the vocal), optional voicing
filter (700 Hz low pass for the muffled hops), silence trim (5 ms envelope, 45 dB under the peak, 3 ms pre-roll, 10 ms
post-roll), fades (equal power, 1 to 15 ms in, 5 to 80 ms out), loudness normalisation to the file target under a
**-1 dBTP** true peak ceiling (4x oversampled), 16-bit TPDF dithered WAV. Loops are filtered as three copies end to end
(no filter seam); the air vent keeps its 1 s equal power loop crossfade. No denoiser: the measured noise floors of the
one-shots are under -44 dBFS and the trims remove the noisy tails; the scrape "floor" (-28 to -31 dBFS) is the friction
sound itself.

**Loudness metric.** BS.1770 K-weighted loudness (LUFS scale). Loops and music: integrated loudness. One-shots: the
**max over a 100 ms window**. The 400 ms momentary window under-reads short impacts (hop_03, 0.13 s, read 8 dB under
hop_02 at the same peak), which made the old variants of a role 4 to 6 dB apart; 100 ms is close to the ear's own
integration time for short sounds, so variants matched on it sound matched. Both values are in the JSON report.

**File targets** (headroom and consistency, before the mix): one-shots -12 LUFS (100 ms max), the spikiest ones end
lower because the true peak ceiling wins (marked TP below); ambience loops -30 LUFS integrated; music -18 LUFS
integrated.

### Before / after

Loudness: LUFS 100 ms max, or integrated (I) for the loops. Before = the M3 clips as shipped (`tools/assets/audio_derive.py`).

| File | Before: dur s / loudness / TP dBTP / floor dBFS / lead+trail ms / DC | After: dur s / loudness / TP dBTP / lead+trail ms | Gain dB |
|---|---|---|---|
| `hop_01` | 0.248 / -14.2 / -0.9 / -240.0 / 5+116 / -5e-05 | 0.14 / -14.3 / -1.0 / 3+18 | -2.4 (TP) |
| `hop_02` | 0.281 / -11.1 / -1.3 / -194.3 / 0+72 / 0.00076 | 0.22 / -12.0 / -3.0 / 0+11 | -3.1 |
| `hop_03` | 0.278 / -17.2 / -1.0 / -240.0 / 23+137 / -0.00012 | 0.131 / -17.4 / -1.0 / 3+23 | -3.7 (TP) |
| `hop_04` | 0.248 / -11.6 / -2.5 / -222.2 / 10+78 / -0.00053 | 0.173 / -12.0 / -2.5 / 3+18 | -5.9 |
| `hop_soft_01` | new | 0.14 / -14.1 / -1.0 / 3+17 | -2.0 (TP) |
| `hop_soft_02` | new | 0.22 / -12.0 / -3.2 / 0+11 | -3.0 |
| `hop_soft_03` | new | 0.131 / -17.2 / -1.0 / 3+23 | -2.6 (TP) |
| `hop_soft_04` | new | 0.173 / -12.0 / -3.6 / 3+22 | -5.8 |
| `scrape_01` | 0.32 / -11.9 / -3.2 / -31.4 / 0+8 / -3e-05 | 0.32 / -12.0 / -3.4 / 2+12 | +5.0 |
| `scrape_02` | 0.3 / -12.6 / -3.9 / -29.3 / 0+9 / 0.00025 | 0.3 / -12.0 / -3.4 / 1+10 | +5.6 |
| `scrape_03` | 0.35 / -12.5 / -2.0 / -28.1 / 0+12 / 0.00012 | 0.35 / -12.0 / -1.5 / 2+13 | +5.7 |
| `creak_long` | 2.603 / -10.7 / -2.4 / -49.7 / 17+205 / -0.00019 | 2.394 / -12.0 / -3.5 / 12+29 | +7.7 |
| `creak_short` | 0.328 / -12.6 / -6.8 / -56.4 / 8+47 / 0.0 | 0.286 / -12.0 / -6.2 / 3+17 | -1.4 |
| `footstep_01` | 0.239 / -14.5 / -1.0 / -48.1 / 10+24 / -0.00015 | 0.22 / -14.6 / -1.0 / 4+12 | -3.5 (TP) |
| `footstep_02` | 0.272 / -14.0 / -1.0 / -54.8 / 20+32 / -1e-05 | 0.233 / -14.3 / -1.0 / 3+22 | -4.3 (TP) |
| `footstep_03` | 0.269 / -14.7 / -1.0 / -44.0 / 14+21 / 6e-05 | 0.258 / -14.4 / -1.0 / 3+21 | -3.8 (TP) |
| `footstep_04` | 0.256 / -16.0 / -1.0 / -55.0 / 6+53 / -4e-05 | 0.196 / -16.0 / -1.0 / 3+17 | -3.5 (TP) |
| `footstep_05` | 0.256 / -13.6 / -2.7 / -52.8 / 3+38 / 3e-05 | 0.226 / -12.3 / -1.0 / 3+20 | -4.7 (TP) |
| `roomtone_airvent_loop` | 6.489 / -30.8 I / -15.4 / -32.5 / 0+0 / 0.00048 | 6.489 / -30.0 I / -15.1 / 0+0 | -1.5 |
| `roomtone_clock_loop` | 8.0 / -29.6 I / -4.3 / -55.0 / 0+2 / -0.0007 | 8.0 / -30.0 I / -4.7 / 3+0 | +0.2 |
| `thump` | 0.391 / -10.4 / -1.0 / -52.4 / 0+42 / 0.0002 | 0.357 / -12.0 / -3.0 / 0+25 | -2.6 |
| `sting_caught` | 0.452 / -10.0 / -6.1 / -63.5 / 20+63 / -9e-05 | 0.382 / -12.0 / -8.0 / 3+19 | -0.7 |
| `sting_caught_long` | 1.112 / -12.0 / -8.6 / -18.1 / 0+4 / **0.01522** | 1.112 / -12.0 / -8.5 / 0+8 | -0.5 |
| `vocal_huh` | 0.352 / -11.5 / -8.3 / -43.8 / 0+10 / -0.0 | 0.352 / -12.0 / -7.5 / 0+10 | +11.7 |
| `ui_click` | 0.097 / -23.2 / -0.9 / -52.1 / 0+2 / 0.00029 | 0.097 / -23.1 / -1.0 / 0+65 | +0.6 (TP) |
| `ui_hover` | new | 0.060 / -23.3 / -1.0 / 0+47 (padded to 60 ms) | -1.3 (TP) |
| `sting_win` | new | 0.797 / -12.0 / -7.2 / 3+25 | -5.8 |
| `door_open` | new | 0.891 / -12.0 / -2.0 / 3+26 | -5.9 |
| `wardrobe_open` | new | 0.327 / -14.3 / -1.0 / 3+27 | -3.6 (TP) |
| `wardrobe_close` | new | 0.325 / -14.2 / -1.0 / 0+26 | -4.5 (TP) |
| `crash` | new | 0.728 / -13.8 / -1.0 / 3+72 | -4.0 (TP) |
| `topple` | new | 0.359 / -15.8 / -1.0 / 3+30 | -3.7 (TP) |
| `lamp_click` | new | 0.209 / -18.0 / -1.0 / 3+19 | -3.9 (TP) |

What changed in substance: the hops lost up to 137 ms of near-silent tail (they overlapped at the 0.224 s hop cadence),
the creak 205 ms, the stings and footsteps 20 to 50 ms of lead or tail; no file clips; the long caught sting's DC offset
(1.5 % of full scale) is gone; the hop and footstep variants of a role now play at one loudness (the runtime gain of each
file is derived from its measured loudness).

## 4. Playback targets (the mix)

Each recorded role plays at `gain x mix`, where `gain = 10^((-12 - file loudness) / 20)` (`AudioLibrary.ReferenceLufs`)
and `mix = 10^((target + 12) / 20)` (the Tuning constants). The M3.1 balance was kept: the old playback levels were
re-measured in the new metric and rounded, except the UI click (+2 dB: music now plays under the menus).

| Category | Roles | Playback target at Volume 100 % (LUFS) |
|---|---|---|
| Alert | creak | -13 |
| Stingers | caught (both), win, recorded "hein ?" | -15, -15, -14 |
| World impacts | thump -14, crash -14, topple -16, door -17 | -14 to -17 |
| Footsteps (within 1 m, linear rolloff to 10 m) | footsteps | -18 |
| Furniture's own moves | pick-up scrape -21, pivot scrape -24, wardrobe -20, warning creak -25, lamp -26, hop -28, soft hop -38 | -20 to -38 |
| UI | click -28, selection tick -34 | -28, -34 |
| Music (Music 100 %) | title -24 I, level **-33 I** | -24, -33 |
| Ambience | room tone -45 I, clock -48 I | -45, -48 |

The level music sits 15 dB under a near footstep and 8 dB under one 6 m away, 5 dB under the player's own hop: it is a
bed, not a mask. Every `gain x mix` stays under 1 (no clamp), checked by `ProbeTestsM3Audio.Step27h` and
`ProbeTestsAudioOverhaul.Step27i`.

## 5. Music

**Chosen** (both Kevin MacLeod, incompetech.com, **CC BY 4.0**, credit shown on the title page in English and French):

| Use | Track | Why | Loop |
|---|---|---|---|
| Title page | "Sneaky Snitch" (87 BPM; oboe, pizzicato string quartet, snare) | the reference sneaky comedy cue; its own description: "the staccato nature of the music suggests walking on tiptoes" | 11.52 to 77.72 s (66.2 s), sample correlation at the seam 0.955 |
| Levels | "Investigations" (94 BPM; pizzicato strings, English horn, bassoon, marimba, glockenspiel) | "a loafing comedic piece ... for scenes with no dialog": calmer and sparser than the title, same plucked family as the title and the win jingle | 18.11 to 58.53 s (40.4 s), seam correlation 0.988 |

**Alternatives considered:**
1. "Cool Vibes" (slow jazz trio: vibraphone, bass, brushed kit; "Calming, Relaxed"): the closest to "upright bass,
   brushed drums, vibraphone", downloaded and analysed for the level. Rejected: it is played loosely, no two passages
   match at the sample level (best loop seam correlation 0.59, 0.39 for a 72 s loop), so any loop would jump; it also
   "modulates at the midpoint".
2. "Hidden Agenda" (xylophone, glockenspiel, bassoon, "Humorous, Suspenseful", 132 BPM) and "Spy Glass" (sax, trumpet,
   vibraphone): too busy for a level, their xylophone and brass sit on top of the footsteps and the creak.
   CC0 first: FreePD (public domain music) was checked first and its comedy page did not answer (HTTP 404); OpenGameArt
   CC0 music was not searched further, MacLeod's catalogue being the brief's own suggestion.

**Loops.** `audio_pipeline.py music` finds the longest stretch whose following seconds match the seconds after an
earlier point (cosine similarity of 40 log band energies, 46 ms frames, 6 s windows centred on the loop point, loops of
at least 50 s for the title and 30 s for the level), refines the lag to the sample by normalised cross-correlation, cuts
`[t1, t2)` and crossfades its last 120 ms into the 120 ms that led into `t1` in the original, so the end flows into the
start. Seam jump 0.004 and 0.001 against a typical sample step of 0.02. Normalised to -18 LUFS integrated, -1 dBTP,
Ogg Vorbis q6 (the source for Unity, sample count checked identical after decoding). Sources: sha256 `db1710333d68...`
(Sneaky Snitch.mp3), `699f7a3cd227...` (Investigations.mp3).

**Player** (`MusicPlayer.cs`, on Main's "Music" child): two looping 2D sources that ignore the listener pause (the
title page and the pause menu pause every game sound). The title page (its level select and Options too) wants the title
loop, anything else the level loop, with a 1.5 s crossfade; a faded loop is paused where it was, so it resumes there.
A catch or a win silences the level loop in 0.25 s so the sting plays alone, and it comes back over 1.5 s on the retry
or the next level. The pause menu ducks it by 6 dB. Volume = gain x mix x Music option x crossfade x duck; the Volume
option (the listener volume) scales it like everything, and `AudioMute` (tests, batch mode, `-mute`) silences it.

**Music option.** `SaveData.options.music`, 0 to 100 % by 10, default **70 %**; a save without it (every save before
this change) loads with 70 and nothing else moves (version stays 1). Options page: a "Music: 70%" / "Musique : 70 %"
row with a beamed-notes icon right under Volume; the page went from 8 to 9 rows, so the row step went from 90 to 80 and
the rows from 84 to 72 reference units high: the last row still clears the bottom of a 20:9 phone.

## 6. Unity import and size

| Kind | Load type | Format | Notes |
|---|---|---|---|
| Percussive one-shots | Decompress On Load | ADPCM | mono, preload on |
| Tonal one-shots (stings, creak, vocal) | Decompress On Load | Vorbis 0.7 | mono, preload on |
| Ambience loops | Compressed In Memory | Vorbis 0.5 | mono |
| Music | **Streaming** | Vorbis 0.7 (PC), **0.5 (Android override)** | stereo, preload off, never forced to mono |

A first build at music quality 0.4 measured 62 to 71 kbps stereo, thin for plucked strings; 0.7 / 0.5 was kept.

| Build | Sounds (build report) | Music files | Total |
|---|---|---|---|
| Android, before (2026-11-18 21:32) | 257.8 KB | none | **APK 37.6 MB** |
| Android, after | 1.2 MB | title 624 KB, level 311 KB | **APK 38.7 MB (+1.1 MB, budget +8 MB)** |
| Windows, after | 1.6 MB | title 877 KB (106 kbps), level 411 KB (81 kbps) | 112.5 MB |

## 7. Verification

All on Unity 6000.3.23f1, 2026-11-18, called directly (no other Unity process).

- Compile (`Builder.SetupAndCompile`, which runs `AudioLibraryBuilder`): no error; "33 effect clips by role, music 2/2".
- EditMode, whole suite: **474 / 474 passed**, including `LicenseTests` (now with `Music_is_cc_by_and_credited_in_game`)
  and the two new Music option tests of `OptionsM6Tests`.
- PlayMode: `ProbeTestsM3Audio` (8, updated for the new roles and the loudness field), the new `ProbeTestsAudioOverhaul`
  (5: new cues and their fallbacks, a real win, the music's streaming and pause settings, title / level / pause / catch
  behaviour and the Music option, the Options row and its fit), `ProbeTestsM6Options` (4), `ProbeTestsM7Quality` (1),
  `ProbeTests.Step09_Restart` (object count), `ProbeTestsM3Look` (11, title page labels): **all passed**.
  `ProbeTestsM5Ui` (10): 9 passed; `Step41b_PlayStartsTheFirstUnwonLevel` fails on its premise "the title is over the
  first level" (the title now shows "title_house", from the untracked `TitleCameraTour.cs` of another work stream):
  not caused by audio, left as is.
- Builds: `Builder.BuildWindows` (Build/Play/OutOfSight.exe) and `Builder.BuildAndroid` both "Result: Success".

## 8. Left to do

- **A listening pass** by the product owner: the music levels against the footsteps (Tuning.MusicLevelMix), the win
  jingle, the wardrobe pair, the door, and whether the recorded crash and topple beat the synthesized ones.
- The dog bark stays synthesized: a full-band CC0 bark is still missing (Freesound has many under CC0 but needs an
  account to download).
- `*.wav` is ignored by the repository's root .gitignore, so the effect WAVs under Assets/ThirdParty/Audio are not in
  git (before and after this change); the music .ogg files, the pipeline and its report are. Rebuild with
  `python tools/audio/audio_pipeline.py sfx` from the staged downloads, or add an exception for that folder.
