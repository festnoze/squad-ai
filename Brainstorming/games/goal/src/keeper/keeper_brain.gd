class_name KeeperBrain
extends RefCounted
## The goalkeeper's head. Pure logic: no node, no scene, no stored state, and no
## dependency beyond Field (geometry) and Aero (flight).
##
## The single design rule of this module is that THE KEEPER DOES NOT CHEAT. He
## never reads the true strike parameters. He only ever sees two things:
##
##   1. the lossy cue dictionary produced before contact by ShotModel.tell_cues,
##      which is body language, not truth, and
##   2. a progressively converging estimate of the flight rebuilt from the part
##      of the path he has already watched.
##
## Everything that makes a level harder is perception and athleticism. Never
## omniscience.
##
## Why that matters, in numbers. A penalty struck at 28 m/s covers the 11 m to
## the line in about 0.41 s. Human reaction is about 0.2 s, and a full lay out
## dive to the post takes about 0.6 s. Subtract and the conclusion is brutal: a
## keeper who WAITS cannot reach a well placed corner, whatever his level. To
## have any chance he has to GAMBLE, and commit before the ball is even struck.
##
## That is the whole drama of the module and it is deliberately not damped out:
##
##   - a gamble that guesses right produces a spectacular, physically honest save
##   - a gamble that guesses wrong leaves him going the wrong way, and the goal
##     is an open one
##   - a keeper who stands up saves what comes at him: the middle, the weak, the
##     miscued
##
## Higher levels read the cues better, react faster, dive faster and reach a
## little further, and they gamble MORE INTELLIGENTLY rather than more often. A
## Legende actually gambles slightly LESS than a Debutant, because he trusts his
## reflexes for everything inside two metres.
##
## Three things carry the difficulty of this module, and they are all perception
## or athleticism. None of them is omniscience.
##
##   1. THE HEIGHT READ. A dive to the correct corner at the wrong height goes
##      straight past the ball, so reading the height is worth exactly as much as
##      reading the side. It comes from `lift_hint`, the body language cue that
##      says whether the shooter is leaning back over the ball or standing on top
##      of it, degraded by read_skill like every other cue.
##
##      AND THE POSE MUST BE ABLE TO SPEND IT. This is the point the module got
##      wrong for a long time and it is worth stating plainly. `dive_pose` used to
##      take a (side, height) enum pair, which chopped the goal into nine boxes.
##      Two adjacent dive heights are 0.83 m apart at the ball; a glove is 0.16 m
##      and a forearm 0.145 m. So a keeper who read the height to within a hand's
##      width dived into the wrong box and missed exactly as cleanly as one who
##      read it backwards, and every extra point of read_skill above the width of
##      a box bought precisely nothing. The pose now takes a CONTINUOUS world
##      point and every part of it is read off that point, which is what turns
##      perception back into a save rate. See dive_pose.
##   2. THE SAVE ENVELOPE. A keeper stops the ball with a forearm, a shin, a
##      trailing leg and a chest, and a keeper who stays at home makes himself
##      big rather than standing to attention. Both are modelled, honestly, as
##      geometry: see the radii below and the centre spread in dive_pose.
##   3. THE COMMITMENT. Not how often he gambles, which is a coin flip he cannot
##      improve, but where and when: a better reader picks the right corner more
##      often and can afford to leave later, which keeps him feintable.
##
##      "When" is owned by the body (see Keeper._should_commit) but the physics it
##      plans against lives here, in dive_time_needed. A gamble buys a HEAD START,
##      never an early launch for its own sake: he leaves when the flight left is
##      down to what the dive costs him plus that head start. On a penalty struck
##      at 30 m/s that means he goes at contact and spends the lot. On a scuffed
##      one that takes 0.9 s to arrive it means he WAITS, watches another third of
##      a second, and dives on a read instead of on a hunch. Before that, a mishit
##      penalty found every level of keeper already flat on the turf a quarter of a
##      second early, which is why the save rate on mishits used to be the same
##      17 % for a Debutant and for a Legende.
##
## Determinism: every random draw goes through a seeded RandomNumberGenerator,
## so a given seed replays identically. That is what makes the module testable
## and the replay faithful.
##
## Axis convention, inherited from the contract: the shooter looks towards -Z,
## the goal line is z = 0, and +X is the shooter's right, therefore the KEEPER'S
## LEFT. So `glove_left` lives on the +X side of the body and `glove_right` on
## the -X side. SIDE_RIGHT (+1) means "dive towards +X", which is a dive to the
## keeper's own left. The names follow the world axes, not the keeper's anatomy,
## because every caller works in world space.


enum Level { DEBUTANT = 0, CONFIRME = 1, PRO = 2, LEGENDE = 3 }

const LEVEL_NAMES: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]

## Dive directions and dive heights. THESE NO LONGER SHAPE THE POSE. They are the
## coarse READING of a dive, for the body, the crowd, the audio and the replay,
## which all want to say "he went left, low" and none of which need a metre
## reading. dive_pose takes a continuous point and quantises nothing.
const SIDE_LEFT   := -1     # towards -X
const SIDE_CENTRE := 0
const SIDE_RIGHT  := 1      # towards +X
const HEIGHT_LOW  := 0
const HEIGHT_MID  := 1
const HEIGHT_HIGH := 2

## Radius within which a glove or a boot stops the ball, metres.
## These already fold in the ball radius (0.11): a glove is about 5 cm of padded
## palm, so contact happens at 0.16 between the two centres. Callers therefore
## treat the ball as a point, which is what save_distance() documents.
const GLOVE_RADIUS := 0.16
const BOOT_RADIUS  := 0.13
const BODY_RADIUS  := 0.26

## Catching, as opposed to merely stopping. See catch_quality() below.
## Up to CATCH_SPEED_EASY the whole glove holds the ball; from there the window
## closes linearly onto the middle of the palm, and past CATCH_SPEED_MAX nothing
## is ever held. The two speeds bracket the real range of a penalty: ShotModel
## strikes between 14 and 34 m/s, and a ball still doing 30 m/s at the line is
## not caught by anybody.
const CATCH_SPEED_EASY := 20.0
const CATCH_SPEED_MAX  := 30.0
## Fraction of GLOVE_RADIUS still catchable at CATCH_SPEED_MAX.
const CATCH_PALM_MIN   := 0.55

## The rest of the save envelope, and it matters more than any of the ladders
## below. A keeper is not two glove points and a pelvis sphere: he is a spread
## body with a trailing leg, two forearms and a trunk, and he blocks with all of
## them. Modelling only the joints left an honest hole straight through the
## middle of him, where a ball at chest height passed between a pelvis sphere at
## 0.98 m and two gloves at 1.02 m without touching anything at all, which is
## absurd for a shot hit at a standing man. The contact test therefore also
## sweeps the OUTER part of each limb and a trunk capsule standing on the pelvis.
##
## Every radius already folds in the 0.11 m of ball: a forearm is about 3.5 cm
## thick, a shin 4 cm, and a trunk is 44 cm across the shoulders, hence 0.22
## plus the ball.
const FOREARM_RADIUS := 0.145
const SHIN_RADIUS    := 0.150
const TRUNK_RADIUS   := 0.310
## Length of the trunk capsule above the pelvis, metres: pelvis to the crown on a
## 1.88 m keeper. It runs past the shoulders on purpose, because a head is part of
## a goalkeeper and a ball that hits one does not go in.
const TRUNK_LENGTH   := 0.72
## Fraction of the way from the body centre to a glove or a boot at which the
## blocking segment starts. Closer in than that it is a shoulder or a hip, which
## already sits inside the trunk capsule.
const LIMB_SPAN      := 0.38

# --- Level ladders -----------------------------------------------------------
# Four numbers per level, and nothing else changes. The physics is identical for
# a Debutant and for a Legende.
#
# The ATHLETIC ladder is deliberately narrow and the PERCEPTUAL one deliberately
# wide, because that is where the difference between keepers actually lives. A
# Debutant is not a slow man: he is a trained goalkeeper who dives nearly as fast
# and reaches nearly as far as a Legende, and what beats him is that he cannot
# read a run up, so he goes the wrong way, at the wrong height, at the wrong
# moment. Widening the athletic gap at the BOTTOM would have produced a beginner
# who looks broken rather than one who looks fooled, and it is not done.
#
# THE ONE PLACE THE ATHLETIC LADDER IS NOT NARROW IS ITS TOP STEP, and that is
# deliberate too. Legende is the level the whole difficulty scale is anchored on
# and the only one with a two sided target (62 to 68 % of clean penalties saved
# on the reference aim distribution). Measured properly, on 2016 clean penalties
# per level pooled over six independent seeds of tests/balance_probe.gd, it sat
# at 61.2 % +/- 2.2, a shade under its own floor, and the same figure came back
# from the entirely separate keeper of match_state.gd. The perceptual lever that
# carries the three steps below cannot fix it: read_skill is 0.99 out of 1.0, and
# the whole remaining distance to a perfect reader is worth about one point of
# save rate. So the last few points come from the body, once: the top step of
# reach is 13 cm where the ones below are 4 to 5, and the top step of dive speed
# is 0.51 m/s where the ones below are 0.27. What that buys is measured, not
# assumed: reach alone moves the save rate about 0.25 points per centimetre and
# costs about 0.7 points of the top corner promise per centimetre, which is why
# reach does not carry the change on its own.

## Seconds between seeing and moving. A real elite keeper sits near 0.16 s, which
## is a genuine measured figure for a trained athlete on an expected stimulus,
## not a gift to the game.
const _REACTION_TIMES: PackedFloat64Array = [0.215, 0.196, 0.176, 0.158]
## Peak horizontal speed of the body centre during a dive, m/s. A full layout
## dive covers roughly 2.2 to 3.1 m of ground travel, which is what these give.
## The top step is the wide one, see the block above.
const _DIVE_SPEEDS: PackedFloat64Array = [4.55, 4.82, 5.09, 5.60]
## Radius of the sphere around the body centre a glove can touch at full stretch.
## Total goal line coverage is this PLUS the travel of the dive, which is why a
## gamble is worth so much more than a fast reaction. The top step is the wide
## one, see the block above.
const _REACH_RADII: PackedFloat64Array = [1.22, 1.26, 1.31, 1.44]
## Odds of committing before the strike. A penalty struck at 28 m/s is on the
## line in 0.41 s and no human reaction plus dive covers a corner in that time,
## so a keeper who does not commit early has conceded before the ball is struck.
## Real keepers move before or at contact on the large majority of penalties, and
## these numbers say so. It still goes DOWN with level: a better keeper needs the
## coin flip a little less often, because he trusts his reflexes for everything
## inside two metres and would rather keep the option of reading the flight.
const _GAMBLE_ODDS: PackedFloat64Array = [0.92, 0.89, 0.86, 0.83]
## How much of the body language he actually decodes, 0..1. THIS is the ladder.
## Everything else on this page is within a few per cent between a Debutant and a
## Legende; this runs from a man who sees almost nothing to one who sees almost
## everything, and the save rate follows it because the dive itself is now honest
## enough to land on whatever he read. Spread wider at the top than it used to be
## (0.78 -> 0.82 and 0.96 -> 0.97) because with a continuous dive the difference
## between reading a penalty to within 60 cm and to within 30 cm is the difference
## between a fingertip and a save, and that is where a Pro and a Legende differ.
##
## The four values are not evenly spaced and should not be. What matters to the
## save rate is not the skill but the WIDTH OF THE MISTAKE it leaves, which is
## roughly sqrt( ((1 - 0.94 s) * 1.99)^2 + (0.42 * (1 - 0.88 s) * 3.63)^2 ) metres
## of goal, and that curve is brutally steep near the top: 0.86 leaves 53 cm and
## 0.99 leaves 24 cm. So the ladder is bunched where the metres are, and the four
## numbers below are the solution of that equation for the four requested save
## rates, measured back through tests/balance_probe.gd rather than guessed.
const _READ_SKILLS: PackedFloat64Array = [0.23, 0.75, 0.92, 0.99]
## Time constant of the push off the standing foot, seconds. Small means an
## explosive keeper who is at full speed almost immediately.
const _PUSH_TAUS: PackedFloat64Array = [0.112, 0.106, 0.100, 0.094]
## How long he stays off the ground before landing and skidding, seconds.
const _AIR_TIMES: PackedFloat64Array = [0.64, 0.66, 0.68, 0.70]
## Amplitude and rate of the pre strike shuffle on the line. Deliberately smaller
## than it once was: a keeper who has wandered 70 cm off his line when the ball
## is struck has beaten himself, and the shuffle is theatre, not a handicap.
const _DANCE_AMPS: PackedFloat64Array = [0.26, 0.34, 0.42, 0.50]
const _DANCE_RATES: PackedFloat64Array = [3.1, 3.8, 4.6, 5.4]

# --- Dive shape, sampled along the height of the ball -------------------------
# THESE TABLES ARE NO LONGER INDEXED, THEY ARE SAMPLED. Each one is three anchors
# laid out at the three canonical ball heights of _GUESS_Y (0.42 m along the
# turf, 1.25 m at the chest, 2.10 m under the bar) and _lerp_table() reads them at
# a CONTINUOUS height factor in [0, 2] computed from the target by
# _height_factor(). A ball at 1.6 m gets the dive that belongs at 1.6 m, not the
# nearest of three.
#
# That is the whole point of the rewrite, and it is worth spelling out why. Two
# adjacent dive heights are 0.83 m apart at the ball, against a glove of 0.16 m
# and a forearm of 0.145 m. Quantising the pose therefore threw away a keeper who
# had read the height nearly right: he missed as cleanly as one who had read it
# backwards, and no amount of dive speed or reach could recover a keeper whose
# arm was simply in the wrong band. Sampling instead of indexing costs nothing and
# converts a near miss on the read into a save, which is exactly the difference
# between a goalkeeper and a lottery.

## Body centre lift at full extension, metres, relative to the standing pelvis.
## Low is a body already on the turf, high is a pelvis at about 1.50 m.
const _RISE: PackedFloat64Array = [-0.58, 0.12, 0.52]
## A low dive is the fastest across the ground, a high one trades travel for lift
## and trades it HARD: getting two gloves up to the angle of the bar means going
## up rather than out, and that is precisely why the top corner is the one place
## on the goal a keeper cannot buy with a good guess. Cut this number and the top
## corner stops being the correct answer to a Legende; RAISE it and the top corner
## dies, because since the rewrite the dive stops exactly on the ball instead of
## sliding past it, so every metre of travel granted here is a metre of goal
## bought. It was 0.55 while the pose was quantised and the keeper flew past the
## corner anyway. It is 0.42 now that he no longer does.
const _TRAVEL_SCALE: PackedFloat64Array = [1.06, 1.00, 0.42]
## Vertical component of the reaching direction, against a lateral component of 1.
## Only used for the TRAILING arm and as the fallback bearing of the leading one:
## the leading glove now points straight at the ball, see dive_pose.
const _GLOVE_LIFT: PackedFloat64Array = [-0.62, 0.14, 0.75]
## How much of a real airborne arc this height produces.
const _AIR_SCALE: PackedFloat64Array = [0.42, 0.85, 1.00]

# --- Pose geometry, metres, relative to Field.KEEPER_HOME --------------------

const _STAND_CENTRE_Y := 0.98
const _STAND_GLOVE_X := 0.46
const _STAND_GLOVE_Y := 1.02
const _STAND_GLOVE_Z := 0.17
const _STAND_BOOT_X := 0.19
const _STAND_BOOT_Y := 0.06
const _STAND_BOOT_Z := 0.02

const _PUSH_TIME := 0.11          # loading of the standing foot
const _PUSH_DIP := 0.09           # the crouch before the launch
const _ARM_SWING := 0.14          # arms leave the ready stance this fast
const _FOOT_SWING := 0.16         # trailing foot leaves the turf after the push
const _LEAD_FOOT_SWING := 0.20
## Where full arm stretch lands, as a fraction of the air time. It was 0.92, which
## meant a Legende took 0.64 s to get an arm out. That is not a dive, it is a
## stretch in the warm up: a penalty is on the line in 0.41 s, so a keeper who had
## READ THE SHOT PERFECTLY and thrown himself at exactly the right point still
## arrived three quarters extended and missed by 28 cm. It was the single largest
## thing standing between the module and the requested save rates, and it was
## measured, not guessed: the diagnostic said a Legende aiming within 20 cm of the
## ball was saving one in three. 0.66 puts a Legende's arm out in 0.46 s, which is
## what a real dive looks like and still leaves the glove arriving last (_EXT_LAG).
const _EXT_FRACTION := 0.66
const _EXT_LAG := 1.55            # >1: the leading glove arrives LAST
const _LEAN_LEAD := 0.72          # <1: the body rolls FIRST
const _LEAN_MAX := 1.45           # radians, a fully horizontal layout
const _AIR_SKEW := 0.80           # <1: rises fast, comes down slower
const _HOP_HEIGHT := 0.34         # extra pelvis lift at the peak of the arc
## How much GROUND the body centre still has to cover, in metres, before the move
## counts as a full length dive rather than a spread block. Below it the two blend
## continuously, which is the second half of de-quantising the pose: there is no
## longer a "centre dive" and a "side dive", there is one move whose shape is read
## off how far the ball actually is.
const _SPREAD_SPAN := 0.75
const _CENTRE_SPREAD := 1.00      # a held middle: one arm towards each post
const _CENTRE_TRAIL := 0.86       # both arms extend, not one and a half
const _CENTRE_BOOT_SPREAD := 0.34 # and the base widens with them
## Fraction of the normal extension time a centre block needs. Spreading is not
## diving: a keeper holding the middle does not have to travel anywhere, he only
## has to throw his arms out, and that takes a third of a second rather than the
## two thirds a full layout dive needs to arrive. Before this the star opened so
## slowly that a keeper who had read the shot perfectly and stayed at home was
## still only half spread when the ball went past him, which is why a ball in the
## middle third of the goal used to beat every level of keeper.
const _CENTRE_EXT_RATE := 0.55
## How much of the vertical part of a dive a centre block keeps. Three anchors,
## sampled at the ball's own height like every other table up here.
## Holding the middle costs him his TRAVEL, not his legs, but only where the ball
## actually is: he stays low for a ball along the turf, he barely rises for one at
## his chest, and he genuinely LEAPS for one driven at the roof of his own goal.
## Tipping a central ball over the bar from a standing start is a real save, and
## scaling the leap down with the travel used to make it impossible.
const _CENTRE_LIFTS: PackedFloat64Array = [0.28, 0.30, 0.85]
const _SLIDE_TAU := 0.26          # skid after landing
const _FORWARD_LEAN := 0.10       # the body attacks the ball, towards +Z
const _GLOVE_FORWARD := 0.14      # the reaching glove goes in front of the body
const _TRAIL_FRACTION := 0.52     # the second glove follows, half extended
## How much of the chosen HEIGHT the trailing arm shares. Almost none, so the
## trailing arm stays roughly horizontal whatever the lead arm is doing. That is
## what a diving keeper looks like, and it is also worth a great deal: with only
## three dive heights available, a keeper who reads the height one step wrong
## would otherwise miss by the whole gap between two of them. A horizontal
## trailing arm covers the middle band on every dive, so a near miss on the
## height read is a deflection instead of a hole.
const _TRAIL_LIFT := 0.15
const _TRAIL_DROP := 0.18
const _TRAIL_SPREAD := 0.22
const _BOOT_DROP := 0.72          # pelvis to boot when standing
const _BOOT_TUCK := 0.62          # how much of that closes up in a layout
const _BOOT_MIN_Y := 0.055
const _MIN_CENTRE_Y := 0.22
## A glove flat on the turf. Needed now that the leading arm points AT the ball
## instead of along a fixed bearing: aimed at a ball rolling into the bottom
## corner, an unclamped arm buries the glove half a metre under the pitch, which
## is both a rendering fault and a free save on anything low.
const _GLOVE_MIN_Y := 0.06
## How far SIDEWAYS the ball has to be from the body before the leading arm stops
## SPREADING and starts POINTING at it, and over how many metres that hand over
## happens. Inside the near distance the ball is on the trunk capsule, so an arm
## aimed at it is an arm thrown away: a keeper holding the middle covers far more
## goal by making himself wide. Outside it, the arm is the only thing that reaches,
## so it goes straight at the ball and the forearm covers the whole ray in between.
##
## Measured on the LATERAL offset and not on the distance, and that is not a
## detail: keyed on the distance, a ball straight above the keeper's head swung the
## arm from horizontal to vertical over five centimetres of target, which put a
## 22 cm step into a pose that is supposed to be continuous.
const _AIM_MIX_NEAR := 0.20
const _AIM_MIX_SPAN := 0.35
## Lateral offset over which the two arms hand the ball over to each other.
##
## SOMEBODY has to reach for the ball, and for a ball dead in front of him it is
## arbitrary which arm does. Left to a bare sign test that arbitrary choice becomes
## a 1.8 m jump in the pose the moment the target crosses the keeper's own x, which
## is a visible pop on screen and a hole in the save envelope. So the two possible
## poses are BLENDED across this band instead, and at x = 0 exactly the result is
## the symmetric one, which is also what a keeper holding the middle really looks
## like. Outside the band only one of them is ever built.
const _ARM_HAND_OVER := 0.35
const _TRAIL_BOOT_BACK := 0.55
const _LEAD_BOOT_FWD := 0.30

# --- Cue reading -------------------------------------------------------------

## aim_hint and lift_hint arrive ALREADY degraded by read_skill (ShotModel
## .tell_cues does it), so they are never degraded again here. Applying the same
## factor twice is the classic bug of this codebase.
const _AIM_WEIGHT := 0.95
## Weight of lift_hint in the height decision. It dominates on purpose: it is the
## only cue that actually knows whether the ball is going low or high. Before it
## existed the height came from the power alone, which read every hard shot as
## low and handed over every top corner for free, and no amount of dive speed can
## fix a keeper who is diving at the wrong height.
const _LIFT_WEIGHT := 0.85
## Residual power and tempo terms of the height read: a driven shot still tends
## to stay low, and a walked up placed strike is the one that gets dinked.
const _HEIGHT_POWER := 0.10
const _HEIGHT_TEMPO := 0.08
const _PLANT_WEIGHT := 0.55       # the plant foot is the honest tell
const _HIP_WEIGHT := 0.40         # open hips point at the target
const _RUN_WEIGHT := 0.22         # the run up angle leaks a little
## How wrong a poor reader gets it, in units of the lateral tell. One unit is
## _HUNCH_X_SLOPE metres of goal, so this really is the width of his mistake and
## not an abstract knob: 0.42 scaled by the skill term below is 1.22 m of goal for
## a Debutant and 0.20 m for a Legende. The skill term is steep on purpose. Reading
## a run up is the skill this ladder is made of, and the previous 0.75 slope left
## even a Legende half a metre out, which a continuous dive turns into a miss just
## as reliably as a quantised one did.
const _MISREAD_SIGMA := 0.42
const _MISREAD_SKILL := 0.88      # fraction of the misread a perfect reader loses
const _HEIGHT_SIGMA := 0.10
const _FEINT_CONFUSION := 0.55    # each feint scrambles the read this much
const _FEINT_DELAY := 0.045       # and holds him this many seconds longer
## How near the middle the read has to be before the REPORTED side comes back as
## SIDE_CENTRE. It no longer decides anything about the pose: since read_cues
## started carrying a continuous target, "how far towards the post he goes" is a
## distance and not a category, and dive_pose turns a small offset into a spread
## by itself. This band only shapes the coarse label the body and the crowd hear.
const _CENTRE_BAND_LOW := 0.26
const _CENTRE_BAND_SKILL := 0.15
## Calibrated against the reticle mapping and against _GUESS_Y below, which puts
## a low dive at 0.42 m, a mid one at 1.25 m and a high one at 2.10 m. The natural
## hand overs sit halfway between those, at 0.84 m and 1.68 m of ball height, and
## with a typical hard strike the score crosses these two cuts exactly there.
const _HEIGHT_LOW_CUT := 0.10
const _HEIGHT_HIGH_CUT := 0.46
## How much of a head start a committed keeper ALLOWS himself, in seconds before
## contact. Held down on purpose. A third of a second buys enough ground travel to
## cover the whole of one side of the goal, top corner included, which both kills
## the corner as an answer and makes the keeper trivially feintable. A fifth is the
## honest compromise: it covers a corner at mid and low height, which is what a
## gamble should buy, and leaves the angle of the bar alone.
##
## Allows, not spends. What he actually takes is decided during the flight by
## Keeper._should_commit, which pushes off at the last responsible moment and can
## only reach back as far as this permits. On a hard penalty that is the lot; on a
## scuffed one that gives him a whole extra half second it is none of it.
##
## Confidence below which a read is not worth committing on at all, the
## confidence at which it is worth committing on fully, and the share of the coin
## flip that survives at the bottom. Calibrated against what a read of a given
## strength actually means: a tell pointing hard at a post lands around 0.65 of
## confidence and must be gambled on, one pointing vaguely half way lands around
## 0.35 and is better answered by standing up and reading the flight, and a read
## of nothing at all must not put him on the turf.
const _COMMIT_GATE := 0.15
const _COMMIT_FULL := 0.62
const _COMMIT_FLOOR := 0.12
const _EARLY_MIN := 0.02          # seconds before contact, unconfident gamble
const _EARLY_MAX := 0.26          # seconds before contact, fully convinced
const _EARLY_FLOOR := 0.0
const _EARLY_SKILL_HOLD := 0.20   # a good reader can afford to wait longer

# --- Perception of the flight ------------------------------------------------

const _LINE_PLANE_Z := 0.0        # he judges the crossing at the goal line
const _MAX_LOOKAHEAD := 2.5       # seconds of flight he bothers to extrapolate
const _ERROR_ACUITY_WORST := 0.070
const _ERROR_ACUITY_BEST := 0.026
const _ERROR_LATENCY := 0.06      # visual pipeline delay folded into the model
const _ERROR_MIN_WINDOW := 0.02   # never divide by nothing
const _ERROR_FLOOR := 0.05
const _ERROR_CEIL := 3.0          # wider than the goal: a worthless estimate
const _WOBBLE_RATE := 11.0        # rad/s of the slow drift of the estimate
const _BIAS_CLAMP := 2.5

# --- Decision ----------------------------------------------------------------

const _TRUST_SCALE := 0.45        # error at which he half trusts what he sees
const _GUESS_X := 2.55            # x a fully convinced side read points at
const _GUESS_Y: PackedFloat64Array = [0.42, 1.25, 2.10]
## --- Turning the raw tells into a point on the goal line ---------------------
##
## `side` and `height` are a THRESHOLDING of the two raw tells, and thresholding
## throws away most of what the keeper read. These two numbers put it back: they
## are the calibration that maps the raw lateral tell and the raw height score
## onto the metres of goal they are actually talking about. Both are derived from
## the cue chain rather than invented, and tests/test_keeper_brain.gd checks the
## derivation by measuring it end to end.
##
## LATERAL. With a perfect reader, `lateral` comes out at aim_hint * _AIM_WEIGHT
## plus the body tell, which works out at about 1.21 units per unit of reticle x,
## and ShotModel.aim_point spans 4.40 m of goal per unit of reticle x. So one unit
## of lateral tell is 4.40 / 1.21 = 3.63 m of goal.
const _HUNCH_X_SLOPE := 3.63
## HEIGHT. height_score is 0.50 + _LIFT_WEIGHT * lift_hint minus the small power
## and tempo terms, lift_hint is 2 * reticle y - 1, and aim_point spans 0.11 m to
## 3.04 m of goal over that reticle. Fold those together and one unit of score is
## 1.72 m of goal, with a score of zero pointing at 0.845 m.
##
## Getting this wrong is not a rounding error. The first cut of the continuous
## hunch anchored the slope on the two decision cuts instead, came out 2.7 times
## too steep, and had a Legende who had read a chest high penalty perfectly diving
## at a point 70 cm over the ball. It cost the Legende half his save rate.
const _HUNCH_Y_BASE := 0.845
const _HUNCH_Y_SLOPE := 1.724
const _HUNCH_Y_MIN := 0.12
const _HUNCH_Y_MAX := 2.60
## Fraction of full arm extension the leading glove has to have reached by the
## time the ball arrives for the save to count as makeable. Used by
## dive_time_needed to decide the last responsible moment to push off.
const _ARRIVAL_EXT := 0.80
## Same decision after contact, on the estimated crossing point rather than on a
## hunch, and for the same reason: inside this the spread centre block is a better
## answer than a dive.
const _SIDE_PICK_BAND := 0.95
## Where a read of the crossing HEIGHT hands over between a low, a mid and a high
## dive. Both sit a little under the midpoint of the guess heights below, because
## a dive that goes too high still has a trailing arm across the middle band while
## one that goes too low has nothing at all above it.
const _HEIGHT_PICK_LOW := 0.85
const _HEIGHT_PICK_HIGH := 1.60
const _TARGET_HALF_X := 4.20
const _TARGET_MAX_Y := 2.80

const _DANCE_RAMP := 0.30
const _DANCE_MAX := 0.9


# =============================================================================
# Level ladders
# =============================================================================

## Seconds between seeing something and starting to move.
static func reaction_time(level: int) -> float:
	return float(_REACTION_TIMES[_level(level)])


## Peak horizontal dive speed, m/s.
static func dive_speed(level: int) -> float:
	return float(_DIVE_SPEEDS[_level(level)])


## Glove reach from the standing centre at full extension, metres.
## Measured from the BODY CENTRE, so the coverage of the goal line is this plus
## whatever the dive itself travelled.
static func reach(level: int) -> float:
	return float(_REACH_RADII[_level(level)])


## Odds the keeper commits before the strike rather than waiting, when the body
## language he just read was unmistakable. A murkier read scales this down, see
## read_cues: gambling on a tell you did not actually see is not gambling, it is
## guessing, and it is what leaves a keeper on the turf while the ball goes the
## other way.
static func gamble_chance(level: int) -> float:
	return float(_GAMBLE_ODDS[_level(level)])


## How much of the shooter's real aim leaks into the cues, 0..1.
static func read_skill(level: int) -> float:
	return float(_READ_SKILLS[_level(level)])


# =============================================================================
# Pre strike read
# =============================================================================

## Pre strike read of the shooter's body language.
##
## `cues` carries: "run_angle" (-1..1), "approach_speed" (0..1),
## "plant_offset" (-1..1), "hip_yaw" (radians), "feints" (int),
## "aim_hint" (-1..1, already degraded by read_skill), "power_hint" (0..1),
## "lift_hint" (-1..1, already degraded by read_skill, -1 along the turf and +1
## up under the bar).
##
## Returns {"side": int, "height": int, "target": Vector3, "confidence": float,
##          "commit": bool, "commit_time": float}
##
## `target` is the same read expressed as a CONTINUOUS point on the goal line, and
## it is what choose_dive actually aims at. `side` and `height` are the coarse
## reading of it, kept because the body, the audio and the replay talk in those
## terms; nothing in the pose is quantised by them any more.
##
## `commit_time` is negative when the keeper dives BEFORE the strike, measured in
## seconds relative to contact. When he decides to stand up and watch it is
## positive and equal to his reaction time, which is the earliest he could move
## once the ball is away.
##
## Confidence steers all three of WHERE, WHEN and WHETHER, and that is what
## "gambles more intelligently, not more often" means in code. gamble_chance() is
## the CEILING, reached only on a tell he genuinely read; a murkier read scales it
## down towards _COMMIT_FLOOR, and what he does instead is stand up and react,
## which covers the middle and the half side band that an early full length dive
## flies straight past. Nothing here lets him gamble more often than his own
## ladder allows, and a Legende still gambles less often than a Debutant.
static func read_cues(cues: Dictionary, level: int, rng_seed: int) -> Dictionary:
	var lv := _level(level)
	var skill := read_skill(lv)

	var run_angle := _cue(cues, "run_angle", 0.0, -1.0, 1.0)
	var approach := _cue(cues, "approach_speed", 0.5, 0.0, 1.0)
	var plant := _cue(cues, "plant_offset", 0.0, -1.0, 1.0)
	var hip_yaw := _cue(cues, "hip_yaw", 0.0, -PI, PI)
	var aim_hint := _cue(cues, "aim_hint", 0.0, -1.5, 1.5)
	var lift_hint := _cue(cues, "lift_hint", 0.0, -1.0, 1.0)
	var power_hint := _cue(cues, "power_hint", 0.6, 0.0, 1.0)
	var feints := 0
	if cues.has("feints"):
		feints = clampi(int(cues["feints"]), 0, 4)

	var rng := _rng(rng_seed)

	# The honest tells. A poor reader simply does not see them, hence the skill
	# factor here and NOT on aim_hint, which arrives pre degraded.
	var body_tell := plant * _PLANT_WEIGHT + sin(hip_yaw) * _HIP_WEIGHT + run_angle * _RUN_WEIGHT
	var lateral := aim_hint * _AIM_WEIGHT + body_tell * skill

	# A feint shows one thing and does another, so it shrinks every tell towards
	# zero. Applied once, to `lateral` only.
	var confusion := 1.0 / (1.0 + _FEINT_CONFUSION * float(feints))
	lateral *= confusion
	lateral += clampf(rng.randfn(0.0, _MISREAD_SIGMA * (1.0 - _MISREAD_SKILL * skill)), -2.0, 2.0)
	lateral = clampf(lateral, -2.0, 2.0)

	# How sure he FEELS, which is not how right he is. A beginner does not know
	# that what he just read was mostly noise, so he believes it and throws
	# himself at a post exactly as hard as a legend does. Scaling confidence by
	# skill instead would quietly reward being unable to read at all: an unsure
	# keeper stays at home, and standing on your line covers more of the goal than
	# a full length dive to the wrong corner. The ladder has to come from being
	# RIGHT more often, never from doubting more usefully.
	var confidence := clampf(absf(lateral) * (0.85 + 0.15 * skill), 0.0, 1.0)

	var band := _CENTRE_BAND_LOW + _CENTRE_BAND_SKILL * skill
	var side := SIDE_CENTRE
	if lateral > band:
		side = SIDE_RIGHT
	elif lateral < -band:
		side = SIDE_LEFT

	# Height read. lift_hint carries it, because it is the only cue that knows
	# anything about the height at all. The power and tempo terms survive as the
	# secondary reading they always were: a driven shot tends to stay low, and a
	# walked up placed strike is the one that gets dinked over a diving keeper.
	# A feint scrambles the height exactly as it scrambles the side.
	var height_score := 0.50 + _LIFT_WEIGHT * lift_hint * confusion
	height_score += -_HEIGHT_POWER * power_hint + _HEIGHT_TEMPO * (1.0 - approach)
	height_score += clampf(rng.randfn(0.0, _HEIGHT_SIGMA * (1.0 - 0.6 * skill)), -0.6, 0.6)
	var height := HEIGHT_MID
	if height_score < _HEIGHT_LOW_CUT:
		height = HEIGHT_LOW
	elif height_score > _HEIGHT_HIGH_CUT:
		height = HEIGHT_HIGH

	# The same read, un-quantised. "side" and "height" survive because the body,
	# the crowd and the replay talk in those terms, but what the keeper actually
	# aims at is this point, and it moves continuously with how strongly he read
	# the tell. A hunch that says "just right of the middle, chest high" no longer
	# has to be rounded up into a full length dive at a post.
	var hunch := _hunch_point(lateral, height_score)

	# WHETHER to commit is a coin flip weighted by how much he actually saw. This
	# is the other half of "smarter, not more often": a keeper who commits on a
	# tell he never read is not gambling, he is guessing, and the punishment is
	# brutal because a full length dive covers three metres of ground and leaves
	# everything inside that open. Held back, he reacts instead, arrives short,
	# and covers the half side band and the middle that an early dive flies past.
	# A shooter who feints is therefore not just muddling the direction, he is
	# talking the keeper out of committing at all.
	var conviction := clampf((confidence - _COMMIT_GATE) / maxf(_COMMIT_FULL - _COMMIT_GATE, 0.001), 0.0, 1.0)
	var commit := rng.randf() < gamble_chance(lv) * (_COMMIT_FLOOR + (1.0 - _COMMIT_FLOOR) * conviction)
	var commit_time := reaction_time(lv)
	if commit:
		# SQUARED, and that is the whole "smarter, not more often" idea in one
		# line. How early he leaves is how sure he is, and it falls away fast:
		# throwing yourself at a post 0.2 s before contact only pays when the tell
		# was unmistakable, because by the time the ball arrives you have covered
		# nearly three metres of ground and anything nearer the middle than that
		# has gone past behind you. Half sure, he barely leaves early at all and
		# lands on the ball rather than beyond it. Diving PAST the shot is the
		# classic amateur error and this curve is what stops the module making it.
		var early := _EARLY_MIN + (_EARLY_MAX - _EARLY_MIN) * confidence * confidence
		early *= 1.0 - _EARLY_SKILL_HOLD * skill
		early = maxf(_EARLY_FLOOR, early - _FEINT_DELAY * float(feints))
		commit_time = -early

	return {
		"side": side,
		"height": height,
		"target": hunch,
		"confidence": confidence,
		"commit": commit,
		"commit_time": commit_time,
	}


# =============================================================================
# Perception of the flight
# =============================================================================

## Standard deviation of the keeper's guess of the crossing point, metres.
##
## This is a model, not a table of magic numbers. He is solving the same boundary
## value problem the code just solved, but from a handful of retinal samples
## taken over `observed` seconds. The angular resolution of the eye is fixed, so
## the uncertainty on the TRANSVERSE velocity of the ball behaves like
##
##     sigma_v  ~  acuity * distance / observed
##
## and that velocity error is then transported to the line over the `remaining`
## flight time. Folding the constants together leaves an error that falls roughly
## as 1 / observed and grows with how much flight is still left to extrapolate:
##
##     sigma  =  acuity * (remaining + latency) / max(observed, floor)
##
## With the constants above that is about 1.1 m after 20 ms of watching, which is
## worse than useless, and about 0.07 m after 200 ms, which is a save. The whole
## tension of the module lives in that curve.
static func _estimate_error(level: int, observed: float, remaining: float) -> float:
	var lv := _level(level)
	var skill := read_skill(lv)
	var acuity := lerpf(_ERROR_ACUITY_WORST, _ERROR_ACUITY_BEST, skill)
	var window := maxf(observed, _ERROR_MIN_WINDOW)
	var horizon := maxf(remaining, 0.0) + _ERROR_LATENCY
	var sigma := acuity * horizon / window
	if not is_finite(sigma):
		return _ERROR_CEIL
	return clampf(sigma, _ERROR_FLOOR, _ERROR_CEIL)


## The keeper's running estimate of where the ball will cross the line, from the
## part of the flight seen so far. `observed` is the seconds of flight watched.
##
## Returns {"point": Vector3, "time": float, "error": float} where `time` is the
## estimated number of seconds still to run before the ball reaches the line, and
## `error` is the one sigma of the guess in metres. `time` is -1.0 when the ball
## is not going to reach the line at all.
##
## The truth comes from Aero.cross_plane on the OBSERVED state, which is the only
## thing the keeper is allowed to know. The noise added on top is drawn once per
## shot (two fixed misperception axes) and then modulated by a slow drift, so the
## estimate WANDERS towards the truth instead of flickering white noise at 120 Hz.
static func estimate_cross(ball_position: Vector3, ball_velocity: Vector3, spin: Vector3, level: int, observed: float, rng_seed: int) -> Dictionary:
	var lv := _level(level)
	var watched := 0.0
	if is_finite(observed):
		watched = maxf(observed, 0.0)

	if not _is_finite_vec(ball_position) or not _is_finite_vec(ball_velocity):
		push_warning("KeeperBrain.estimate_cross: non finite ball state, estimate refused")
		return {"point": _blind_point(), "time": -1.0, "error": _ERROR_CEIL}

	var safe_spin := spin
	if not _is_finite_vec(safe_spin):
		safe_spin = Vector3.ZERO

	var truth: Dictionary = Aero.cross_plane(ball_position, ball_velocity, safe_spin, Vector3.ZERO, _LINE_PLANE_Z, _MAX_LOOKAHEAD)
	if not bool(truth.get("crossed", false)):
		return {"point": _blind_point(), "time": -1.0, "error": _ERROR_CEIL}

	var true_point: Vector3 = truth.get("point", _blind_point())
	if not _is_finite_vec(true_point):
		return {"point": _blind_point(), "time": -1.0, "error": _ERROR_CEIL}
	var remaining := float(truth.get("time", 0.0))
	if not is_finite(remaining):
		remaining = 0.0
	remaining = maxf(remaining, 0.0)

	var sigma := _estimate_error(lv, watched, remaining)

	var rng := _rng(rng_seed)
	var bias_x := clampf(rng.randfn(0.0, 1.0), -_BIAS_CLAMP, _BIAS_CLAMP)
	var bias_y := clampf(rng.randfn(0.0, 1.0), -_BIAS_CLAMP, _BIAS_CLAMP)
	var phase := rng.randf() * TAU

	var drift := watched * _WOBBLE_RATE + phase
	var offset_x := sigma * (bias_x * 0.75 + sin(drift) * 0.35)
	# Height is read against the frame of the goal, which is a fixed reference the
	# eye is good at, so the vertical guess is better than the lateral one.
	var offset_y := sigma * (bias_y * 0.55 + cos(drift) * 0.25) * 0.70

	var point := Vector3(
		clampf(true_point.x + offset_x, -_TARGET_HALF_X, _TARGET_HALF_X),
		clampf(true_point.y + offset_y, 0.0, _TARGET_MAX_Y),
		_LINE_PLANE_Z
	)

	# A misjudged flight is also a misjudged arrival time, but never a negative one.
	var time_error := sigma * 0.04 * bias_x
	var estimated_time := maxf(remaining + time_error, 0.0)

	return {"point": point, "time": estimated_time, "error": sigma}


# =============================================================================
# Decision
# =============================================================================

## Picks the dive. Called once, the frame the keeper commits.
## Returns {"side": int, "height": int, "target": Vector3, "gambled": bool}
##
## `elapsed` is seconds since contact, so it is NEGATIVE when the keeper is
## committing before the strike. In that case he has watched nothing and the
## pre strike guess is all he has: that is a gamble, flagged as such so the
## renderer, the crowd and the tests can tell the story.
##
## After contact he blends: the sharper his estimate, the more it overrides his
## own hunch. Trust is 1 / (1 + error / scale), so a 5 cm estimate is worth 0.90
## and a 1.1 m estimate only 0.29, leaving the hunch in charge.
static func choose_dive(estimate: Dictionary, guess: Dictionary, level: int, elapsed: float) -> Dictionary:
	var _lv := _level(level)
	var guess_side := SIDE_CENTRE
	if guess.has("side"):
		guess_side = clampi(int(guess["side"]), SIDE_LEFT, SIDE_RIGHT)
	var guess_height := HEIGHT_MID
	if guess.has("height"):
		guess_height = clampi(int(guess["height"]), HEIGHT_LOW, HEIGHT_HIGH)
	# The continuous hunch when read_cues produced one, the coarse (side, height)
	# corner otherwise, so a hand built guess dictionary still works.
	var guess_point := _guess_point(guess_side, guess_height)
	var raw_hunch: Variant = guess.get("target", null)
	if raw_hunch is Vector3 and _is_finite_vec(raw_hunch):
		guess_point = _safe_target(raw_hunch)

	var gambled := true
	if is_finite(elapsed) and elapsed > 0.0:
		gambled = false

	var target := guess_point
	if not gambled:
		var est_point: Vector3 = estimate.get("point", guess_point)
		var est_error := float(estimate.get("error", _ERROR_CEIL))
		var est_time := float(estimate.get("time", -1.0))
		if _is_finite_vec(est_point) and is_finite(est_error) and is_finite(est_time) and est_time >= 0.0:
			# Squared, not linear: a keeper who has genuinely READ the flight to
			# within a few centimetres stops arguing with his own hunch entirely,
			# while a metre wide guess is worth almost nothing and leaves the
			# hunch in charge. A linear falloff leaves a stubborn 10% of the
			# hunch in a read that is already perfect, which shows up on screen
			# as a keeper diving next to a ball he can plainly see.
			var ratio := maxf(est_error, 0.0) / _TRUST_SCALE
			var trust := clampf(1.0 / (1.0 + ratio * ratio), 0.0, 1.0)
			target = guess_point.lerp(est_point, trust)

	target = Vector3(
		clampf(target.x, -_TARGET_HALF_X, _TARGET_HALF_X),
		clampf(target.y, 0.0, _TARGET_MAX_Y),
		_LINE_PLANE_Z
	)

	var side := SIDE_CENTRE
	if target.x > _SIDE_PICK_BAND:
		side = SIDE_RIGHT
	elif target.x < -_SIDE_PICK_BAND:
		side = SIDE_LEFT

	var height := HEIGHT_MID
	if target.y < _HEIGHT_PICK_LOW:
		height = HEIGHT_LOW
	elif target.y > _HEIGHT_PICK_HIGH:
		height = HEIGHT_HIGH

	return {"side": side, "height": height, "target": target, "gambled": gambled}


# =============================================================================
# The dive itself
# =============================================================================

## Keeper limb positions `t` seconds into a dive at `target`, in WORLD space.
##
## `target` is the world point on the goal line the keeper is throwing himself at,
## and it is CONTINUOUS. There is no longer an enum of three sides and three
## heights: the shape of the dive, how far the body travels, how high the pelvis
## goes, how much of an arc it describes, whether it is a full layout or a spread
## block, and where the leading glove points, are all read off that one point.
##
## Two consequences, and they are the reason the signature changed.
##
##   1. A NEAR MISS ON THE READ IS NOW A NEAR MISS ON THE BALL. Quantised into
##      three bands, a keeper who read the height to within 30 cm dived into the
##      wrong band and missed by 80, which is not a goalkeeper, it is a rounding
##      error with gloves on.
##   2. HE STOPS ON THE BALL INSTEAD OF SLIDING PAST IT. The travel is the
##      MINIMUM of what the dive can cover by now and what the target actually
##      requires, so a keeper who has correctly read a ball a metre to his side
##      arrives there and stays there. He used to keep going and end up two metres
##      beyond it, which is why a slow scuffed penalty down the middle used to
##      beat every level of keeper equally.
##
## Returns {"centre": Vector3, "glove_left": Vector3, "glove_right": Vector3,
##          "boot_left": Vector3, "boot_right": Vector3,
##          "lean": float, "airborne": float}
##
## This is what the renderer draws, so it is a dive and not a lerp. Five things
## happen at once and each one is what makes a dive read as a dive:
##
##   1. a PUSH: over the first 0.11 s the pelvis dips into the standing foot and
##      the body loads before anything moves sideways,
##   2. TRAVEL along the dive line, an exponential approach to the peak dive
##      speed (you cannot be at 4 m/s in the first frame), saturating into a skid
##      once he lands,
##   3. EXTENSION of the leading arm on a late biased curve, so the glove is the
##      last thing to arrive. That lag is exactly what makes a fingertip save
##      read as a fingertip save,
##   4. an AIRBORNE arc that peaks around 40% of the flight and comes back down,
##   5. a LEAN that rolls early into the direction of travel, so the body is
##      already horizontal by the time the glove gets there.
##
## `lean` is positive when the crown of the head tips towards +X. `airborne` is 0
## on the ground and 1 at the peak of a full blooded dive (less for a low dive or
## a centre hop, which barely leave the turf).
##
## At t = 0 the result is EXACTLY the standing home pose, whatever target or
## level is asked for. Callers rely on that to blend in and out of a dive.
static func dive_pose(target: Vector3, t: float, level: int) -> Dictionary:
	var lv := _level(level)
	var aim := _safe_target(target)
	var time := t
	if not is_finite(time):
		time = 0.0
	time = maxf(time, 0.0)

	# Which half of the body reaches for the ball is the one genuinely discrete
	# choice left in the pose, and a bare sign test on the target puts a metre and
	# a half of jump into it the instant the ball crosses the keeper's own line.
	# So the hand over is blended: see _ARM_HAND_OVER. Outside the band exactly one
	# pose is built, so this costs nothing on a real dive.
	var dx := aim.x - Field.KEEPER_HOME.x
	var hand := clampf(0.5 + 0.5 * dx / _ARM_HAND_OVER, 0.0, 1.0)
	if hand >= 0.999:
		return _dive_pose_led(aim, time, lv, 1)
	if hand <= 0.001:
		return _dive_pose_led(aim, time, lv, -1)
	var minus := _dive_pose_led(aim, time, lv, -1)
	var plus := _dive_pose_led(aim, time, lv, 1)
	return {
		"centre": (minus["centre"] as Vector3).lerp(plus["centre"], hand),
		"glove_left": (minus["glove_left"] as Vector3).lerp(plus["glove_left"], hand),
		"glove_right": (minus["glove_right"] as Vector3).lerp(plus["glove_right"], hand),
		"boot_left": (minus["boot_left"] as Vector3).lerp(plus["boot_left"], hand),
		"boot_right": (minus["boot_right"] as Vector3).lerp(plus["boot_right"], hand),
		"lean": lerpf(float(minus["lean"]), float(plus["lean"]), hand),
		"airborne": lerpf(float(minus["airborne"]), float(plus["airborne"]), hand),
	}


## The pose for one choice of which arm leads. `aim` is already sanitised, `time`
## is already non negative and `lv` already clamped: dive_pose owns all of that.
static func _dive_pose_led(aim: Vector3, time: float, lv: int, lead_sign: int) -> Dictionary:
	var home: Vector3 = Field.KEEPER_HOME
	var stand_centre := home + Vector3(0.0, _STAND_CENTRE_Y, 0.0)
	var dx := aim.x - home.x
	var trail_sign := -lead_sign

	var stand_lead_glove := home + Vector3(float(lead_sign) * _STAND_GLOVE_X, _STAND_GLOVE_Y, _STAND_GLOVE_Z)
	var stand_trail_glove := home + Vector3(float(trail_sign) * _STAND_GLOVE_X, _STAND_GLOVE_Y, _STAND_GLOVE_Z)
	var stand_lead_boot := home + Vector3(float(lead_sign) * _STAND_BOOT_X, _STAND_BOOT_Y, _STAND_BOOT_Z)
	var stand_trail_boot := home + Vector3(float(trail_sign) * _STAND_BOOT_X, _STAND_BOOT_Y, _STAND_BOOT_Z)

	# Every per height number, read at the height the ball actually has.
	var hf := _height_factor(aim.y)
	var rise := _lerp_table(_RISE, hf)
	var travel_scale := _lerp_table(_TRAVEL_SCALE, hf)
	var glove_lift := _lerp_table(_GLOVE_LIFT, hf)
	var air_scale := _lerp_table(_AIR_SCALE, hf)
	var centre_lift := _lerp_table(_CENTRE_LIFTS, hf)

	# How much GROUND this ball actually costs him. The pelvis ends at the height
	# the dive shape puts it, the arm is `reach` long, so the lateral half of that
	# arm covers what is left after the vertical part is paid for. Anything beyond
	# it is travel, and travel is the expensive currency.
	var needed := _travel_needed(aim, rise, reach(lv), dx)
	# ...and how much of a dive that is. Nothing at all for a ball he can cover
	# standing (he spreads instead, and a spread is fast), a full length layout for
	# one at the post. The two blend, continuously, over _SPREAD_SPAN.
	var commit := clampf(needed / _SPREAD_SPAN, 0.0, 1.0)

	var t_air := float(_AIR_TIMES[lv])
	# Spreading is not diving: see _CENTRE_EXT_RATE.
	var t_ext := t_air * _EXT_FRACTION * lerpf(_CENTRE_EXT_RATE, 1.0, commit)
	var u_ext := clampf(time / t_ext, 0.0, 1.0)

	var body := _smoothstep01(u_ext)
	var ext := _smoothstep01(pow(u_ext, _EXT_LAG))
	var roll := _smoothstep01(pow(u_ext, _LEAN_LEAD))
	var arm := _smoothstep01(clampf(time / _ARM_SWING, 0.0, 1.0))
	var foot := _smoothstep01(clampf((time - _PUSH_TIME) / _FOOT_SWING, 0.0, 1.0))
	var lead_foot := _smoothstep01(clampf(time / _LEAD_FOOT_SWING, 0.0, 1.0))
	var push := clampf(time / _PUSH_TIME, 0.0, 1.0)

	# Holding the middle gives up TRAVEL, not legs: `lift_scale` barely touches how
	# high he goes, and the travel is already limited by `needed` itself.
	var lift_scale := lerpf(centre_lift, 1.0, commit)

	# The arc only begins once the push is finished: while he is still loading the
	# standing foot he is, by definition, on the ground. Without this gate the
	# pelvis starts rising during the crouch, which reads as a hop rather than a
	# dive.
	var airborne := 0.0
	if time > _PUSH_TIME and time < t_air:
		var u_arc := clampf((time - _PUSH_TIME) / maxf(t_air - _PUSH_TIME, 0.001), 0.0, 1.0)
		airborne = sin(PI * pow(u_arc, _AIR_SKEW))
	airborne = clampf(airborne * air_scale * lift_scale, 0.0, 1.0)

	# THE ONE LINE THAT STOPPED HIM SLIDING PAST THE BALL. He travels as far as the
	# dive has managed by now, or as far as the ball is, whichever is the LESS.
	var travel := minf(_dive_travel(time, lv) * travel_scale, needed)

	var centre := stand_centre
	centre.x += float(lead_sign) * travel
	centre.y += rise * body * lift_scale
	centre.y += _HOP_HEIGHT * airborne
	centre.y -= _PUSH_DIP * sin(PI * push) * lift_scale
	centre.z += _FORWARD_LEAN * body
	centre.y = maxf(centre.y, _MIN_CENTRE_Y)

	# Reaching direction. The LEADING glove points straight at the ball, which is
	# what a goalkeeper does and what makes reading the height nearly right worth
	# something: the arm makes up whatever the pelvis did not.
	# The forward component lives INSIDE the reaching direction rather than being
	# added on afterwards, so the leading glove sits exactly reach() from the body
	# centre and never a centimetre more. He attacks the ball in front of his
	# line, which is why the z term is there at all.
	#
	# Near the body it SPREADS instead, because a ball that close is already on the
	# trunk capsule and a keeper holding the middle covers far more goal by making
	# himself wide: one arm towards each post, and that star is what blocks the
	# middle third. The two blend over _AIM_MIX_SPAN.
	var to_ball := Vector2(aim.x - centre.x, aim.y - centre.y)
	var to_len := to_ball.length()
	var spread := Vector2(float(lead_sign) * _CENTRE_SPREAD, glove_lift).normalized()
	var aim_mix := clampf((absf(aim.x - centre.x) - _AIM_MIX_NEAR) / _AIM_MIX_SPAN, 0.0, 1.0)
	var plane := spread
	if to_len > 0.0001:
		plane = spread.lerp(to_ball / to_len, aim_mix)
	if plane.length_squared() < 0.0001:
		plane = Vector2(float(lead_sign), glove_lift)
	plane = plane.normalized()
	# The trailing arm streams out on the side he did NOT commit to, always, and
	# only its LENGTH changes with the commitment. It used to swing across to the
	# leading side as the dive got longer, which put a hole in the pose: half way
	# through that swing its lateral component passes through zero, the direction
	# it is normalised from collapses onto the small forward term, and the glove
	# snaps through 80 cm of arc for 5 cm of ball. A trailing arm on the trailing
	# side is also what a diving keeper looks like from behind, and it covers the
	# side he gave up on, which is worth having.
	var trail_lateral := float(trail_sign) * _CENTRE_SPREAD
	var trail_fraction := lerpf(_CENTRE_TRAIL, _TRAIL_FRACTION, commit)

	var lead_dir := Vector3(plane.x, plane.y, _GLOVE_FORWARD).normalized()
	var trail_dir := Vector3(trail_lateral, glove_lift * _TRAIL_LIFT, _GLOVE_FORWARD).normalized()
	var lead_reach := reach(lv) * ext

	var lead_glove := centre + lead_dir * lead_reach
	lead_glove.y = maxf(lead_glove.y, _GLOVE_MIN_Y)
	lead_glove = stand_lead_glove.lerp(lead_glove, arm)

	var trail_glove := centre + trail_dir * (lead_reach * trail_fraction)
	trail_glove += Vector3(float(trail_sign) * _TRAIL_SPREAD * (1.0 - ext), -_TRAIL_DROP, 0.0)
	trail_glove.y = maxf(trail_glove.y, _GLOVE_MIN_Y)
	trail_glove = stand_trail_glove.lerp(trail_glove, arm)

	# Legs. The trailing foot is the one that pushed, so it stays planted until
	# the push is done and only then trails behind the body.
	var axis := Vector3(float(lead_sign) * commit, 0.0, 0.0)
	var drop := _BOOT_DROP * (1.0 - _BOOT_TUCK * body)
	# Same star on the legs: standing his ground, he widens his base rather than
	# keeping his feet together, which is both what a keeper does and another
	# thirty centimetres of low block on each side.
	var boot_spread := _CENTRE_BOOT_SPREAD * (1.0 - commit) * body

	var trail_boot := centre - axis * _TRAIL_BOOT_BACK + Vector3(float(trail_sign) * (0.12 + boot_spread), -drop, 0.0)
	trail_boot.y = maxf(trail_boot.y, _BOOT_MIN_Y)
	trail_boot = stand_trail_boot.lerp(trail_boot, foot)

	var lead_boot := centre + axis * _LEAD_BOOT_FWD + Vector3(float(lead_sign) * (0.10 + boot_spread), -drop * 1.15, 0.0)
	lead_boot.y = maxf(lead_boot.y, _BOOT_MIN_Y)
	lead_boot = stand_lead_boot.lerp(lead_boot, lead_foot)

	var lean := float(lead_sign) * _LEAN_MAX * roll * commit

	var glove_left := lead_glove
	var glove_right := trail_glove
	var boot_left := lead_boot
	var boot_right := trail_boot
	if lead_sign < 0:
		glove_left = trail_glove
		glove_right = lead_glove
		boot_left = trail_boot
		boot_right = lead_boot

	return {
		"centre": centre,
		"glove_left": glove_left,
		"glove_right": glove_right,
		"boot_left": boot_left,
		"boot_right": boot_right,
		"lean": lean,
		"airborne": airborne,
	}


## Ground travelled by the body centre `t` seconds into a dive, metres.
##
## An exponential approach to the peak speed while airborne, then a skid: the
## keeper cannot accelerate any more once he has landed, he only decelerates. The
## two branches match in value AND in slope at the landing, so the pose has no
## visible kink when he touches down.
static func _dive_travel(t: float, level: int) -> float:
	if t <= 0.0:
		return 0.0
	var lv := _level(level)
	var v := dive_speed(lv)
	var tau := float(_PUSH_TAUS[lv])
	var t_air := float(_AIR_TIMES[lv])
	if t <= t_air:
		return v * (t - tau * (1.0 - exp(-t / tau)))
	var at_land := v * (t_air - tau * (1.0 - exp(-t_air / tau)))
	var v_land := v * (1.0 - exp(-t_air / tau))
	var skid := t - t_air
	return at_land + v_land * _SLIDE_TAU * (1.0 - exp(-skid / _SLIDE_TAU))


## Seconds a dive of this level needs before the leading glove is at full stretch.
## The pose curve is the authority, this is just its extension window named so the
## body can plan against it.
static func extension_time(level: int) -> float:
	return float(_AIR_TIMES[_level(level)]) * _EXT_FRACTION


## Seconds this level needs to have a glove on `target`, pushing off from a body
## centre standing at `from_x` on the goal line.
##
## This is the number the body uses to find the LAST RESPONSIBLE MOMENT to leave,
## and it is the whole reason a slow, scuffed penalty is now a different problem
## from a hard one. It is the longer of two things: the ground travel, inverted
## out of the very same _dive_travel curve the pose uses, and the time the arm
## needs to be _ARRIVAL_EXT of the way out. Neither is a guess about the shot, so
## nothing here lets the keeper see anything he is not allowed to see.
static func dive_time_needed(target: Vector3, from_x: float, level: int) -> float:
	var lv := _level(level)
	var aim := _safe_target(target)
	var start := from_x
	if not is_finite(start):
		start = Field.KEEPER_HOME.x
	var hf := _height_factor(aim.y)
	var rise := _lerp_table(_RISE, hf)
	var travel_scale := maxf(_lerp_table(_TRAVEL_SCALE, hf), 0.05)
	var needed := _travel_needed(aim, rise, reach(lv), aim.x - start)
	var commit := clampf(needed / _SPREAD_SPAN, 0.0, 1.0)
	var ground := _travel_time(needed / travel_scale, lv)
	var swing := extension_time(lv) * lerpf(_CENTRE_EXT_RATE, 1.0, commit) * _ARRIVAL_EXT
	return maxf(ground, swing)


## Ground the body centre still has to cover for a glove to be ON the ball: the
## lateral distance, less whatever the arm covers once the vertical part of the
## reach has been paid for. Zero for a ball he can touch without leaving his spot.
static func _travel_needed(aim: Vector3, rise: float, span: float, dx: float) -> float:
	var home: Vector3 = Field.KEEPER_HOME
	var final_y := maxf(home.y + _STAND_CENTRE_Y + rise, _MIN_CENTRE_Y)
	var vertical := aim.y - final_y
	var lateral := sqrt(maxf(span * span - vertical * vertical, 0.0))
	return maxf(absf(dx) - lateral, 0.0)


## _dive_travel inverted: how long the airborne branch takes to cover `distance`.
## Fixed point rather than closed form, because the curve has no closed inverse;
## it converges in two or three passes and six are budgeted.
static func _travel_time(distance: float, level: int) -> float:
	if not is_finite(distance) or distance <= 0.0:
		return 0.0
	var lv := _level(level)
	var v := dive_speed(lv)
	var tau := float(_PUSH_TAUS[lv])
	var flat := distance / maxf(v, 0.01)
	var t := flat + tau
	for _i in 6:
		t = flat + tau * (1.0 - exp(-maxf(t, 0.0) / tau))
	if not is_finite(t):
		return flat
	return maxf(t, 0.0)


## Continuous height factor of a ball: 0 along the turf, 1 at the chest, 2 under
## the bar, piecewise linear through the _GUESS_Y anchors so the sampled tables
## still hit their authored values exactly at those three heights.
static func _height_factor(y: float) -> float:
	var low := float(_GUESS_Y[HEIGHT_LOW])
	var mid := float(_GUESS_Y[HEIGHT_MID])
	var high := float(_GUESS_Y[HEIGHT_HIGH])
	if not is_finite(y) or y <= low:
		return 0.0
	if y >= high:
		return 2.0
	if y <= mid:
		return (y - low) / maxf(mid - low, 0.001)
	return 1.0 + (y - mid) / maxf(high - mid, 0.001)


## Samples a three anchor table at a continuous factor in [0, 2].
static func _lerp_table(table: PackedFloat64Array, factor: float) -> float:
	var count := table.size()
	if count == 0:
		return 0.0
	if count == 1:
		return float(table[0])
	var f := clampf(factor, 0.0, float(count - 1))
	var i := clampi(int(floor(f)), 0, count - 2)
	return lerpf(float(table[i]), float(table[i + 1]), clampf(f - float(i), 0.0, 1.0))


## The pre strike read as a continuous point rather than a corner of a grid.
## `lateral` is the raw lateral tell and `height_score` the raw height tell, both
## straight out of read_cues, both scaled by the calibration above.
##
## There is deliberately NO dead band here, unlike the side/height thresholds. A
## keeper whose read only just leans right should aim only just right of himself,
## and dive_pose already turns a small offset into a spread rather than a dive.
## Snapping small reads to the middle and large ones to a post is exactly the
## quantisation this whole pass exists to remove.
static func _hunch_point(lateral: float, height_score: float) -> Vector3:
	return _safe_target(Vector3(
		lateral * _HUNCH_X_SLOPE,
		clampf(_HUNCH_Y_BASE + height_score * _HUNCH_Y_SLOPE, _HUNCH_Y_MIN, _HUNCH_Y_MAX),
		_LINE_PLANE_Z))


## A target brought back inside the goal and onto the line, NaN included.
static func _safe_target(target: Vector3) -> Vector3:
	var x := target.x
	var y := target.y
	if not is_finite(x):
		x = Field.KEEPER_HOME.x
	if not is_finite(y):
		y = float(_GUESS_Y[HEIGHT_MID])
	return Vector3(
		clampf(x, -_TARGET_HALF_X, _TARGET_HALF_X),
		clampf(y, 0.0, _TARGET_MAX_Y),
		_LINE_PLANE_Z)


# =============================================================================
# Contact
# =============================================================================

## Shortest distance between the ball's path over one physics step and the
## nearest keeper limb, minus that limb's radius. Negative means contact.
##
## The ball is treated as a POINT and the limb radii already carry the 0.11 m of
## ball. The test is segment against segment, the swept ball path against the
## whole limb, never endpoints against endpoints, so a ball covering 25 cm in a
## physics step can never tunnel through a glove or slip between an elbow and a
## hand.
static func save_distance(pose: Dictionary, ball_from: Vector3, ball_to: Vector3) -> float:
	if not _is_finite_vec(ball_from) or not _is_finite_vec(ball_to):
		return _ERROR_CEIL
	var best := INF
	for entry in _limbs(pose):
		var pair := _closest_between(entry[1], entry[2], ball_from, ball_to)
		var limb_point: Vector3 = pair[0]
		var ball_point: Vector3 = pair[1]
		var signed: float = limb_point.distance_to(ball_point) - float(entry[3])
		if signed < best:
			best = signed
	if not is_finite(best):
		return _ERROR_CEIL
	return best


## Contact test plus what was hit.
## Returns {"saved": bool, "limb": String, "point": Vector3, "normal": Vector3}
## `limb` is one of "glove_left", "glove_right", "boot_left", "boot_right",
## "centre", or "" when nothing was touched.
##
## The limb returned is the one that was ACTUALLY closest, radius included, so a
## ball that grazes a boot and a glove at the same time is credited to whichever
## really got there. The normal points away from that limb, which is what lets
## the ball deflect plausibly rather than simply stopping.
static func try_save(pose: Dictionary, ball_from: Vector3, ball_to: Vector3) -> Dictionary:
	var miss := {"saved": false, "limb": "", "point": ball_to, "normal": Vector3(0.0, 0.0, 1.0)}
	if not _is_finite_vec(ball_from) or not _is_finite_vec(ball_to):
		return miss

	var best := INF
	var best_name := ""
	var best_limb := Vector3.ZERO
	var best_point := ball_to

	for entry in _limbs(pose):
		var limb_name: String = entry[0]
		var pair := _closest_between(entry[1], entry[2], ball_from, ball_to)
		var limb_point: Vector3 = pair[0]
		var closest: Vector3 = pair[1]
		var signed: float = limb_point.distance_to(closest) - float(entry[3])
		if signed < best:
			best = signed
			best_name = limb_name
			best_limb = limb_point
			best_point = closest

	if best_name.is_empty() or best >= 0.0 or not is_finite(best):
		return miss

	var normal := best_point - best_limb
	if normal.length_squared() < 1e-10:
		# Dead centre of the limb: send it back the way it came.
		normal = ball_from - ball_to
	if normal.length_squared() < 1e-10:
		normal = Vector3(0.0, 0.0, 1.0)

	return {
		"saved": true,
		"limb": best_name,
		"point": best_point,
		"normal": normal.normalized(),
	}


## Radius of the palm window at this impact speed, metres. Never negative, never
## rises with speed. A speed that is not a finite positive number is a broken
## input and shuts the window: failing closed here costs a catch, failing open
## would hand the keeper a ball he never had.
static func catch_window(impact_speed: float) -> float:
	var speed := impact_speed
	if not is_finite(speed) or speed < 0.0:
		return 0.0
	if speed >= CATCH_SPEED_MAX:
		return 0.0
	var k := clampf(
		(speed - CATCH_SPEED_EASY) / maxf(CATCH_SPEED_MAX - CATCH_SPEED_EASY, 0.001), 0.0, 1.0)
	return GLOVE_RADIUS * lerpf(1.0, CATCH_PALM_MIN, k)


## Was that save a CLEAN CATCH, or only a parry?
##
## The two outcomes are physically different and the game shows them as such: a
## catch ends the flight in the keeper's hands, a parry puts the ball back into
## play. Deciding between them from the contact itself, rather than from a die
## roll, is what makes the difference readable: you can SEE why the rocket into
## the top corner was only pushed away while the tame one down the middle was
## gathered.
##
## Three conditions, all of them already measured by try_save:
##   1. it has to be a HAND. `limb` names the glove for a forearm block too (the
##      forearm segment is credited to the glove it hangs off), so the contact
##      point is re-measured against the glove itself: past GLOVE_RADIUS from it
##      the ball hit an arm, and an arm parries. A boot, a shin or the trunk is
##      a block by definition and never a catch.
##   2. it has to be in the PALM, and how much palm there is depends on the
##      speed: catch_window() above.
##   3. it has to be slow enough to hold at all.
##
## `pose` is the pose the save was tested against, `save` a try_save dictionary
## and `impact_speed` the ball speed at contact, in m/s.
## Returns {"catch": bool, "grip": float, "hand": String, "offset": float}
## `hand` is the glove that holds it, or "" for a parry. `grip` is 1 at the dead
## centre of the palm and 0 at the edge of the window, so a caller can make a
## marginal catch look and sound different from a comfortable one.
static func catch_quality(pose: Dictionary, save: Dictionary, impact_speed: float) -> Dictionary:
	var miss := {"catch": false, "grip": 0.0, "hand": "", "offset": _ERROR_CEIL}
	if not bool(save.get("saved", false)):
		return miss
	var limb := String(save.get("limb", ""))
	if limb != "glove_left" and limb != "glove_right":
		return miss
	var hand := _pose_point(pose, limb)
	if not bool(hand[1]):
		return miss
	var raw_point: Variant = save.get("point", null)
	if not (raw_point is Vector3):
		return miss
	var point: Vector3 = raw_point
	if not _is_finite_vec(point):
		return miss

	var offset := point.distance_to(hand[0] as Vector3)
	var window := catch_window(impact_speed)
	if window <= 0.0 or offset > window:
		return {"catch": false, "grip": 0.0, "hand": "", "offset": offset}
	return {
		"catch": true,
		"grip": clampf(1.0 - offset / maxf(window, 0.001), 0.0, 1.0),
		"hand": limb,
		"offset": offset,
	}


# =============================================================================
# Line dance
# =============================================================================

## Where the keeper shuffles to on the line before the strike, to put the shooter
## off. Returns an x offset in metres, bounded to +/- 0.9.
##
## Three incommensurable sines so the shuffle never repeats visibly, seeded per
## shot, and ramped in from zero so he starts square on his line and only then
## begins to move. A Legende dances wider and faster than a Debutant: it is the
## only thing in this module that is pure theatre, and it works on the player.
static func line_dance(elapsed: float, level: int, rng_seed: int) -> float:
	if not is_finite(elapsed) or elapsed <= 0.0:
		return 0.0
	var lv := _level(level)
	var rng := _rng(rng_seed)
	var p1 := rng.randf() * TAU
	var p2 := rng.randf() * TAU
	var p3 := rng.randf() * TAU
	var rate := float(_DANCE_RATES[lv])
	var wave := 0.58 * sin(elapsed * rate + p1)
	wave += 0.30 * sin(elapsed * rate * 1.71 + p2)
	wave += 0.12 * sin(elapsed * rate * 3.13 + p3)
	var ramp := _smoothstep01(clampf(elapsed / _DANCE_RAMP, 0.0, 1.0))
	var offset := wave * float(_DANCE_AMPS[lv]) * ramp
	if not is_finite(offset):
		return 0.0
	return clampf(offset, -_DANCE_MAX, _DANCE_MAX)


# =============================================================================
# Private helpers
# =============================================================================

static func _level(level: int) -> int:
	return clampi(level, int(Level.DEBUTANT), int(Level.LEGENDE))


static func _smoothstep01(x: float) -> float:
	var u := clampf(x, 0.0, 1.0)
	return u * u * (3.0 - 2.0 * u)


static func _is_finite_vec(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)


## Consecutive integer seeds hand RandomNumberGenerator visibly correlated
## streams, and this module is fed shot indices, so the seed is mixed first.
static func _rng(rng_seed: int) -> RandomNumberGenerator:
	var h := rng_seed
	h = (h ^ 61) ^ (h >> 16)
	h = h + (h << 3)
	h = h ^ (h >> 4)
	h = h * 0x27D4EB2D
	h = h ^ (h >> 15)
	var rng := RandomNumberGenerator.new()
	rng.seed = h
	return rng


static func _cue(cues: Dictionary, key: String, fallback: float, low: float, high: float) -> float:
	if not cues.has(key):
		return fallback
	var raw: Variant = cues[key]
	if not (raw is float or raw is int):
		return fallback
	var value := float(raw)
	if not is_finite(value):
		return fallback
	return clampf(value, low, high)


## Where a committed (side, height) guess is actually aimed, in world space.
static func _guess_point(side: int, height: int) -> Vector3:
	var s := clampi(side, SIDE_LEFT, SIDE_RIGHT)
	var h := clampi(height, HEIGHT_LOW, HEIGHT_HIGH)
	return Vector3(float(s) * _GUESS_X, float(_GUESS_Y[h]), _LINE_PLANE_Z)


## Fallback "I have no idea" point: straight down the middle at chest height.
static func _blind_point() -> Vector3:
	return Vector3(0.0, _GUESS_Y[HEIGHT_MID], _LINE_PLANE_Z)


## The collidable body of a pose, as [name, end a, end b, radius]. A point limb
## has a == b, a segment limb does not.
##
## Every entry is credited to one of the five names the contract allows, so a
## forearm block is reported as the glove that was leading and a shin block as
## the boot that was trailing. The joints come first and keep their own radii, so
## a fingertip save is still a fingertip save and save_distance() still reports
## exactly -GLOVE_RADIUS for a ball going through the middle of a glove.
static func _limbs(pose: Dictionary) -> Array:
	var out: Array = []
	var centre := _pose_point(pose, "centre")
	var glove_l := _pose_point(pose, "glove_left")
	var glove_r := _pose_point(pose, "glove_right")
	var boot_l := _pose_point(pose, "boot_left")
	var boot_r := _pose_point(pose, "boot_right")

	if bool(glove_l[1]):
		out.append(["glove_left", glove_l[0], glove_l[0], GLOVE_RADIUS])
	if bool(glove_r[1]):
		out.append(["glove_right", glove_r[0], glove_r[0], GLOVE_RADIUS])
	if bool(boot_l[1]):
		out.append(["boot_left", boot_l[0], boot_l[0], BOOT_RADIUS])
	if bool(boot_r[1]):
		out.append(["boot_right", boot_r[0], boot_r[0], BOOT_RADIUS])
	if not bool(centre[1]):
		return out

	var body: Vector3 = centre[0]
	out.append(["centre", body, body, BODY_RADIUS])

	# The trunk. It stands on the pelvis along the body's own up axis, which is
	# UP rolled by the reported lean, so an upright keeper blocks with his chest
	# and one laid out flat blocks with the whole length of himself. That single
	# capsule is what makes shooting at the goalkeeper a losing idea.
	var lean := 0.0
	var raw_lean: Variant = pose.get("lean", 0.0)
	if raw_lean is float or raw_lean is int:
		var value := float(raw_lean)
		if is_finite(value):
			lean = clampf(value, -_LEAN_MAX, _LEAN_MAX)
	# Vector3.FORWARD is -Z, and a right handed turn of UP about -Z tips the
	# crown of the head towards +X, which is the sign convention `lean` uses.
	var trunk_axis := Vector3.UP.rotated(Vector3.FORWARD, lean)
	out.append(["centre", body, body + trunk_axis * TRUNK_LENGTH, TRUNK_RADIUS])

	# The limbs between the joints. Only the outer part of each is swept.
	if bool(glove_l[1]):
		out.append(["glove_left", body.lerp(glove_l[0], LIMB_SPAN), glove_l[0], FOREARM_RADIUS])
	if bool(glove_r[1]):
		out.append(["glove_right", body.lerp(glove_r[0], LIMB_SPAN), glove_r[0], FOREARM_RADIUS])
	if bool(boot_l[1]):
		out.append(["boot_left", body.lerp(boot_l[0], LIMB_SPAN), boot_l[0], SHIN_RADIUS])
	if bool(boot_r[1]):
		out.append(["boot_right", body.lerp(boot_r[0], LIMB_SPAN), boot_r[0], SHIN_RADIUS])
	return out


## Reads a finite Vector3 out of a pose. Returns [Vector3, bool valid], because a
## caller handing over a corrupted pose must lose that limb, not the whole test.
static func _pose_point(pose: Dictionary, key: String) -> Array:
	if not pose.has(key):
		return [Vector3.ZERO, false]
	var raw: Variant = pose[key]
	if not (raw is Vector3):
		return [Vector3.ZERO, false]
	var point: Vector3 = raw
	if not _is_finite_vec(point):
		return [Vector3.ZERO, false]
	return [point, true]


## Closest pair of points between two segments, clamped to both. Returns
## [point on the limb, point on the ball path].
##
## This is the standard clamped solve, and the degenerate branches matter here:
## a point limb is a zero length segment and the ball barely moves at all on a
## slow rolling shot, so both segments really do collapse in practice.
static func _closest_between(a0: Vector3, a1: Vector3, b0: Vector3, b1: Vector3) -> Array:
	var d1 := a1 - a0
	var d2 := b1 - b0
	var r := a0 - b0
	var len1 := d1.length_squared()
	var len2 := d2.length_squared()
	var f := d2.dot(r)
	var s := 0.0
	var t := 0.0

	if len1 <= 1e-12 and len2 <= 1e-12:
		return [a0, b0]
	if len1 <= 1e-12:
		t = clampf(f / len2, 0.0, 1.0)
	elif len2 <= 1e-12:
		s = clampf(-d1.dot(r) / len1, 0.0, 1.0)
	else:
		var c := d1.dot(r)
		var b := d1.dot(d2)
		var denom := len1 * len2 - b * b
		if denom > 1e-12:
			s = clampf((b * f - c * len2) / denom, 0.0, 1.0)
		else:
			# Parallel: any s does, so start from the near end and let the clamp
			# below slide it into place.
			s = 0.0
		t = (b * s + f) / len2
		if t < 0.0:
			t = 0.0
			s = clampf(-c / len1, 0.0, 1.0)
		elif t > 1.0:
			t = 1.0
			s = clampf((b - c) / len1, 0.0, 1.0)

	return [a0 + d1 * s, b0 + d2 * t]
