## The bowl around the goal: four raked stands, a crowd, four floodlight pylons,
## perimeter advertising and the corner flags.
##
## Why it is built the way it is:
##
## The stadium is pure decoration wrapped around a very small piece of gameplay,
## so it is only allowed to cost a rounding error. The whole bowl is a few dozen
## draw calls: one merged mesh per stand, one MultiMesh holding every seat in the
## ground, eight holding the spectators, one per advertising artwork, one for the
## flag poles and one for the camera flashes. Nothing here is a per object node,
## because ten thousand seats as ten thousand Node3D would burn more CPU on
## transform propagation than the ball, the keeper and the net put together.
##
## The crowd carries the atmosphere. It is a set of MultiMeshes of camera facing
## quads, each one cropping a different spectator out of the crowd texture:
## positions are drawn from a seeded RandomNumberGenerator so the ground is laid
## out identically on every run, the gain of each spectator comes from
## Palette.vary so the mass is never flat, and the density thins out towards the
## upper rows the way a real stand empties at the back. The idle sway is written
## back into the instance buffer from _process, but only a rolling slice of a few
## hundred instances per frame: each spectator is a continuous function of time
## and phase, so refreshing one in ten frames is invisible while refreshing all
## four thousand every frame would not be.
##
## The floodlights are the single most expensive thing that could happen here, and
## in the daylight match they are SWITCHED OFF. The four pylons keep every piece
## of their geometry, because a mast and a bank of lamps at each corner is most of
## what makes a stadium look like a stadium from inside it, but no SpotLight3D is
## created at all: four spots at midday would be invisible, and two of them would
## be paying for a shadow map nobody can see. The whole shadow budget of the game
## is now the one directional sun owned by SkyController.
##
## The night wiring is kept whole one branch away, because it is good work and the
## night look is still reachable: `Mats.daylight = false` brings back the four
## spots converging between the goal mouth and the penalty spot, with shadows on a
## diagonal pair only so the keeper throws one readable shadow towards the shooter
## and one towards the net. Either way nothing in this file casts a shadow: the
## stands, the seats, the crowd and the pylons are all either outside the light or
## too far to matter.
##
## Engine traps this file works around, on purpose:
##  - a MultiMesh format (use_colors) must be set before instance_count, never
##    after, or the allocation is rejected;
##  - an instance colour multiplies albedo_color, so every material used with
##    instance colours gets its albedo forced to white here, otherwise the tint
##    is applied twice and the crowd goes black;
##  - the exact local convention of Meshes.stand(), Meshes.floodlight_head() and
##    Meshes.limb() belongs to another module, so orientation and anchoring are
##    derived from the returned geometry (AABB, and the y/z covariance of the
##    vertices) instead of being assumed.
class_name Stadium
extends Node3D

# --------------------------------------------------------------- geometry --

## Steps per stand, and the size of one step.
const STAND_ROWS := 20
const ROW_DEPTH := 0.85
const ROW_RISE := 0.45
## Height of the perimeter wall the front row sits on, metres.
const STAND_BASE_Y := 1.15

## Front face of each stand. The built pitch spans x in [-34, 34] and z in
## [-6, 62], so the stands sit a few metres of run off further out.
const SIDE_STAND_X := 37.5
const END_STAND_NEAR_Z := -9.5
const END_STAND_FAR_Z := 65.5
const SIDE_STAND_WIDTH := 82.0
const END_STAND_WIDTH := 84.0
## The built pitch is not symmetric in z, so the side stands are centred on this.
const SIDE_STAND_CENTRE_Z := 28.0

## Spectators. Tex.crowd() is a cut out, so a sprite is the person and not the
## card it is drawn on: the seat pitch is what sets the density now, not the quad
## width, and at the old 0.95 spacing the stands came out visibly half empty.
const CROWD_SPACING := 0.68
const CROWD_QUAD_W := 0.74
const CROWD_QUAD_H := 0.92
const CROWD_MAX := 8600
## Instances whose transform is rewritten each frame. See the module docstring.
const SWAY_SLICE := 384

## Tex.crowd() is a grid of individual spectators, and a spectator sprite has to
## show one of them rather than the whole block, so the material crops a single
## cell out of it. A MultiMesh carries one material, so telling the spectators
## apart means one MultiMesh per cell: twenty-four of them, twenty-four draw
## calls, twenty-four different people instead of four thousand clones.
const CROWD_CELLS_PER_ATLAS := 12
const CROWD_ATLASES := 2
const CROWD_VARIANTS := CROWD_CELLS_PER_ATLAS * CROWD_ATLASES
## Photographic and procedural atlas layouts. Keeping both matters: deleting
## assets/ must restore the old 32 x 22 silhouettes, not crop twelve crowd blocks.
const CROWD_PHOTO_COLUMNS := 4
const CROWD_PHOTO_ROWS := 3
const CROWD_FALLBACK_COLUMNS := 32
const CROWD_FALLBACK_ROWS := 22
## Mid grey the per instance gain is built around, see _crowd_gain().
const CROWD_TINT_GREY := 0.45
## Width of the per instance gain, and the odds and strength of the rare
## spectator who catches a light. See _crowd_gain().
const CROWD_GAIN_SPREAD := 0.40
## Kept low on purpose. Tex.crowd() already picks its own pale shirts, and the two
## draws are independent: a spectator that wins both used to come out as a clipped
## white rectangle, which is the single brightest thing the old stands produced.
const CROWD_GLINT_ODDS := 0.05
const CROWD_GLINT_GAIN := 1.25
## Extra gain applied to every spectator in the DAYLIGHT match.
##
## Mats.crowd() is unshaded, so a spectator's brightness on screen is
## `Tex.crowd()` times the instance gain, and then the tonemap. The daylight
## tonemap runs at a markedly LOWER exposure than the night one (there is an order
## of magnitude more light in the scene), so the very same gain that put the crowd
## a comfortable step under the floodlit turf puts it in a black hole under the
## sun. This factor buys that step back, and no more: the crowd has to stay a dark
## busy mass BEHIND the goal, never a band competing with it.
##
## RAISED, and the measurement that forced it is worth keeping. The daylight pass
## was judged from the goal camera, which looks back down the pitch: there the
## crowd is seventy metres away and it is the sunlit turf, not the stand, that
## fills most of the frame. From the SHOOTING camera, the one the player spends
## the entire game in, the near end stand is twenty nine metres away and it fills
## the whole upper half of the image on its own, and roughly half of that area is
## spectators. Measured on that frame, the upper half came back at 42 of 255 while
## the pitch below it sat at 135: a lit pitch under a dark bowl, which is what a
## floodlit evening match looks like and not an afternoon one.
##
## The spectators are the only part of that bowl NO amount of light can rescue,
## because the material is unshaded on purpose (see Mats.crowd(): a billboard has
## no honest normal, so a lit crowd would brighten and dim as the player cycled
## the cameras). Their value is set here or nowhere. Raising the sky ambient moved
## that upper half by two levels; this moved it by five, which is the proportion
## of it the crowd actually covers.
##
## The ceiling is still the same one: the crowd may not out-read the goal. At this
## gain a spectator lands around 95 of 255 against 135 for the lit turf and 210
## for the goal frame, so the ladder the whole stadium was tuned around is intact.
const CROWD_DAY_GAIN := 2.40
## Generated photographs carry normal photographic exposure, whereas the old
## procedural sprites bake a 0.34 body gain into their pixels.
const CROWD_PHOTO_GAIN := 0.50

## Seats.
const SEAT_SPACING := 0.62
const SEAT_WIDTH := 0.46
const SEAT_HEIGHT := 0.40
const SEAT_MAX := 13000

## Roof. A cantilever slab over the whole rake, reaching out over the front row
## and back past the rear wall, with a fascia hanging off its leading edge. It is
## what caps the bowl: without it the crowd runs straight into the night sky and
## the stand reads as a floating band rather than as a building.
const ROOF_CLEARANCE := 4.2
const ROOF_THICKNESS := 0.55
const ROOF_OVERHANG := 2.6
const ROOF_BACK := 1.2
const FASCIA_HEIGHT := 1.4
const FASCIA_DEPTH := 0.36
## Ribs under the roof, running front to back. Structure, not decoration: they
## are what tells the eye the roof is a roof and not a black band.
const TRUSS_SPACING := 8.5
const TRUSS_WIDTH := 0.26
const TRUSS_DROP := 0.42

## Aisles cutting the seating into blocks, and the tunnel mouths at their foot.
const AISLE_SPACING := 13.5
const AISLE_HALF_WIDTH := 0.72
const TUNNEL_WIDTH := 1.9
const TUNNEL_HEIGHT := 0.92
## The horizontal gangway that splits the lower tier from the upper one. No seats
## and no spectators on this row, plus a handrail along its front edge.
const GANGWAY_ROW := 11

## Dim gantry lights mounted on the fascia, washing the seating below. They are
## the only reason the rake reads at all: the four pylons are aimed at the
## penalty area and reach the stands with about one percent of their energy.
## Shadows are OFF on every one of them, and so is their contribution to the
## volumetric fog, so the whole set costs a clustered light each and nothing more.
##
## COUNT AND SPREAD MATTER MORE THAN ENERGY. Three narrow, powerful spots over an
## eighty metre stand threw three small hot pools with darkness between them, and
## the middle one read as a lit wedge hanging in the frame rather than as house
## lighting. Six wide, weak ones overlap into a continuous wash that falls off
## towards the back of the rake, which is what a real gantry does.
const GANTRY_PER_STAND := 6
const GANTRY_ENERGY := 8.5
const GANTRY_RANGE := 44.0
const GANTRY_ANGLE := 56.0
## Warm, and much weaker than Palette.FLOODLIGHT: house lighting, not floodlight.
const GANTRY_COLOUR := Color(1.0, 0.86, 0.66, 1.0)
## The same fittings in DAYLIGHT are not modelling tungsten any more.
##
## What actually reaches a roofed rake at four in the afternoon is SKYLIGHT
## through the front opening of the stand, plus sunlight bounced off the pitch:
## cool, not warm. Left at the sodium colour and pushed to the energy the daylight
## bowl needs, this set painted a visible orange wash across the seating with a
## blue sky over it, which is a look no stadium has ever had. Faintly blue instead,
## so the rake reads as being lit by the sky it is standing under.
const GANTRY_DAY_COLOUR := Color(0.88, 0.93, 1.0, 1.0)
## What the gantry wash is worth in DAYLIGHT, as a multiple of GANTRY_ENERGY.
##
## THIS IS THE SKY WEDGE GODOT'S AMBIENT CANNOT MODEL, and that is the whole
## reason it is above one rather than well below it.
##
## The argument that put it at 0.32 was that Godot applies its ambient term
## uniformly and without occlusion, so the sky already fills the seating to the
## back wall and the gantry only has to keep a gradient on the steps. The first
## half of that is true and the second half is where it went wrong: an unoccluded
## ambient is not just flat, it is also WEAK, because it is the average of the
## whole dome rather than the bright wedge of sky a stand actually faces. Measured
## from the shooting camera, raising the sky ambient by half moved the near stand
## by two levels of 255 while raising these six lamps moved it by five.
##
## They earn the energy because they are aimed the way the missing light really
## arrives: down and back from the front edge of the roof, falling off towards the
## rear of the rake, which is exactly the gradient an opening in a roof produces.
## Shadows are still off on every one of them, so the cost is unchanged: this is
## the cheapest light in the game and it is doing the most visible work.
const GANTRY_DAY_SCALE := 1.55

## Advertising boards.
const ADVERT_WIDTH := 3.0
const ADVERT_HEIGHT := 0.95
const ADVERT_GAP := 0.16
const ADVERT_VARIANTS := 4

## Floodlights.
const PYLON_X := 42.5
const PYLON_Z_NEAR := -13.5
const PYLON_Z_FAR := 66.5
const PYLON_HEIGHT := 31.0
const HEAD_WIDTH := 6.4
## The four spots converge here: between the goal mouth and the penalty spot, so
## both are lit and the keeper's shadow falls across the six yard box.
const LIGHT_AIM := Vector3(0.0, 0.0, 5.5)

## Camera flashes.
const FLASH_MAX := 96

# ------------------------------------------------------------- verdict ids --
#
# These mirror Shootout.Verdict, whose order is fixed by the contract
# (BUT, ARRET, POTEAU, BARRE, DEHORS). They are copied rather than referenced so
# this file never names an autoload: a file that does cannot be syntax checked
# with --script, which is how every module here is verified.
const _VERDICT_BUT := 0
const _VERDICT_ARRET := 1
const _VERDICT_POTEAU := 2
const _VERDICT_BARRE := 3
const _VERDICT_DEHORS := 4

# ---------------------------------------------------------------- runtime --

var _built := false
var _time := 0.0
var _excitement := 0.25

## Crowd instance data, parallel arrays. A spectator is identified by its index
## in these, and lives in the MultiMesh `_crowd_variant[i]` at slot
## `_crowd_slot[i]`.
var _crowd_base := PackedVector3Array()
var _crowd_right := PackedVector3Array()
var _crowd_phase := PackedFloat32Array()
var _crowd_scale := PackedFloat32Array()
var _crowd_variant := PackedByteArray()
var _crowd_slot := PackedInt32Array()
var _sway_cursor := 0

## One off body language on top of the idle sway.
var _pulse_left := 0.0
var _pulse_total := 1.0
var _pulse_gain := 0.0
var _pulse_dir := 1

var _flashes: Array[Dictionary] = []

var _crowd_nodes: Array[MultiMeshInstance3D] = []
var _flash_mm: MultiMeshInstance3D = null
var _crowd_audio: Node = null
var _crowd_lookup_msec := 0

var _place_rng := RandomNumberGenerator.new()
var _flash_rng := RandomNumberGenerator.new()

# ------------------------------------------------------------------- life --

func _ready() -> void:
	if not _built:
		build()


func _process(delta: float) -> void:
	if not _built:
		return
	_time += delta
	if _pulse_left > 0.0:
		_pulse_left = maxf(_pulse_left - delta, 0.0)
	_update_crowd()
	_update_flashes(delta)


## Builds the whole arena. Idempotent: a second call tears the first one down and
## rebuilds it byte for byte, because every random draw comes from a fixed seed.
func build() -> void:
	_clear()
	_place_rng.seed = 0x60A15EED
	_flash_rng.seed = 0x1A5ED0
	_build_stands()
	_build_adverts()
	_build_floodlights()
	_build_flags()
	_build_barrier()
	_build_flashes()
	_built = true
	set_process(true)


## Crowd excitement in [0, 1]. Drives the sway of the spectators and is handed on
## to the audio side if a Crowd node is reachable. The link is deliberately loose
## (duck typed, looked up lazily, never cached across a free) so the stadium
## still builds and animates in a scene that has no sound at all.
func set_excitement(level: float) -> void:
	_excitement = clampf(level, 0.0, 1.0)
	var audio := _crowd_audio_node()
	if audio != null:
		audio.call("set_tension", _excitement)


## One off crowd reaction to a Shootout.Verdict. Visual only: the audio side owns
## its own reaction so a verdict is never cheered twice.
func react(verdict: int) -> void:
	match verdict:
		_VERDICT_BUT:
			set_excitement(1.0)
			_pulse(1.0, 2.8, 1)
			flash_burst(64)
		_VERDICT_ARRET:
			set_excitement(0.82)
			_pulse(0.85, 1.9, 1)
		_VERDICT_POTEAU, _VERDICT_BARRE:
			# The collective intake of breath: everyone rises then sags back.
			set_excitement(0.62)
			_pulse(0.6, 1.4, -1)
		_VERDICT_DEHORS:
			set_excitement(0.3)
			_pulse(0.45, 1.6, -1)
		_:
			set_excitement(0.35)


## Camera flashes ripple out from a random point of the stands. `count` is capped
## because a flash is an additive sprite and a thousand of them at once is a
## white screen, not a stadium.
func flash_burst(count: int) -> void:
	if _flash_mm == null or _crowd_base.is_empty():
		return
	var wanted := clampi(count, 0, FLASH_MAX)
	if wanted <= 0:
		return
	_flashes.clear()
	var last := _crowd_base.size() - 1
	var epicentre := _crowd_base[_flash_rng.randi_range(0, last)]
	for i in wanted:
		var origin := _crowd_base[_flash_rng.randi_range(0, last)]
		var delay := origin.distance_to(epicentre) * 0.011 + _flash_rng.randf() * 0.06
		_flashes.append({
			"pos": origin + Vector3(0.0, 0.28, 0.0),
			"age": -delay,
			"life": _flash_rng.randf_range(0.10, 0.20),
			"size": _flash_rng.randf_range(0.45, 0.85),
		})


# ------------------------------------------------------------------ stands --

func _build_stands() -> void:
	var stand_mesh := Meshes.stand(SIDE_STAND_WIDTH, STAND_ROWS, ROW_DEPTH, ROW_RISE)
	var end_mesh := Meshes.stand(END_STAND_WIDTH, STAND_ROWS, ROW_DEPTH, ROW_RISE)

	var seat_transforms: Array[Transform3D] = []
	var seat_colours := PackedColorArray()
	# Structural boxes, gathered across all four stands and drawn as three
	# MultiMeshes at the end: concrete slabs, steel members, and the black
	# openings. A unit cube scaled by the instance transform is what lets a roof,
	# a fascia and a handrail share one mesh and one draw call.
	var slabs: Array[Transform3D] = []
	var members: Array[Transform3D] = []
	var voids: Array[Transform3D] = []

	# Order matters only for determinism, not for looks.
	_add_stand(end_mesh, END_STAND_WIDTH,
			Vector3(0.0, STAND_BASE_Y, END_STAND_NEAR_Z), PI,
			seat_transforms, seat_colours, slabs, members, voids)
	_add_stand(end_mesh, END_STAND_WIDTH,
			Vector3(0.0, STAND_BASE_Y, END_STAND_FAR_Z), 0.0,
			seat_transforms, seat_colours, slabs, members, voids)
	_add_stand(stand_mesh, SIDE_STAND_WIDTH,
			Vector3(SIDE_STAND_X, STAND_BASE_Y, SIDE_STAND_CENTRE_Z), PI * 0.5,
			seat_transforms, seat_colours, slabs, members, voids)
	_add_stand(stand_mesh, SIDE_STAND_WIDTH,
			Vector3(-SIDE_STAND_X, STAND_BASE_Y, SIDE_STAND_CENTRE_Z), -PI * 0.5,
			seat_transforms, seat_colours, slabs, members, voids)

	# THE ROOF IS THE ONE THING IN THIS FILE THAT CASTS A SHADOW, and it earns it.
	#
	# Godot applies the ambient term without occlusion, so under a bright sky the
	# seating, the crowd and the concrete are all filled to the same flat level
	# whether they are under a roof or out in the open, and the whole bowl comes
	# back as a pale band brighter than the pitch it surrounds. One shadow caster
	# fixes it at the source: with the slabs in the shadow map the rake sits in the
	# shade of its own roof, exactly as a real stand does, and the sunlit pitch
	# becomes the brightest thing in frame again by simple physics rather than by
	# tuning six numbers against each other.
	#
	# The cost is one MultiMesh of a few dozen boxes added to the shadow pass, and
	# the shadow is cast onto surfaces that are already being drawn. The stand
	# blocks, the seats, the crowd and the pylons still cast nothing.
	_build_box_multimesh("StandSlabs", slabs, Mats.concrete(), Mats.daylight)
	_build_box_multimesh("StandSteel", members, _member_material())
	_build_box_multimesh("StandVoids", voids, _void_material())
	_build_seat_multimesh(seat_transforms, seat_colours)
	_build_crowd_multimesh()


## Places one stand and appends its seats, spectators and structure to the shared
## buffers. `yaw` turns stand space (+Z away from the pitch, +X along the width,
## origin on the front edge at tread level) into world space.
func _add_stand(mesh: ArrayMesh, width: float, origin: Vector3, yaw: float,
		seat_transforms: Array[Transform3D], seat_colours: PackedColorArray,
		slabs: Array[Transform3D], members: Array[Transform3D],
		voids: Array[Transform3D]) -> void:
	if mesh == null:
		push_warning("Stadium: Meshes.stand returned nothing, stand skipped.")
		return

	var stand_basis := Basis(Vector3.UP, yaw)
	var stand_xform := Transform3D(stand_basis, origin)

	# The local convention of the stand mesh belongs to another module, so it is
	# measured instead of assumed: if y grows as z shrinks the block rises
	# towards -Z and has to be turned around.
	var flip := not _rises_towards_positive_z(mesh)
	var fix_basis := Basis(Vector3.UP, PI) if flip else Basis.IDENTITY
	var fixed := _transformed_aabb(mesh.get_aabb(), fix_basis)
	var fix_origin := Vector3(
		-(fixed.position.x + fixed.size.x * 0.5),
		-fixed.position.y,
		-fixed.position.z)

	var block := MeshInstance3D.new()
	block.name = "Stand"
	block.mesh = mesh
	block.transform = stand_xform * Transform3D(fix_basis, fix_origin)
	block.material_override = Mats.concrete()
	block.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	block.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(block)

	# The wall the front row sits on, so the pitch never shows daylight under
	# the seating.
	var wall_mesh := Meshes.box(Vector3(width, STAND_BASE_Y, 0.6), 0.6)
	var wall := MeshInstance3D.new()
	wall.name = "StandWall"
	wall.mesh = wall_mesh
	var wall_centre := Vector3.ZERO
	if wall_mesh != null:
		wall_centre = _centre_offset(wall_mesh.get_aabb())
	wall.transform = Transform3D(stand_basis,
			origin + Vector3(0.0, -STAND_BASE_Y * 0.5, 0.0) + wall_centre)
	wall.material_override = Mats.concrete()
	wall.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	wall.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(wall)

	var profile := _tread_profile(mesh, fix_basis, fix_origin, width)
	var half := width * 0.5 - 0.6
	var aisles := _aisle_positions(half)

	_add_stand_structure(stand_xform, width, half, aisles, slabs, members, voids)
	_add_gantry_lights(stand_xform, width)

	for row in STAND_ROWS:
		var tread := _tread_height(profile, row)
		if row == GANGWAY_ROW:
			# The gangway is a walkway, not a row: no seats, no spectators, and a
			# handrail along its leading edge. It is the single strongest read of
			# scale in the whole bowl, because it draws one continuous horizontal
			# line right across the rake.
			members.append(_box(stand_xform,
					Vector3(0.0, tread + 0.52, (float(row) + 0.08) * ROW_DEPTH),
					Vector3(width - 1.2, 0.09, 0.09)))
			members.append(_box(stand_xform,
					Vector3(0.0, tread + 0.28, (float(row) + 0.08) * ROW_DEPTH),
					Vector3(width - 1.2, 0.06, 0.06)))
			continue
		_add_row_seats(stand_xform, row, tread, half, aisles, seat_transforms, seat_colours)
		_add_row_crowd(stand_xform, row, tread, half, aisles)


## Roof, fascia, ribs, aisle steps, tunnel mouths and the pitch side fence: the
## parts that make the block read as a building rather than as a tilted plane.
func _add_stand_structure(stand_xform: Transform3D, width: float, half: float,
		aisles: PackedFloat32Array, slabs: Array[Transform3D],
		members: Array[Transform3D], voids: Array[Transform3D]) -> void:
	var depth := float(STAND_ROWS) * ROW_DEPTH
	var top := float(STAND_ROWS) * ROW_RISE
	var roof_under := top + ROOF_CLEARANCE
	var roof_span := depth + ROOF_BACK + ROOF_OVERHANG
	var roof_mid := (depth + ROOF_BACK - ROOF_OVERHANG) * 0.5

	# The slab itself, cantilevered out over the front row.
	slabs.append(_box(stand_xform,
			Vector3(0.0, roof_under + ROOF_THICKNESS * 0.5, roof_mid),
			Vector3(width + 0.8, ROOF_THICKNESS, roof_span)))
	# The fascia hanging off its leading edge, which is the band a stadium is
	# recognised by from the pitch.
	slabs.append(_box(stand_xform,
			Vector3(0.0, roof_under - FASCIA_HEIGHT * 0.5, -ROOF_OVERHANG + FASCIA_DEPTH * 0.5),
			Vector3(width + 0.8, FASCIA_HEIGHT, FASCIA_DEPTH)))
	# Ribs under the slab, front to back.
	var ribs := maxi(int(round(width / TRUSS_SPACING)), 2)
	for k in range(ribs + 1):
		var x := -width * 0.5 + width * float(k) / float(ribs)
		members.append(_box(stand_xform,
				Vector3(x, roof_under - TRUSS_DROP * 0.5, roof_mid),
				Vector3(TRUSS_WIDTH, TRUSS_DROP, roof_span - 0.4)))
	# Back wall carried up to the roof, so the top rows are not open to the sky.
	slabs.append(_box(stand_xform,
			Vector3(0.0, (top + roof_under) * 0.5, depth + 0.3),
			Vector3(width, roof_under - top, 0.6)))

	# Aisles: a strip of plain concrete up the rake where the seats were skipped,
	# and a black tunnel mouth punched through the perimeter wall at its foot.
	for a in aisles:
		slabs.append(_box(stand_xform,
				Vector3(a, top * 0.5 - 0.06, depth * 0.5),
				Vector3(AISLE_HALF_WIDTH * 1.9, top + 0.2, depth)))
		voids.append(_box(stand_xform,
				Vector3(a, -STAND_BASE_Y + TUNNEL_HEIGHT * 0.5, -0.34),
				Vector3(TUNNEL_WIDTH, TUNNEL_HEIGHT, 0.22)))

	# Pitch side fence in front of the first row.
	members.append(_box(stand_xform,
			Vector3(0.0, 0.62, -0.16), Vector3(width - 1.2, 0.08, 0.08)))
	for k in range(int(width / 3.0) + 1):
		var px := -half + float(k) * 3.0
		if px > half:
			break
		members.append(_box(stand_xform,
				Vector3(px, 0.31, -0.16), Vector3(0.06, 0.62, 0.06)))


## Local x of every aisle, evenly spaced so the seating comes out in equal blocks.
## The block count is forced ODD, which puts a block of seating on the centre
## line of every stand instead of an aisle: the goal camera looks straight down
## that line, and a gangway splitting the frame in half behind the goal is the
## one place in this stadium where a piece of architecture would fight the ball.
func _aisle_positions(half: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	var blocks := maxi(int(round((half * 2.0) / AISLE_SPACING)), 3)
	if blocks % 2 == 0:
		blocks += 1
	for k in range(1, blocks):
		out.append(-half + (half * 2.0) * float(k) / float(blocks))
	return out


func _in_aisle(x: float, aisles: PackedFloat32Array) -> bool:
	for a in aisles:
		if absf(x - a) < AISLE_HALF_WIDTH:
			return true
	return false


## A world transform for a unit cube of the given local size and centre.
func _box(stand_xform: Transform3D, centre: Vector3, size: Vector3) -> Transform3D:
	return stand_xform * Transform3D(Basis.IDENTITY.scaled(size), centre)


func _add_row_seats(stand_xform: Transform3D, row: int, tread: float, half: float,
		aisles: PackedFloat32Array, seat_transforms: Array[Transform3D],
		seat_colours: PackedColorArray) -> void:
	if seat_transforms.size() >= SEAT_MAX:
		return
	var count := int(floor((half * 2.0) / SEAT_SPACING))
	# Seats sit at the back of their tread. The half turn puts the face of the
	# backrest towards the pitch, and the lean then tips its top edge away from
	# the pitch, which is both what a seat does and what makes the rake read
	# from the high television camera.
	var local_z := (float(row) + 0.74) * ROW_DEPTH
	var lean := Basis(Vector3.UP, PI) * Basis(Vector3.RIGHT, -0.30)
	for i in count:
		if seat_transforms.size() >= SEAT_MAX:
			return
		var x := -half + (float(i) + 0.5) * SEAT_SPACING
		if _in_aisle(x, aisles):
			continue
		var local := Vector3(x, tread + SEAT_HEIGHT * 0.5 + 0.04, local_z)
		seat_transforms.append(stand_xform * Transform3D(lean, local))
		# Blocks of colour, the way a real ground alternates its seating.
		var band := int(floor(float(i) / 9.0)) + int(floor(float(row) / 4.0))
		var base: Color = Palette.SEAT_A if band % 2 == 0 else Palette.SEAT_B
		seat_colours.append(Palette.vary(base, _place_rng.randf(), 0.10))


func _add_row_crowd(stand_xform: Transform3D, row: int, tread: float, half: float,
		aisles: PackedFloat32Array) -> void:
	if _crowd_base.size() >= CROWD_MAX:
		return
	var count := int(floor((half * 2.0) / CROWD_SPACING))
	var t := float(row) / float(maxi(STAND_ROWS - 1, 1))
	# The back of a stand is always emptier than the front.
	var occupancy := lerpf(0.93, 0.34, pow(t, 0.75))
	var local_z := (float(row) + 0.52) * ROW_DEPTH
	var right := stand_xform.basis.x.normalized()
	for i in count:
		if _crowd_base.size() >= CROWD_MAX:
			return
		if _place_rng.randf() > occupancy:
			continue
		var x := -half + (float(i) + 0.5) * CROWD_SPACING + _place_rng.randf_range(-0.09, 0.09)
		if _in_aisle(x, aisles):
			continue
		var local := Vector3(
			x,
			tread + CROWD_QUAD_H * 0.5 - 0.14 + _place_rng.randf_range(-0.03, 0.03),
			local_z + _place_rng.randf_range(-0.05, 0.05))
		_crowd_base.append(stand_xform * local)
		_crowd_right.append(right)
		_crowd_phase.append(_place_rng.randf() * TAU)
		_crowd_scale.append(_place_rng.randf_range(0.90, 1.08))
		_crowd_variant.append(_place_rng.randi_range(0, CROWD_VARIANTS - 1))


## The house lighting of one stand: a few soft spots on the fascia, washing down
## and back across the seating. Shadows off, volumetric contribution off.
func _add_gantry_lights(stand_xform: Transform3D, width: float) -> void:
	var top := float(STAND_ROWS) * ROW_RISE
	var mount_y := top + ROOF_CLEARANCE - FASCIA_HEIGHT * 0.65
	var mount_z := -ROOF_OVERHANG + FASCIA_DEPTH
	var aim_z := float(STAND_ROWS) * ROW_DEPTH * 0.55
	for k in GANTRY_PER_STAND:
		var x := width * (float(k) + 0.5) / float(GANTRY_PER_STAND) - width * 0.5
		var from := Vector3(x, mount_y, mount_z)
		var to := Vector3(x, top * 0.35, aim_z)
		var light := SpotLight3D.new()
		light.name = "Gantry%d" % k
		# looking_at points local -Z down the beam, which is the SpotLight3D
		# convention. Computed rather than look_at() so build() works before the
		# node is in a tree.
		light.transform = stand_xform * Transform3D(Basis.looking_at(to - from, Vector3.UP), from)
		light.light_color = GANTRY_DAY_COLOUR if Mats.daylight else GANTRY_COLOUR
		light.light_energy = GANTRY_ENERGY * (GANTRY_DAY_SCALE if Mats.daylight else 1.0)
		light.light_specular = 0.25
		light.light_bake_mode = Light3D.BAKE_DISABLED
		light.light_volumetric_fog_energy = 0.0
		light.shadow_enabled = false
		light.spot_range = GANTRY_RANGE
		light.spot_attenuation = 1.4
		light.spot_angle = GANTRY_ANGLE
		# A soft cone edge, so two neighbouring gantries cross fade into each
		# other instead of drawing their own outlines on the seating.
		light.spot_angle_attenuation = 0.35
		add_child(light)


## Steelwork of the stands: the roof ribs, the gangway handrail and the pitch
## side fence.
##
## NOT Mats.steel() as it comes: that material is 0.88 metallic, which is right
## for the goal frame standing in a floodlight and completely wrong here. A metal
## with nothing to reflect renders black, so a truly metallic handrail in an
## unlit stand simply is not there. Half the metalness and a rougher finish give
## a painted steel that the gantry lights can actually pick out.
## It also has to UNDO the photographic set `Mats.steel()` now carries when the
## optional assets are present. That set is galvanised sheet: a real metallic map
## at ~1.0 and a roughness map averaging 0.37, both of which MULTIPLY the scalars
## below, so the copy would come back at 0.23 roughness, which is a chrome
## handrail. Every map is therefore cleared before the painted set goes on, and
## that is also the reason this is done here rather than by nudging two numbers:
## a texture inherited from a duplicate is invisible in the code that reads wrong.
func _member_material() -> StandardMaterial3D:
	var mat := _own_copy(Mats.steel())
	mat.albedo_texture = null
	mat.normal_enabled = false
	mat.normal_texture = null
	mat.ao_enabled = false
	mat.ao_texture = null
	mat.roughness_texture = null
	mat.metallic_texture = null
	mat.uv1_triplanar = false
	mat.uv1_world_triplanar = false
	mat.uv1_scale = Vector3.ONE
	mat.metallic = 0.35
	mat.roughness = 0.62
	mat.albedo_color = Palette.shade(Palette.STEEL, 1.9)

	# Painted metal panel, when the optional assets are there. Detail only: the
	# map is a neutral multiplier, so the rails and ribs keep exactly the value
	# they were tuned to and gain the chipping and the panel lines of real painted
	# steel. World triplanar because these are unit cubes scaled into bars.
	var detail := Tex.surface_detail("metal_painted")
	if detail != null:
		mat.albedo_texture = detail
		# The map averages Tex.DETAIL_MEAN, so the painted colour is divided by it.
		# See Tex.DETAIL_MEAN for why the map cannot simply average one.
		var k := 1.0 / maxf(Tex.DETAIL_MEAN, 0.01)
		mat.albedo_color = Color(
			mat.albedo_color.r * k, mat.albedo_color.g * k, mat.albedo_color.b * k, 1.0)
		var normal := Tex.surface_normal("metal_painted")
		if normal != null:
			mat.normal_enabled = true
			mat.normal_texture = normal
			mat.normal_scale = 0.6
		mat.uv1_triplanar = true
		mat.uv1_world_triplanar = true
		# One tile per metre: a handrail is 9 cm across, so anything coarser shows
		# a single flat texel along its whole length.
		mat.uv1_scale = Vector3.ONE
		mat.uv1_triplanar_sharpness = 1.0
	return mat


## Flat near black, for the tunnel mouths. A hole in a wall is not a dark grey
## surface: it is the absence of one, so it is drawn unshaded and it stays put
## whatever the gantry lights do.
##
## The DAYLIGHT value is lifted, and it is still a hole. At night a tunnel mouth
## really is the darkest thing in the ground, but in the afternoon the sky reaches
## a couple of metres inside it and lights the floor and the near wall, so a real
## one photographs as a very dark grey rather than as a cut out. Left at the night
## value, the mouths behind the goal read as hard black rectangles punched into an
## otherwise sunlit wall, which is the one thing an unshaded material can do that
## nothing else in the frame can. Still by far the darkest surface in the daylight
## stadium, and still flat, so it never picks up a gantry highlight.
func _void_material() -> StandardMaterial3D:
	var shade := 0.048 if Mats.daylight else 0.012
	return Mats.flat(Color(shade, shade, shade * 1.25, 1.0))


## One MultiMesh of unit cubes, scaled and placed by their transforms. Shadow
## casting is off unless the caller asks: see the roof, which is the only set of
## boxes in this stadium worth putting in a shadow map.
func _build_box_multimesh(node_name: String, transforms: Array[Transform3D],
		material: StandardMaterial3D, casts_shadow: bool = false) -> void:
	if transforms.is_empty():
		return
	var cube := Meshes.box(Vector3.ONE, 1.0)
	if cube == null:
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = cube
	mm.instance_count = transforms.size()
	for i in transforms.size():
		mm.set_instance_transform(i, transforms[i])
	var node := MultiMeshInstance3D.new()
	node.name = node_name
	node.multimesh = mm
	node.material_override = material
	node.cast_shadow = (GeometryInstance3D.SHADOW_CASTING_SETTING_ON if casts_shadow
			else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(node)


func _build_seat_multimesh(seat_transforms: Array[Transform3D], colours: PackedColorArray) -> void:
	if seat_transforms.is_empty():
		return
	var mat := _own_copy(Mats.seat(Palette.SEAT_A))
	var seat_texture := Tex.stadium_seat()
	# The instance colour multiplies albedo_color, so albedo has to be neutral or
	# the seat tint is applied twice and the whole stand turns to mud.
	#
	# NEUTRAL IS NOT ALWAYS ONE. Should this material ever gain a detail map, that
	# map averages Tex.DETAIL_MEAN rather than 1 and the material it came from
	# carries the matching compensation in its albedo_color: overwriting that with a
	# plain white would silently halve every seat in the ground. So "neutral" is
	# whatever cancels the texture that is actually there. Mats.seat() deliberately
	# binds none today, see the note in that function.
	var neutral := 1.0
	if seat_texture != null:
		mat.albedo_texture = seat_texture
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
		mat.alpha_scissor_threshold = 0.12
		mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	elif mat.albedo_texture != null:
		neutral = 1.0 / maxf(Tex.DETAIL_MEAN, 0.01)
	mat.albedo_color = Color(neutral, neutral, neutral, 1.0)
	mat.vertex_color_use_as_albedo = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED

	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = Meshes.quad(SEAT_WIDTH, SEAT_HEIGHT)
	mm.instance_count = seat_transforms.size()
	var base_luminance := maxf(Palette.SEAT_A.get_luminance(), 0.001)
	for i in seat_transforms.size():
		mm.set_instance_transform(i, seat_transforms[i])
		if seat_texture != null:
			var gain := clampf(colours[i].get_luminance() / base_luminance, 0.78, 1.08)
			mm.set_instance_color(i, Color(gain, gain, gain, 1.0))
		else:
			mm.set_instance_color(i, colours[i])

	var node := MultiMeshInstance3D.new()
	node.name = "Seats"
	node.multimesh = mm
	node.material_override = mat
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(node)


func _build_crowd_multimesh() -> void:
	var total := _crowd_base.size()
	if total == 0:
		return
	var quad := Meshes.quad(CROWD_QUAD_W, CROWD_QUAD_H)
	var flipped := _quad_uv_flipped(quad)

	# One instance list per variant, so each MultiMesh can be allocated at its
	# exact size (the format of a MultiMesh is frozen once it has instances).
	var per_variant := PackedInt32Array()
	per_variant.resize(CROWD_VARIANTS)
	per_variant.fill(0)
	_crowd_slot.resize(total)
	for i in total:
		var variant := int(_crowd_variant[i])
		_crowd_slot[i] = per_variant[variant]
		per_variant[variant] = per_variant[variant] + 1

	_crowd_nodes.resize(CROWD_VARIANTS)
	for variant in CROWD_VARIANTS:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_colors = true
		mm.mesh = quad
		mm.instance_count = per_variant[variant]
		var node := MultiMeshInstance3D.new()
		node.name = "Crowd%d" % variant
		node.multimesh = mm
		node.material_override = _crowd_material(variant, flipped)
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(node)
		_crowd_nodes[variant] = node

	for i in total:
		var mesh: MultiMesh = _crowd_nodes[int(_crowd_variant[i])].multimesh
		var slot := _crowd_slot[i]
		var size := _crowd_scale[i]
		mesh.set_instance_transform(slot,
				Transform3D(Basis.IDENTITY.scaled(Vector3(size, size, size)), _crowd_base[i]))
		mesh.set_instance_color(slot, _crowd_gain(_place_rng.randf()))


## One spectator cell of the crowd texture, cropped out with the UV transform.
func _crowd_material(variant: int, flipped_v: bool) -> StandardMaterial3D:
	var mat := _own_copy(Mats.crowd())
	var photographic := Tex.crowd_uses_asset()
	var atlas_index := variant / CROWD_CELLS_PER_ATLAS
	var cell_variant := variant % CROWD_CELLS_PER_ATLAS
	mat.albedo_texture = Tex.crowd(atlas_index if photographic else 0)
	mat.vertex_color_use_as_albedo = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	# Yaw only billboarding: spectators turn towards the camera but stay
	# upright, which full billboarding stops doing as soon as the television
	# camera looks down at the pitch.
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	mat.billboard_keep_scale = true

	# Cells are picked with two coprime strides so the variants land far apart in
	# the grid rather than next to each other.
	var columns := CROWD_PHOTO_COLUMNS if photographic else CROWD_FALLBACK_COLUMNS
	var rows := CROWD_PHOTO_ROWS if photographic else CROWD_FALLBACK_ROWS
	var stride_u := 1 if photographic else 7
	var stride_v := 1 if photographic else 9
	var column := (cell_variant * stride_u + 3) % columns
	var row := (cell_variant * stride_v + 5) % rows
	var cell_u := 1.0 / float(columns)
	var cell_v := 1.0 / float(rows)
	# Keep filtering inside the transparent gutter without cropping raised hands.
	var inset := 0.02 if photographic else 0.1
	var u0 := (float(column) + inset * 0.5) * cell_u
	var v0 := (float(row) + inset * 0.5) * cell_v
	var span_u := cell_u * (1.0 - inset)
	var span_v := cell_v * (1.0 - inset)
	if flipped_v:
		# The quad's v runs bottom to top, so the crop has to run backwards or
		# every spectator in the ground is upside down.
		mat.uv1_scale = Vector3(span_u, -span_v, 1.0)
		mat.uv1_offset = Vector3(u0, v0 + span_v, 0.0)
	else:
		mat.uv1_scale = Vector3(span_u, span_v, 1.0)
		mat.uv1_offset = Vector3(u0, v0, 0.0)
	return mat


## Per instance modulation of a spectator.
##
## It is a neutral gain, not a colour. The crowd texture is already painted with
## Palette.CROWD_A, CROWD_B and CROWD_C, so multiplying it by one of those again
## would apply the palette twice and turn the stands to mud. Palette.vary around
## a mid grey gives the same deterministic jitter, and dividing by that grey
## brings the average back to 1.0 so the mass keeps its intended brightness.
##
## Since Mats.crowd() is unshaded, this gain IS the spectator's final brightness
## multiplier: there is no light to blow it out and no light to rescue it, which
## is exactly why the crowd can be tuned here with confidence. The distribution
## is deliberately lopsided. Most of the mass sits at or below 1.0, so the stand
## reads dark and low contrast, and a small minority is pushed well over it: the
## occasional spectator catching a light, which is the only sparkle this crowd is
## allowed to have.
##
## The one thing the hour changes is the SIZE of the gain, not its shape. Being
## unshaded, the crowd is the single surface in the game that does not follow the
## exposure on its own, so a daylight tonemap running lower than the night one
## would silently drop the whole stand into a hole. CROWD_DAY_GAIN buys back
## exactly that step and nothing more.
func _crowd_gain(rng_value: float) -> Color:
	var grey := Color(CROWD_TINT_GREY, CROWD_TINT_GREY, CROWD_TINT_GREY, 1.0)
	var varied := Palette.vary(grey, rng_value, CROWD_GAIN_SPREAD)
	var k := 1.0 / CROWD_TINT_GREY
	# Weighted towards the dark half: the mass has to sit behind the goal, not
	# beside it.
	k *= 0.82
	# The daylight tonemap runs at a lower exposure, so an unshaded surface needs
	# a bigger number to land in the same place. See CROWD_DAY_GAIN.
	if Mats.daylight:
		k *= CROWD_DAY_GAIN
	if Tex.crowd_uses_asset():
		k *= CROWD_PHOTO_GAIN
	if _place_rng.randf() < CROWD_GLINT_ODDS:
		k *= CROWD_GLINT_GAIN
	return Color(varied.r * k, varied.g * k, varied.b * k, 1.0)


## True when the quad mesh puts v = 1 at the top instead of at the bottom. The
## UV convention of Meshes.quad belongs to another module, so it is read off the
## geometry rather than assumed.
func _quad_uv_flipped(quad: ArrayMesh) -> bool:
	if quad == null or quad.get_surface_count() == 0:
		return false
	var arrays: Array = quad.surface_get_arrays(0)
	if arrays.is_empty():
		return false
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	if vertices.size() == 0 or uvs.size() != vertices.size():
		return false
	var top := 0
	var bottom := 0
	for i in vertices.size():
		if vertices[i].y > vertices[top].y:
			top = i
		if vertices[i].y < vertices[bottom].y:
			bottom = i
	return uvs[top].y > uvs[bottom].y


# ---------------------------------------------------------------- adverts --

func _build_adverts() -> void:
	# One MultiMesh per artwork, because a MultiMesh carries a single material.
	# Four artworks is four draw calls for the whole perimeter.
	var slots: Array[Array] = []
	for i in ADVERT_VARIANTS:
		var empty: Array[Transform3D] = []
		slots.append(empty)

	var pitch_step := ADVERT_WIDTH + ADVERT_GAP
	# Boards lean back a little, exactly like the real ones, so they catch the
	# floodlights instead of facing the sky edge on.
	var lean := Basis(Vector3.RIGHT, -0.21)
	var half_x := Field.PITCH_HALF_X + 0.9
	var near_z := Field.PITCH_MIN_Z - 0.9
	var far_z := Field.PITCH_MAX_Z + 0.9
	var height := Vector3(0.0, ADVERT_HEIGHT * 0.5 + 0.05, 0.0)

	var index := 0
	# Behind the goal, seen on every single shot: the busiest line.
	index = _fill_advert_line(slots, index,
			Vector3(-Field.PITCH_HALF_X, 0.0, near_z),
			Vector3(Field.PITCH_HALF_X, 0.0, near_z),
			pitch_step, Basis(Vector3.UP, 0.0) * lean, height)
	index = _fill_advert_line(slots, index,
			Vector3(-Field.PITCH_HALF_X, 0.0, far_z),
			Vector3(Field.PITCH_HALF_X, 0.0, far_z),
			pitch_step, Basis(Vector3.UP, PI) * lean, height)
	index = _fill_advert_line(slots, index,
			Vector3(half_x, 0.0, Field.PITCH_MIN_Z),
			Vector3(half_x, 0.0, Field.PITCH_MAX_Z),
			pitch_step, Basis(Vector3.UP, -PI * 0.5) * lean, height)
	index = _fill_advert_line(slots, index,
			Vector3(-half_x, 0.0, Field.PITCH_MIN_Z),
			Vector3(-half_x, 0.0, Field.PITCH_MAX_Z),
			pitch_step, Basis(Vector3.UP, PI * 0.5) * lean, height)

	var board := Meshes.quad(ADVERT_WIDTH, ADVERT_HEIGHT)
	for variant in ADVERT_VARIANTS:
		var transforms: Array = slots[variant]
		if transforms.is_empty():
			continue
		var mat := _own_copy(Mats.advert(variant))
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = board
		mm.instance_count = transforms.size()
		for i in transforms.size():
			mm.set_instance_transform(i, transforms[i])
		var node := MultiMeshInstance3D.new()
		node.name = "Adverts%d" % variant
		node.multimesh = mm
		node.material_override = mat
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(node)


## Lays boards end to end between two points and returns the next artwork index,
## so the artworks keep alternating across the whole perimeter.
func _fill_advert_line(slots: Array[Array], start_index: int, from: Vector3, to: Vector3,
		step: float, facing: Basis, height: Vector3) -> int:
	var span := from.distance_to(to)
	var count := int(floor(span / step))
	if count <= 0:
		return start_index
	var direction := (to - from).normalized()
	var margin := (span - float(count) * step) * 0.5
	var index := start_index
	for i in count:
		var centre := from + direction * (margin + (float(i) + 0.5) * step) + height
		var variant := index % ADVERT_VARIANTS
		var list: Array = slots[variant]
		list.append(Transform3D(facing, centre))
		index += 1
	return index


# ----------------------------------------------------------- floodlights --

func _build_floodlights() -> void:
	var head := Meshes.floodlight_head(6, 3)
	var mast := Meshes.limb(1.05, 0.45, PYLON_HEIGHT)
	var lamp_transforms: Array[Transform3D] = []
	var halo_transforms: Array[Transform3D] = []

	var corners: Array[Vector3] = [
		Vector3(-PYLON_X, 0.0, PYLON_Z_NEAR),
		Vector3(PYLON_X, 0.0, PYLON_Z_NEAR),
		Vector3(PYLON_X, 0.0, PYLON_Z_FAR),
		Vector3(-PYLON_X, 0.0, PYLON_Z_FAR),
	]
	# Shadows on a diagonal pair only. One lights the keeper from behind the
	# goal, so his shadow runs towards the shooter, the other from the far side,
	# so it runs into the six yard box: both cameras get a readable figure, and
	# the shadow budget stays at two spots instead of four.
	var shadow_casters: Array[int] = [0, 2]

	var head_xform := Transform3D.IDENTITY
	var head_depth := 0.5
	if head != null:
		head_xform = _head_transform(head)
		head_depth = maxf(_transformed_aabb(head.get_aabb(), head_xform.basis).size.z, 0.4)

	for i in corners.size():
		var foot: Vector3 = corners[i]
		var pylon := Node3D.new()
		pylon.name = "Pylon%d" % i
		pylon.position = foot
		add_child(pylon)

		if mast != null:
			var column := MeshInstance3D.new()
			column.name = "Mast"
			column.mesh = mast
			column.position = _ground_offset(mast.get_aabb())
			column.material_override = Mats.steel()
			column.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			column.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
			pylon.add_child(column)

		# Basis.looking_at points local -Z along a direction, which is where the
		# truss, the lamp bank and the spot all face. It is computed rather than
		# obtained with look_at() so build() works before the node is in a tree.
		var top := foot + Vector3(0.0, PYLON_HEIGHT, 0.0)
		var head_basis := Basis.looking_at(LIGHT_AIM - top, Vector3.UP)
		var aim := Node3D.new()
		aim.name = "Head"
		aim.transform = Transform3D(head_basis, Vector3(0.0, PYLON_HEIGHT, 0.0))
		pylon.add_child(aim)

		if head != null:
			var truss := MeshInstance3D.new()
			truss.name = "Truss"
			truss.mesh = head
			truss.transform = head_xform
			truss.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			truss.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
			var surfaces := head.get_surface_count()
			for s in surfaces:
				# A single surface head is all truss, so it gets steel and the
				# lamp bank below supplies the glow. A multi surface head is
				# read as truss first, lamp faces after.
				if surfaces > 1 and s > 0:
					truss.set_surface_override_material(s, Mats.lamp())
				else:
					truss.set_surface_override_material(s, Mats.steel())
			aim.add_child(truss)

		# The lamp bank and its halo sit just in front of the truss. Their
		# transforms are expressed in stadium space, since the MultiMesh that
		# draws all four of them is a direct child of this node. The half turn
		# is what turns the face of the bank towards the pitch: the aim basis
		# points its -Z at the goal, while a quad faces its own +Z.
		var pylon_xform := Transform3D(head_basis, top)
		lamp_transforms.append(pylon_xform * Transform3D(
				Basis(Vector3.UP, PI), Vector3(0.0, 0.0, -head_depth * 0.5 - 0.2)))
		# The halo is the haze around a burning lamp. A lamp that is off has none,
		# and an additive sprite against a bright sky is a grey smudge, so in
		# daylight the halo bank is simply never built.
		if not Mats.daylight:
			halo_transforms.append(pylon_xform * Transform3D(
					Basis.IDENTITY, Vector3(0.0, 0.0, -head_depth * 0.5 - 0.6)))

		# In daylight the lamps are dark and no light is created at all: not a spot
		# at energy zero, which would still be clustered, culled and shadowed, but
		# no node. The mast, the truss and the lamp bank above are all that remain.
		if not Mats.daylight:
			var spot := SpotLight3D.new()
			spot.name = "Spot"
			spot.light_color = Palette.FLOODLIGHT
			spot.light_energy = 4.6
			spot.light_specular = 0.6
			spot.light_bake_mode = Light3D.BAKE_DISABLED
			spot.spot_range = 150.0
			spot.spot_attenuation = 0.85
			spot.spot_angle = 26.0
			spot.spot_angle_attenuation = 0.55
			if shadow_casters.has(i):
				spot.shadow_enabled = true
				spot.shadow_bias = 0.05
				spot.shadow_normal_bias = 1.4
				spot.shadow_blur = 1.3
			# The spot inherits the aim node, so it already points at LIGHT_AIM.
			aim.add_child(spot)

	_build_lamp_banks(lamp_transforms, halo_transforms)


func _build_lamp_banks(lamps: Array[Transform3D], halos: Array[Transform3D]) -> void:
	if not lamps.is_empty():
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = Meshes.quad(HEAD_WIDTH * 0.92, HEAD_WIDTH * 0.42)
		mm.instance_count = lamps.size()
		for i in lamps.size():
			mm.set_instance_transform(i, lamps[i])
		var node := MultiMeshInstance3D.new()
		node.name = "LampBanks"
		node.multimesh = mm
		var mat := _own_copy(Mats.lamp())
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		node.material_override = mat
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(node)

	if halos.is_empty():
		return
	var halo_mm := MultiMesh.new()
	halo_mm.transform_format = MultiMesh.TRANSFORM_3D
	halo_mm.mesh = Meshes.quad(11.0, 11.0)
	halo_mm.instance_count = halos.size()
	for i in halos.size():
		halo_mm.set_instance_transform(i, halos[i])
	var halo_node := MultiMeshInstance3D.new()
	halo_node.name = "LampHalos"
	halo_node.multimesh = halo_mm
	var halo_mat := _own_copy(Mats.additive(Palette.FLOODLIGHT))
	if halo_mat.albedo_texture == null:
		halo_mat.albedo_texture = Tex.radial(128)
	halo_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	halo_mat.billboard_keep_scale = true
	halo_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	halo_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	halo_node.material_override = halo_mat
	halo_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	halo_node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(halo_node)


# ----------------------------------------------------------- corner flags --

func _build_flags() -> void:
	# The goal line is z = 0 and the touchlines are x = +/- PITCH_HALF_X, so the
	# only true corner flags are the two on the goal line. The pair further up
	# the pitch are the halfway line flags, a metre outside the touchline, which
	# is exactly where the laws put them.
	var spots: Array[Vector3] = [
		Vector3(-Field.PITCH_HALF_X, 0.0, 0.0),
		Vector3(Field.PITCH_HALF_X, 0.0, 0.0),
		Vector3(-Field.PITCH_HALF_X - 1.0, 0.0, 52.5),
		Vector3(Field.PITCH_HALF_X + 1.0, 0.0, 52.5),
	]
	var pole := Meshes.limb(0.035, 0.028, 1.55)
	if pole != null:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = pole
		mm.instance_count = spots.size()
		var lift := _ground_offset(pole.get_aabb())
		for i in spots.size():
			mm.set_instance_transform(i, Transform3D(Basis.IDENTITY, spots[i] + lift))
		var node := MultiMeshInstance3D.new()
		node.name = "FlagPoles"
		node.multimesh = mm
		node.material_override = Mats.steel()
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
		add_child(node)

	var cloth_mm := MultiMesh.new()
	cloth_mm.transform_format = MultiMesh.TRANSFORM_3D
	cloth_mm.mesh = Meshes.quad(0.42, 0.30)
	cloth_mm.instance_count = spots.size()
	for i in spots.size():
		var post: Vector3 = spots[i]
		# The cloth hangs on the pitch side of the pole.
		var yaw := PI * 0.5 if post.x > 0.0 else -PI * 0.5
		var cloth_basis := Basis(Vector3.UP, yaw)
		var offset := cloth_basis.x * -0.21
		cloth_mm.set_instance_transform(i,
				Transform3D(cloth_basis, post + Vector3(0.0, 1.34, 0.0) + offset))
	var cloth := MultiMeshInstance3D.new()
	cloth.name = "FlagCloth"
	cloth.multimesh = cloth_mm
	var cloth_mat := _own_copy(Mats.jersey(Palette.UI_ACCENT))
	cloth_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	cloth.material_override = cloth_mat
	cloth.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	cloth.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(cloth)


# --------------------------------------------------------------- barrier --

func _build_barrier() -> void:
	# One body, a handful of boxes: the stands and the advertising exist for the
	# rest of the game as a single prop collider, never as one body per board.
	var body := StaticBody3D.new()
	body.name = "Barrier"
	body.collision_layer = Layers.PROP
	body.collision_mask = 0
	add_child(body)

	var wall_height := 3.5
	_add_barrier_box(body, Vector3(END_STAND_WIDTH, wall_height, 0.6),
			Vector3(0.0, wall_height * 0.5, END_STAND_NEAR_Z))
	_add_barrier_box(body, Vector3(END_STAND_WIDTH, wall_height, 0.6),
			Vector3(0.0, wall_height * 0.5, END_STAND_FAR_Z))
	_add_barrier_box(body, Vector3(0.6, wall_height, SIDE_STAND_WIDTH),
			Vector3(SIDE_STAND_X, wall_height * 0.5, SIDE_STAND_CENTRE_Z))
	_add_barrier_box(body, Vector3(0.6, wall_height, SIDE_STAND_WIDTH),
			Vector3(-SIDE_STAND_X, wall_height * 0.5, SIDE_STAND_CENTRE_Z))

	var span_z := Field.PITCH_MAX_Z - Field.PITCH_MIN_Z
	var mid_z := (Field.PITCH_MAX_Z + Field.PITCH_MIN_Z) * 0.5
	var advert_h := ADVERT_HEIGHT + 0.1
	_add_barrier_box(body, Vector3(Field.PITCH_HALF_X * 2.0, advert_h, 0.2),
			Vector3(0.0, advert_h * 0.5, Field.PITCH_MIN_Z - 0.9))
	_add_barrier_box(body, Vector3(Field.PITCH_HALF_X * 2.0, advert_h, 0.2),
			Vector3(0.0, advert_h * 0.5, Field.PITCH_MAX_Z + 0.9))
	_add_barrier_box(body, Vector3(0.2, advert_h, span_z),
			Vector3(Field.PITCH_HALF_X + 0.9, advert_h * 0.5, mid_z))
	_add_barrier_box(body, Vector3(0.2, advert_h, span_z),
			Vector3(-Field.PITCH_HALF_X - 0.9, advert_h * 0.5, mid_z))


func _add_barrier_box(body: StaticBody3D, size: Vector3, centre: Vector3) -> void:
	var shape := BoxShape3D.new()
	shape.size = size
	var owner_node := CollisionShape3D.new()
	owner_node.shape = shape
	owner_node.position = centre
	body.add_child(owner_node)


# ---------------------------------------------------------------- flashes --

func _build_flashes() -> void:
	var mat := _own_copy(Mats.additive(Color(1.0, 0.97, 0.90, 1.0)))
	if mat.albedo_texture == null:
		mat.albedo_texture = Tex.radial(64)
	# The per instance colour carries the decay, so albedo stays neutral.
	mat.albedo_color = Color(1.0, 1.0, 1.0, 1.0)
	mat.vertex_color_use_as_albedo = true
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	mat.billboard_keep_scale = true
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED

	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = Meshes.quad(1.0, 1.0)
	mm.instance_count = FLASH_MAX
	mm.visible_instance_count = 0
	for i in FLASH_MAX:
		mm.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ZERO), Vector3.ZERO))
		mm.set_instance_color(i, Color(0.0, 0.0, 0.0, 0.0))

	_flash_mm = MultiMeshInstance3D.new()
	_flash_mm.name = "Flashes"
	_flash_mm.multimesh = mm
	_flash_mm.material_override = mat
	_flash_mm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_flash_mm.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(_flash_mm)


func _update_flashes(delta: float) -> void:
	if _flash_mm == null:
		return
	var mm := _flash_mm.multimesh
	if mm == null:
		return
	if _flashes.is_empty():
		if mm.visible_instance_count != 0:
			mm.visible_instance_count = 0
		return

	var written := 0
	var index := _flashes.size() - 1
	while index >= 0:
		var flash: Dictionary = _flashes[index]
		var age := float(flash["age"]) + delta
		var life := float(flash["life"])
		if age >= life:
			_flashes.remove_at(index)
			index -= 1
			continue
		flash["age"] = age
		_flashes[index] = flash
		index -= 1
		if age < 0.0 or written >= FLASH_MAX:
			continue
		var fade := 1.0 - age / maxf(life, 0.001)
		var size: float = float(flash["size"]) * (0.55 + 0.45 * fade)
		var where: Vector3 = flash["pos"]
		mm.set_instance_transform(written,
				Transform3D(Basis.IDENTITY.scaled(Vector3(size, size, size)), where))
		mm.set_instance_color(written, Color(1.0, 0.97, 0.90, fade * fade))
		written += 1
	mm.visible_instance_count = written


# ------------------------------------------------------------------ crowd --

func _update_crowd() -> void:
	var count := _crowd_base.size()
	if count == 0 or _crowd_nodes.is_empty():
		return

	var amp_v := lerpf(0.010, 0.075, _excitement)
	var amp_h := lerpf(0.008, 0.055, _excitement)
	var freq := lerpf(1.1, 2.9, _excitement)
	var envelope := 0.0
	if _pulse_left > 0.0:
		envelope = pow(_pulse_left / maxf(_pulse_total, 0.001), 0.7) * _pulse_gain

	var slice := mini(SWAY_SLICE, count)
	for k in slice:
		var i := (_sway_cursor + k) % count
		var phase := _crowd_phase[i]
		var bob := sin(_time * freq + phase) * amp_v
		var lateral := sin(_time * freq * 0.53 + phase * 1.7) * amp_h
		if envelope > 0.0:
			if _pulse_dir > 0:
				# Everyone on their feet: the bob only ever goes up.
				bob += absf(sin(_time * 7.5 + phase)) * 0.30 * envelope
				lateral += sin(_time * 4.1 + phase * 2.3) * 0.10 * envelope
			else:
				# Heads in hands: the whole stand sags for a moment.
				bob -= (0.12 + 0.05 * sin(_time * 2.0 + phase)) * envelope
		var origin := _crowd_base[i] + _crowd_right[i] * lateral + Vector3(0.0, bob, 0.0)
		var size := _crowd_scale[i]
		var mesh: MultiMesh = _crowd_nodes[int(_crowd_variant[i])].multimesh
		mesh.set_instance_transform(_crowd_slot[i],
				Transform3D(Basis.IDENTITY.scaled(Vector3(size, size, size)), origin))
	_sway_cursor = (_sway_cursor + slice) % count


func _pulse(gain: float, seconds: float, direction: int) -> void:
	_pulse_gain = clampf(gain, 0.0, 1.0)
	_pulse_total = maxf(seconds, 0.05)
	_pulse_left = _pulse_total
	_pulse_dir = direction


## Lazily finds the audio side without depending on its class, and without
## rescanning the tree every frame when it simply is not there.
func _crowd_audio_node() -> Node:
	if is_instance_valid(_crowd_audio):
		return _crowd_audio
	_crowd_audio = null
	if not is_inside_tree():
		return null
	var now := Time.get_ticks_msec()
	if now < _crowd_lookup_msec:
		return null
	_crowd_lookup_msec = now + 1000

	var tree := get_tree()
	if tree == null:
		return null
	var root: Node = tree.current_scene
	if root == null:
		root = tree.get_root()
	if root == null:
		return null

	var queue: Array[Node] = [root]
	var visited := 0
	while not queue.is_empty() and visited < 600:
		var node: Node = queue.pop_front()
		visited += 1
		if node != self and node.has_method("set_tension") and node.has_method("hush"):
			_crowd_audio = node
			return node
		for child in node.get_children():
			queue.append(child)
	return null


# ---------------------------------------------------------------- helpers --

func _clear() -> void:
	set_process(false)
	_built = false
	_crowd_nodes.clear()
	_flash_mm = null
	_crowd_base = PackedVector3Array()
	_crowd_right = PackedVector3Array()
	_crowd_phase = PackedFloat32Array()
	_crowd_scale = PackedFloat32Array()
	_crowd_variant = PackedByteArray()
	_crowd_slot = PackedInt32Array()
	_flashes.clear()
	_sway_cursor = 0
	_pulse_left = 0.0
	for child in get_children():
		remove_child(child)
		child.queue_free()


## A copy of a cached material, so tweaking it here never corrupts the shared
## instance every other module is drawing with.
func _own_copy(source: StandardMaterial3D) -> StandardMaterial3D:
	if source == null:
		push_warning("Stadium: missing source material, falling back to a plain one.")
		return StandardMaterial3D.new()
	var copy := source.duplicate() as StandardMaterial3D
	if copy == null:
		return StandardMaterial3D.new()
	return copy


## True when the block gets taller as z grows, measured from the geometry rather
## than assumed, so the stand mesh convention can be either way round.
func _rises_towards_positive_z(mesh: ArrayMesh) -> bool:
	if mesh.get_surface_count() == 0:
		return true
	var arrays: Array = mesh.surface_get_arrays(0)
	if arrays.is_empty():
		return true
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var count := vertices.size()
	if count < 3:
		return true
	var mean_y := 0.0
	var mean_z := 0.0
	for v: Vector3 in vertices:
		mean_y += v.y
		mean_z += v.z
	mean_y /= float(count)
	mean_z /= float(count)
	var covariance := 0.0
	for v: Vector3 in vertices:
		covariance += (v.y - mean_y) * (v.z - mean_z)
	return covariance >= 0.0


## Height of the highest surface found up to each depth of the stand, in stand
## space, so seats and spectators are anchored on the real treads rather than on
## a guessed step height.
##
## It is a running maximum on purpose. A stepped block only carries vertices on
## the edges of its steps, so asking for the highest vertex near the middle of a
## tread finds nothing at all; asking for the highest vertex anywhere before that
## point finds the tread itself. Vertices close to the two ends of the block are
## ignored, so a side wall cannot pass itself off as the floor.
func _tread_profile(mesh: ArrayMesh, fix_basis: Basis, fix_origin: Vector3,
		width: float) -> PackedFloat32Array:
	var bins := PackedFloat32Array()
	bins.resize(STAND_ROWS * 4 + 8)
	bins.fill(-1.0e9)
	if mesh.get_surface_count() == 0:
		return bins
	var arrays: Array = mesh.surface_get_arrays(0)
	if arrays.is_empty():
		return bins
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var bin_depth := ROW_DEPTH * 0.25
	var inner := maxf(width * 0.5 - 1.0, 0.5)
	for v: Vector3 in vertices:
		var p := fix_basis * v + fix_origin
		if absf(p.x) > inner:
			continue
		var index := int(floor(p.z / bin_depth))
		if index < 0 or index >= bins.size():
			continue
		if p.y > bins[index]:
			bins[index] = p.y
	for i in range(1, bins.size()):
		if bins[i - 1] > bins[i]:
			bins[i] = bins[i - 1]
	return bins


func _tread_height(profile: PackedFloat32Array, row: int) -> float:
	var ceiling := float(STAND_ROWS + 1) * ROW_RISE
	# Just short of the back of the tread: past the riser that leads onto it,
	# short of the riser that leads off it.
	var bin_depth := ROW_DEPTH * 0.25
	var index := int(floor(((float(row) + 0.82) * ROW_DEPTH) / bin_depth))
	if index >= 0 and index < profile.size() and profile[index] > -1.0e8:
		return clampf(profile[index], 0.0, ceiling)
	return clampf(float(row + 1) * ROW_RISE, 0.0, ceiling)


func _transformed_aabb(box: AABB, rotation_basis: Basis) -> AABB:
	var out := AABB(rotation_basis * box.position, Vector3.ZERO)
	for i in 8:
		out = out.expand(rotation_basis * box.get_endpoint(i))
	return out


## Offset that brings the middle of a mesh onto its own origin, for the builders
## whose anchoring convention this module does not own.
func _centre_offset(box: AABB) -> Vector3:
	return -(box.position + box.size * 0.5)


## Offset that drops a mesh onto y = 0 and centres it horizontally.
func _ground_offset(box: AABB) -> Vector3:
	return Vector3(
		-(box.position.x + box.size.x * 0.5),
		-box.position.y,
		-(box.position.z + box.size.z * 0.5))


## Places and scales a floodlight head whatever its authored size or plane: the
## widest axis becomes the width, and a head authored flat in XZ is stood up.
func _head_transform(head: ArrayMesh) -> Transform3D:
	var box := head.get_aabb()
	var head_basis := Basis.IDENTITY
	if box.size.y < box.size.z and box.size.y < box.size.x:
		head_basis = Basis(Vector3.RIGHT, -PI * 0.5)
	var oriented := _transformed_aabb(box, head_basis)
	var widest := maxf(oriented.size.x, 0.001)
	var factor := HEAD_WIDTH / widest
	head_basis = head_basis.scaled(Vector3(factor, factor, factor))
	var centred := _transformed_aabb(box, head_basis)
	var offset := -(centred.position + centred.size * 0.5)
	return Transform3D(head_basis, offset)
