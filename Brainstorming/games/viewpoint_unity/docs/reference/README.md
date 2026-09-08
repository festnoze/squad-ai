# Reference frames

One directory per tier of `docs/PRD_VISUAL.md`, written by
`VIEWPOINT.exe --shot` and saved as JPEG quality 80. Section 3.5 of that
document calls these "the one place binary files are welcome: they document,
they do not ship", and section 6.1 makes reviewing them the thing that actually
signs a tier off:

> A person signs a tier off on those frames; nothing else counts as done.

So these are not decoration. Every tier is meant to be compared side by side
with the previous tier's set, by eye, by a person. The harness cannot do it:
`verify-player.ps1` reported PLAYER VERT for a build in which bloom, vignette,
colour grading and antialiasing were all silently switched off, because a game
that starts, runs, throws nothing and photographs itself looks green from the
outside. Only the pictures showed it.

`diagnostics.txt` is saved beside each set: it is what the game says about
itself in that build (shaders resolved, renderers with materials, eye height,
mean colour per frame).

## Sets

| set | state |
|---|---|
| `tier-01/` | Tiers 0 and 1: pipeline settings, post-processing, warm/cool lighting, the sun, clouds, the abyss, distance fog, the teleporter and battery lights. Verified: 101 EditMode, 29 PlayMode, 0 design defects, player green. |

## How to regenerate

    ./verify-player.ps1          # builds, runs --shot, checks, leaves PNGs in Build/Windows/Shots

then convert that directory to JPEG 80 into a new `tier-N/`.

## What to look for

The audit in section 1.1 of the PRD lists what was wrong at the start. Each set
should be read against it: do surfaces read as materials, do edges catch light,
do objects sit in the world, do emissives glow and nothing else, is there depth
to the horizon, does the abyss read as depth rather than as a floor, and above
all does the colour language still separate at a glance - grey permanent, pale
carvable, lavender ephemeral, steel sealed, lead inert, amber live.
