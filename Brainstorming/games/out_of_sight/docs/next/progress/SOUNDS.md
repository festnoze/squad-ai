# SOUNDS progress (the furniture's step and the caught stings, redesigned)

Agent SOUNDS, 2026-11-24. User request: the clicking of the furniture when it moves "plus feutre, mais brillant" (felted and
soft, with a bright pleasant sparkle, neither dull nor harsh), and a more crafted "caught" sound.

## What plays on a move step

- Every hopping furniture (chair, stool, armchair, lamp, rocking chair, wardrobe...): one hop sound per hop
  (`FurnitureController.HopCount`, every pi / `Tuning.HopFrequency` = 0.224 s while it travels or turns), played by
  `GameState.PlaySounds`: `Sfx.PlayHop` (hop_01..04, mix `SfxHopMix`, -32 LUFS) or, on a rug, in a soft room or masked by
  a robot's hum, `Sfx.PlaySoftHop` (hop_soft_01..04, mix `SfxSoftHopMix`, -42 LUFS). Variants never repeat twice in a row,
  pitch 0.92 to 1.08 per hop.
- A hop taken while pivoting hard on the spot plays a leg scrape (scrape_01..03) instead: unchanged.
- The office chair (`Body.Glides`) never hops: it plays the synthesized caster roll (`Sfx.PlayRoll`) every 0.3 s. Unchanged.
- The stool's rattle (`SetRattle`) only plays when it goes too fast (the tip tell), the rocking chair's creak only when it
  rocks: not part of a normal step. Unchanged.

So the "cliquetis" is the hop: the 8 files hop_01..04 and hop_soft_01..04 (rubberduck's recorded wood knocks until now,
sharp onsets, some with a bounce).

## The new sounds

All made by `tools/audio/make_sounds.py` (venv `tools/audio/.venv`, numpy/scipy/soundfile/pyloudnorm), same file names, mono
44.1 kHz 16-bit, 40 Hz high pass, fades to exact zero, loudness matched to the -12 LUFS (100 ms max) file target of
`audio_pipeline.py` under -1 dBTP, so the Tuning playback targets are unchanged.

- **hop_01..04** (0.19 s, under the 0.224 s hop interval): a felt-padded wooden foot (five damped wood modes from about
  155 to 1000 Hz, Q about 20, a 3.2 to 3.8 ms raised cosine attack instead of a click, a faint dark felt "puff") plus a
  small glassy tick on top, 11 dB under the foot (glockenspiel bar partials 1 : 2.76 : 5.40 at 2.6 / 3.1 / 3.5 / 4.0 kHz,
  a drawer pull ringing softly). Variants differ in wood pitch and damping, tick pitch, and a single tick or a "ti-tink".
- **hop_soft_01..04** (0.16 s): the same foot lower, more damped, 1 kHz low passed, the tick 12 dB further down.
- **sting_caught** (1.45 s): a 70 ms swish into a soft brass stab on B dim7 (with a low octave and a small fall), a soft
  orchestral kick and a choked cymbal; a marimba runs down the chord (Ab5 F5 D5 B4); it lands on a low pizzicato G with a
  marimba G3 and a muted brass "bwomp" falling a semitone (G7b9: the "oops" left hanging); a small warm room reverb.
- **sting_caught_long** (2.6 s, the slow defeat): the same palette, a muted brass "wah wah wah waaah" (D4 C#4 C4 B3, a harmon
  formant opening on each note, the last held with vibrato and a fall), the marimba doubling an octave up, a low pizzicato
  G, kick, choked cymbal and a marimba G B D under the held B (a G major "aww"), same reverb.

Analysis (make_sounds_report.json; RMS frequency = power weighted brightness, the test's measure):

| | old | new |
|---|---|---|
| hop (hard) RMS frequency | 400 to 630 Hz | 770 to 1130 Hz |
| hop attack | 20 to 27 dB jump in 1 ms (a click) | 3.2 to 3.8 ms soft rise |
| hop energy above 6 kHz | 0.01 to 0.3 % | 0.15 % (not harsh) |
| hop_soft RMS frequency | 190 to 420 Hz | 250 to 330 Hz |
| caught peak / length | -8 dBFS, 0.38 s | -4.7 dBFS, 1.45 s |
| long peak / length | -8.5 dBFS, 1.11 s | -4.7 dBFS, 2.6 s |

No clipped sample, DC under 4e-5, first and last samples 0 in every file.

## Files changed

- `Assets/ThirdParty/Audio/hop_01..04.wav`, `hop_soft_01..04.wav`, `sting_caught.wav`, `sting_caught_long.wav` (replaced,
  same .meta, same GUIDs).
- `Assets/Editor/AudioLibraryBuilder.cs`: the new loudness numbers (-12.0 for all ten), the hard hops now `Kind.Tonal`
  (Vorbis: the ringing tick would show ADPCM hiss).
- `Assets/Resources/AudioLibrary.asset`: rebuilt by `Builder.SetupAndCompile`.
- `tools/audio/make_sounds.py` (new), `tools/audio/make_sounds_report.json` (new); `tools/audio/audio_pipeline.py` no longer
  lists the ten files (its "sfx" command would have overwritten them with the old recordings).
- `Assets/Scripts/Core/Credits.cs`: 0new4y's trumpet and rubberduck's "75 CC0 breaking / falling / hit sfx" are no longer
  used, so no longer credited; the "other sounds" line now says the furniture's steps and the caught stings are made for the
  game. `docs/LICENSES.md`: their six rows replaced by a "Made for the game" paragraph.
- `Assets/Tests/PlayMode/ProbeTestsM3Audio.cs`: new `Step27i_MoveStepAndCaughtStingsAreShaped` (on the imported clips: hard
  hop RMS frequency 550 to 2500 Hz, each soft hop under 0.6 x the darkest hard hop, every hop shorter than the hop interval,
  short sting 0.9 to 1.6 s, long sting longer and under 3 s, no clipping, no DC, silent edges).
- `Assets/Scripts/Runtime/Sfx.cs`: the PlayCaught summary only.

Listen without the game: `Build/sounds/new/*.wav` (new) and `Build/sounds/old/*.wav` (the replaced files).

## Results

- Unity run 1, `Builder.SetupAndCompile` (Build/sounds_setup.log): compiled, AudioLibrary rebuilt (33 effect clips, 4
  importers updated: the hard hops to Vorbis).
- Unity run 2, `ProbeTestsM3Audio` PlayMode (TestResults/sounds.xml): 9/9 passed, Step27i included. Measured on the
  imported clips: hard hops 769 / 901 / 1009 / 1119 Hz RMS frequency, muffled hops 249 / 279 / 286 / 329 Hz (the same as the
  script's numbers on the WAVs: the Vorbis import keeps the brightness).
- Unity run 3: Windows build `Build/Play/OutOfSight.exe` (Build/pc.log): Success (no OutOfSight process was running). No APK.

## A VERIFIER

- Listen to `Build/sounds/new/hop_01..04.wav` against `Build/sounds/old/`: is the tick bright enough, or too present? One
  knob: `TICK_RMS_RATIO` in make_sounds.py (0.28 now; 0.2 softer, 0.4 brighter), then rerun the script and SetupAndCompile.
- In game, a long walk on a hard floor (4 hops per second): does the tick get tiring? The pitch jitter (0.92 to 1.08) and 4
  variants should keep it alive.
- The muffled step on a rug: still audible enough at -42 LUFS with a darker file?
- The caught sting: is the "busted" hit clear over the level music, and is the landing ("bwomp") funny rather than sad?
- The long sting is 2.6 s (the old one 1.1 s): check it does not overlap the end panel's own sounds awkwardly.

## SOUNDS2 (2026-11-24): the move step becomes a muffled carpet footstep

User request: the felted wood with a glassy tick did not suit furniture at all; the step should sound like a FOOTSTEP,
muffled, as if walking on carpet. Only the eight hop files change; the caught stings are kept as they are (the script now
writes them only with `--stings`, and they regenerate bit identical).

Design (`make_hop`, `padded_impact`, `fabric_brush` in `tools/audio/make_sounds.py`, same venv `tools/audio/.venv`):

- **hop_01..04** (0.20 s, under the 0.224 s hop interval): a low padded thump (a 94 to 134 Hz sine whose pitch sags about
  25 % as the pile and underlay compress), a low-mid noise body (the pile squashing, 150 to 950 Hz), both under a 3.5 to
  5 ms raised cosine attack (short, never a click), a gentle tanh squash (about 2 dB less crest, so every file reaches
  -12 LUFS under -1 dBTP) and a 1.5 kHz low pass; on top a faint fabric whisper (1.3 to 4.2 kHz band passed noise with a
  fibrous flutter, 11 to 14 dB under the body, rolled off above 5 kHz). Variants: 01 a firm heel with a short scuff, 02
  heel then toe 55 ms later, 03 a light toe-led step (more pile, a longer brush), 04 a heavy heel then toe 70 ms later.
- **hop_soft_01..04** (0.18 s): the same step on a thick rug: pitch x0.9, attack x1.7, the body band narrowed and low
  passed at 550 Hz, the toe contact 3 dB down, the whisper 9 dB down and under 2.2 kHz. The files keep the same -12 LUFS
  target; the 10 dB drop is the mix's (`Tuning.SfxSoftHopMix` -42 against `SfxHopMix` -32), unchanged.

Analysis (make_sounds_report.json, old = the SOUNDS felted hops):

| | old (felt + tick) | new (carpet) |
|---|---|---|
| hop RMS frequency | 774 / 910 / 1009 / 1125 Hz | 722 / 625 / 882 / 512 Hz |
| hop spectral centroid | 373 to 487 Hz | 290 to 561 Hz |
| hop energy above 1.5 kHz | 7.3 % (the tick) | 2.4 to 6 % (the whisper) |
| hop energy above 6 kHz | 0.15 % | 0.01 to 0.05 % |
| hop peak / RMS | -4.0 to -2.5 / -17.7 dBFS | -5.2 to -1.7 / -18.0 dBFS |
| hop_soft RMS frequency | 248 / 279 / 286 / 327 Hz | 214 / 224 / 320 / 206 Hz |
| hop_soft energy above 1.5 kHz | 0.5 % | 0.1 to 0.2 % |
| hop_soft peak / RMS | -4.5 to -3.2 / -17.0 dBFS | -5.3 to -1.1 / -17.5 dBFS |
| loudness (100 ms max) | -12.0 LUFS | -12.0 LUFS (none peak limited) |

No clipped sample, DC under 1.1e-4, first and last samples 0, first 2 ms at -16 to -37 dBFS (a soft onset), last 2 ms
under -92 dBFS.

Files changed:

- `Assets/ThirdParty/Audio/hop_01..04.wav`, `hop_soft_01..04.wav` (replaced, same .meta, same GUIDs).
- `tools/audio/make_sounds.py`: the carpet step generator replaces `felt_foot` and `glass_tick`; hops only by default,
  `--stings` for the stings; backups in `Build/sounds/old2/`, new hops in `Build/sounds/new2/`; a `>1k5` energy column.
- `tools/audio/make_sounds_report.json`: rewritten.
- `Assets/Editor/AudioLibraryBuilder.cs`: the hard hops back to `Kind.OneShot` (ADPCM; Vorbis was only for the ringing
  tick); loudness numbers unchanged (-12.0).
- `Assets/Tests/PlayMode/ProbeTestsM3Audio.cs`, `Step27i_`: hard hop RMS frequency 380 to 950 Hz (was 550 to 2500), their
  mean under 800 Hz (the felted step averaged about 950), each soft hop under 0.7 x the darkest hard hop (was 0.6) and
  under 400 Hz. Not run (the user runs the tests): filter `ProbeTestsM3Audio`.

Listen without the game: `Build/sounds/new2/*.wav` (carpet) against `Build/sounds/old2/*.wav` (felt and tick).

Knobs if needed: the whisper level is the brush dB of each `HOP_VARIANTS` row (-11 to -14; lower is quieter),
`IMPACT_LOWPASS_HZ` (1500) and `SOFT_IMPACT_LOWPASS_HZ` (550) set how muffled, `SQUASH` (2.0) the crest. Rerun the
script, then `Builder.SetupAndCompile`.
