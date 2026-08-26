class_name GoalFrame
extends Node3D
## Posts, crossbar, back frame, and above all the simulated net.
##
## WHY A REAL CLOTH AND NOT A BILLBOARD
## The net is one of the three things the contract says carry the whole game
## (section 4). A goal is over in a tenth of a second; what the player actually
## remembers is the wave that leaves the impact point and races across the mesh.
## A pre-baked animation cannot do that, because the wave has to start wherever
## the ball happened to arrive, at whatever speed it arrived with.
##
## THE MODEL
## Four panels of mass points: back 48 x 20, roof 48 x 12, and two sides 12 x 20,
## exactly the grids the contract fixes. Every node carries three spring families:
##
##   structural  the four grid neighbours. They set the cord length.
##   shear       the four diagonals. Without them the grid has no resistance to
##               in-plane skew at all and folds up like a paper bag.
##   bend        the two-step neighbours. They resist folding across a cord line.
##               Without them the surface creases into hard zig-zags and reads as
##               jelly rather than as a net under tension.
##
## Integration is Verlet (position, previous position, no stored velocity) and the
## springs are solved as position based distance constraints with a small
## relaxation count. That combination is chosen deliberately over an explicit
## force based spring solver: an explicit spring stiff enough to look like a taut
## cord needs a timestep far below the physics tick to stay stable, and it
## explodes spectacularly the first time a 34 m/s shot arrives. Position based
## constraints cannot add energy, so raising the "stiffness" here costs realism at
## worst, never stability. The relaxation count is the knob, not the stiffness.
##
## Three further safety nets, in order of how often they matter:
##   1. Node velocity is clamped, so a single pathological step cannot fling a
##      node across the pitch.
##   2. Nodes cannot go below the turf.
##   3. Pinned nodes are never written to, so the boundary is exact by
##      construction rather than by convergence.
##
## PRE-TENSION, GRAVITY AND WHY THE PANEL COMES BACK TAUT
## The rest length of every structural and shear spring is slightly shorter than
## the grid spacing: a real net is stretched onto its frame, and that pre-tension
## is what keeps it from bagging under its own weight.
##
## Pre-tension alone is not enough here, and the reason is worth writing down.
## A position based solver run for a small fixed number of passes is compliant:
## each substep it removes only a fraction of the error, so gravity and the
## constraints reach a truce at a sag that depends on the pass count rather than
## on the physics. Measured on this grid, two passes and the real 9.81 leave a
## permanent 16 cm bag. That is fatal, not because it looks wrong (real nets do
## hang), but because net_bulge() is the game's proof that a goal was scored and
## a permanent bag would drown the signal.
##
## So two corrections, both defensible as physics rather than as fudges. The node
## gravity is reduced: a cord panel is mostly air, and most of its weight is
## already carried by the tension in the cords running to the frame. And RECOVERY
## adds the elastic restoring field of a pre-tensioned membrane that the low pass
## count cannot resolve on its own. Together the resting sag is under three
## centimetres, against a bulge of half a metre on a well struck shot.
##
## COST, MEASURED
## The four panels come to 2212 mass points and 11512 springs. Solving all of them
## twice per substep is several milliseconds, which is far too much to pay sixty
## times a second for something that is motionless almost all of the time. Three
## things keep the bill down, in order of how much they save:
##
##   Panels sleep. A panel whose fastest node has stayed under SLEEP_SPEED for
##   SLEEP_STEPS consecutive substeps stops being integrated and stops rebuilding
##   its mesh, and only wakes when net_impulse() actually reaches it. Between
##   shots the whole net costs nothing at all.
##
##   The substep is 60 Hz while the game runs at 120, so a physics tick pays for
##   half a net step on average, and the mesh is rebuilt once per step_net() call
##   rather than once per substep.
##
##   The second relaxation pass only runs while the panel is genuinely moving.
##
## Measured on a woken back panel plus roof, which is what a goal into the middle
## of the net produces: about 3.0 ms per substep and 3.9 ms per rendered frame,
## for the second or two the ripple lasts. That is the price of the thing the
## contract calls the reward for scoring, and it is paid during the verdict phase
## when nothing else in the scene is doing any work.

const SUBSTEP := 1.0 / 60.0
## Guard against a spiral of death after a frame hitch: never catch up more than
## this many substeps in one call.
const MAX_SUBSTEPS := 3
## The relaxation knob. Two passes on a pre-tensioned grid already look taut, and
## in position based dynamics this is the knob to turn, never the stiffness.
const RELAX_ITERATIONS := 2
## Node speed above which the panel gets the full pass count, m/s. The second pass
## buys crispness while the wave is crossing the panel, which is the only moment
## anyone is looking at it; during the long quiet settle afterwards it is pure
## cost. Measured, the full solve of a woken back panel and roof is about 3.7 ms
## and the single pass version about 2.1 ms, so this roughly halves the tail.
const RIPPLE_SPEED := 0.35

## Effective gravity on a net node. See the class comment on why it is not 9.81.
const NET_GRAVITY := 1.6
## Verlet velocity retention per substep. 0.982 ^ 60 is about 0.34, so a ripple
## has lost two thirds of its speed after one second: visible, then gone.
const DAMPING := 0.982
## Rest length as a fraction of the grid spacing. This is the cord pre-tension.
const PRETENSION := 0.985
## Fraction of the remaining offset from the rest shape that the cord tension
## takes back every substep. A pre-tensioned membrane pulls itself flat again,
## and a handful of relaxation passes is nowhere near enough to reproduce that on
## its own: without this term the panel keeps a permanent 16 cm bag under its own
## weight, and net_bulge() could never tell a goal from a sagging net. Being a
## position pull towards the rest shape rather than a force, it is a strictly
## dissipative first order return: it can only ever remove displacement, so it is
## also a third line of defence against a blow up.
const RECOVERY := 0.015

const STIFF_STRUCT := 1.0
const STIFF_SHEAR := 0.55
const STIFF_BEND := 0.22

## Hard ceiling on node speed, m/s. A node moving faster than this is not a net
## any more, it is a projectile.
const MAX_NODE_SPEED := 12.0
const SLEEP_SPEED := 0.035
const SLEEP_STEPS := 24

## Reference strike speed, the top of ShotModel's range. Impulses are scaled
## against it so the fastest legal shot is the loudest the net ever gets.
const REF_SHOT_SPEED := 34.0
## Node speed handed to the impact centre, per m/s of ball speed.
const IMPULSE_GAIN := 0.20
## Instant displacement per m/s of ball speed, so the very first rendered frame
## after contact already shows a dent instead of a flat panel.
const IMPULSE_SET := 0.006
const IMPULSE_SET_MAX := 0.09
## Gaussian width of the affected neighbourhood, metres. A harder shot spreads
## the load over more cord, exactly as a real impact does. The ceiling is the
## width the fastest legal shot produces, so nothing beyond the game's own range
## can widen it further.
const IMPULSE_SIGMA_BASE := 0.30
const IMPULSE_SIGMA_GAIN := 0.013
const IMPULSE_SIGMA_MAX := IMPULSE_SIGMA_BASE + IMPULSE_SIGMA_GAIN * REF_SHOT_SPEED

## Metres of net per repeat of the cord texture.
##
## `Tex.net()` draws eight mesh cells per repeat, so this is also the mesh size of
## the cloth: 0.90 m gives an 11 cm square, which is what a real goal net is
## knotted at. It used to be 0.55, a 7 cm mesh, and that was the second half of the
## net's aliasing problem.
##
## The arithmetic is worth writing down because it is what decides the number. The
## shooting camera puts the 7.32 m mouth across about 640 pixels, so a metre of net
## is 88 pixels and a 7 cm cell was FOUR of them. Two families of cords crossing
## at forty five degrees inside four pixels cannot be resolved at all: what came
## out was not cord, it was the beat between the cord spacing and the pixel grid,
## an axis aligned lattice of bright specks that crawled whenever anything moved.
## At 11 cm the cell is six and a half pixels, half again as much room, and the
## diagonals read as diagonals instead of interfering.
##
## Coarser is also cheaper in the only way that matters here: it is the same
## geometry and the same 256 texture, just sampled at a lower frequency, so the
## mip chain is asked for a shallower level and the cord survives further away.
## The Verlet grid is untouched (the cloth is still 48 x 20, see BACK_COLS) since
## this only changes what is painted on it.
const UV_METRES := 0.90

## Panel identifiers, used by the impulse to report what it woke.
const PANEL_BACK := 0
const PANEL_ROOF := 1
const PANEL_SIDE_LEFT := 2
const PANEL_SIDE_RIGHT := 3

const BACK_COLS := 48
const BACK_ROWS := 20
const ROOF_COLS := 48
const ROOF_ROWS := 12
const SIDE_COLS := 12
const SIDE_ROWS := 20

## Clearance between the net surface and the metal, so the cloth never z-fights
## the frame it hangs from.
const FRAME_CLEARANCE := 0.02

const POST_HALF_X := Field.GOAL_HALF + Field.POST_RADIUS
const BAR_CENTRE_Y := Field.GOAL_HEIGHT + Field.POST_RADIUS
const NET_HALF_X := Field.GOAL_HALF - FRAME_CLEARANCE
const NET_Z_FRONT := -FRAME_CLEARANCE
const NET_Z_BACK := -(Field.NET_DEPTH - FRAME_CLEARANCE)
const ROOF_Y_FRONT := Field.GOAL_HEIGHT
const ROOF_Y_BACK := Field.NET_BACK_TOP

## Radius of the secondary back frame tubes. Thinner than the posts: on a real
## goal the back supports are a lighter section than the uprights.
const BACK_TUBE_RADIUS := 0.042


## One rectangular sheet of cloth. Panels never share nodes: every panel edge is
## pinned to a frame member anyway, so a shared node would be pinned on both
## sides and could not transmit anything. Keeping the ranges disjoint is what
## makes per panel sleeping possible.
class NetPanel extends RefCounted:
	var id: int = 0
	var cols: int = 0
	var rows: int = 0
	## Half open node range into the owner's flat arrays.
	var node_from: int = 0
	var node_to: int = 0
	## Half open constraint range.
	var con_from: int = 0
	var con_to: int = 0
	## The constraint range split into batches that share a stiffness and a pin
	## pattern. Inside a batch both correction weights are loop constants and no
	## constraint needs a branch, which is worth about a factor of two on the
	## hottest loop in the game. See _add_panel_springs.
	var batch_from: PackedInt32Array = PackedInt32Array()
	var batch_to: PackedInt32Array = PackedInt32Array()
	var batch_wa: PackedFloat32Array = PackedFloat32Array()
	var batch_wb: PackedFloat32Array = PackedFloat32Array()
	## Outward direction of the visible side, pointing into the goal mouth.
	var facing: Vector3 = Vector3.FORWARD
	## How much the shading normal leans towards the sky. The cords are round, so
	## on a vertical panel the lit part of every cord faces the floodlights rather
	## than the sheet normal. Zero on the roof, which is already seen from below.
	var up_bias: float = 0.0
	var uv: PackedVector2Array = PackedVector2Array()
	var tris: PackedInt32Array = PackedInt32Array()
	## Tangents, computed once from the rest shape. A rippling net barely rotates
	## its tangent frame in UV space, and the cord material carries no normal map
	## anyway, so recomputing them sixty times a second would buy nothing. They are
	## still written into the surface: a mesh with UVs and no tangents is a trap
	## for whoever adds a normal map later.
	var tans: PackedFloat32Array = PackedFloat32Array()
	var mesh: ArrayMesh = null
	var instance: MeshInstance3D = null
	var awake: bool = false
	var still_steps: int = 0
	## Set by a substep, cleared by the rebuild. The surface is regenerated once
	## per step_net() call, never once per substep: at 120 Hz that would rebuild
	## the same geometry twice for a single rendered frame, and the rebuild is the
	## single most expensive thing this module does.
	var dirty: bool = false

	func node_count() -> int:
		return node_to - node_from

	## Flat index of a grid coordinate, in the owner's node arrays.
	func at(i: int, j: int) -> int:
		return node_from + j * (cols + 1) + i


var _built: bool = false

# Flat node state. One entry per mass point, all panels concatenated.
var _pos: PackedVector3Array = PackedVector3Array()
var _prev: PackedVector3Array = PackedVector3Array()
var _rest: PackedVector3Array = PackedVector3Array()
var _pinned: PackedByteArray = PackedByteArray()

# Flat constraint state, one entry per spring, sorted into the batches described
# on NetPanel. Constraints with both ends pinned are dropped at build time: they
# can never do anything and they are pure cost. The correction weights are not
# stored here at all, they are constants of the batch.
var _con_a: PackedInt32Array = PackedInt32Array()
var _con_b: PackedInt32Array = PackedInt32Array()
var _con_rest: PackedFloat32Array = PackedFloat32Array()

var _panels: Array = []
var _frame_root: Node3D = null
var _net_root: Node3D = null
var _accumulator: float = 0.0
## Cached painted metal of the back stanchions. See _back_frame_material().
var _back_frame_mat: StandardMaterial3D = null


func _ready() -> void:
	set_physics_process(true)


func _physics_process(delta: float) -> void:
	if not _built:
		return
	step_net(delta)


## Builds posts, bar, net grids and the frame colliders. Idempotent.
func build() -> void:
	_discard()

	_frame_root = Node3D.new()
	_frame_root.name = "Frame"
	add_child(_frame_root)

	_net_root = Node3D.new()
	_net_root.name = "Net"
	add_child(_net_root)

	_build_frame()
	_build_net_grids()
	_build_colliders()

	_built = true
	settle_net()


## Pushes the net at a world point, as if hit by a ball carrying `velocity`.
func net_impulse(point: Vector3, velocity: Vector3) -> void:
	if not _built:
		return
	var speed := velocity.length()
	if speed < 0.05:
		return

	# Everything below works in the node's own space, because that is where the
	# mass points live. The goal is normally at the origin unrotated, but there is
	# no reason to bake that assumption in. global_transform is only legal inside
	# the tree, and a test harness is entitled to drive a detached GoalFrame.
	var world := global_transform if is_inside_tree() else transform
	var inv := world.affine_inverse()
	var centre := inv * point
	var push := (inv.basis * (velocity / speed)).normalized()

	var sigma := minf(IMPULSE_SIGMA_BASE + IMPULSE_SIGMA_GAIN * speed, IMPULSE_SIGMA_MAX)
	var two_sigma_sq := 2.0 * sigma * sigma
	var reach := sigma * 3.0
	var reach_sq := reach * reach

	# A harder shot both moves the cord faster and dents it further on contact.
	var peak_speed := clampf(speed * IMPULSE_GAIN, 0.35, MAX_NODE_SPEED)
	var peak_set := minf(speed * IMPULSE_SET, IMPULSE_SET_MAX)

	var touched := 0
	for panel_variant in _panels:
		var panel: NetPanel = panel_variant
		var panel_touched := false
		for i in range(panel.node_from, panel.node_to):
			if _pinned[i] != 0:
				continue
			var here := _pos[i]
			var d_sq := here.distance_squared_to(centre)
			if d_sq > reach_sq:
				continue
			var weight := exp(-d_sq / two_sigma_sq)
			if weight < 0.004:
				continue
			# Velocity in Verlet lives in the gap between the current and the
			# previous position, so an impulse is written by moving the PREVIOUS
			# point back. The momentum the node already carried is preserved, which
			# is what lets a ball rattling around inside the net keep adding energy
			# instead of resetting the cloth on every contact.
			var carried := here - _prev[i]
			var moved := here + push * (peak_set * weight)
			_pos[i] = moved
			_prev[i] = moved - carried - push * (peak_speed * weight * SUBSTEP)
			panel_touched = true
			touched += 1
		if panel_touched:
			panel.awake = true
			panel.still_steps = 0

	if touched == 0:
		# Not a failure worth shouting about, but a shot that produced no net
		# motion at all usually means the impact point was reported in the wrong
		# space, and that is worth seeing in the log.
		push_warning("GoalFrame.net_impulse: aucun noeud de filet a portee de %s" % str(point))


## Steps the Verlet net. Called from _physics_process, exposed for the tests.
func step_net(delta: float) -> void:
	if not _built or delta <= 0.0:
		return
	_accumulator += delta
	var budget := MAX_SUBSTEPS
	while _accumulator >= SUBSTEP and budget > 0:
		_accumulator -= SUBSTEP
		budget -= 1
		_substep()
	if budget <= 0 and _accumulator > SUBSTEP:
		# The frame was so long that catching up is pointless. Drop the backlog
		# rather than spending the next second paying it off in slow motion.
		_accumulator = 0.0
	for panel_variant in _panels:
		var panel: NetPanel = panel_variant
		if panel.dirty:
			panel.dirty = false
			_rebuild_panel_mesh(panel)


## Deepest current displacement of the net, metres. The tests use it to prove the
## net actually moves, and the smoke probe uses it to prove a goal was scored.
func net_bulge() -> float:
	if not _built:
		return 0.0
	var worst := 0.0
	var count := _pos.size()
	for i in count:
		var d := _pos[i].distance_squared_to(_rest[i])
		if d > worst:
			worst = d
	return sqrt(worst)


## Resets the net to rest instantly.
func settle_net() -> void:
	if not _built:
		return
	var count := _pos.size()
	for i in count:
		var r := _rest[i]
		_pos[i] = r
		_prev[i] = r
	_accumulator = 0.0
	for panel_variant in _panels:
		var panel: NetPanel = panel_variant
		panel.awake = false
		panel.still_steps = 0
		panel.dirty = false
		_rebuild_panel_mesh(panel)


# --- simulation -------------------------------------------------------------


## One fixed size step of the whole net.
##
## Integration and constraint relaxation are written out here in one method
## rather than split into readable helpers. That is deliberate. The relaxation
## loop is the hottest code in the game, and the shape it is written in was
## chosen by measurement, not by taste: batching the constraints so the stiffness
## and both correction weights become loop constants, and specialising the loop
## on which end is free, took a woken back panel plus roof from 5.1 ms per
## substep to 3.0 ms. Splitting it back into a tidy helper per family would put
## the branches and the per constraint weight lookups straight back.
##
## The flat arrays are pulled into locals for the same reason. The copy-on-write
## clone of the two arrays this method writes happens once per substep and costs
## a few microseconds.
func _substep() -> void:
	var gravity_step := Vector3(0.0, -NET_GRAVITY * SUBSTEP * SUBSTEP, 0.0)
	var max_move := MAX_NODE_SPEED * SUBSTEP
	var max_move_sq := max_move * max_move
	var sleep_move_sq := SLEEP_SPEED * SUBSTEP * (SLEEP_SPEED * SUBSTEP)
	var ripple_move_sq := RIPPLE_SPEED * SUBSTEP * (RIPPLE_SPEED * SUBSTEP)

	var pos := _pos
	var prev := _prev
	var rest := _rest
	var pinned := _pinned
	var con_a := _con_a
	var con_b := _con_b
	var con_rest := _con_rest
	var touched_anything := false

	for panel_variant in _panels:
		var panel: NetPanel = panel_variant
		if not panel.awake:
			continue
		touched_anything = true

		# 1. Verlet integration, with the three safety clamps: bounded node speed,
		#    no going under the turf, and the dissipative pull back to the rest
		#    shape.
		var node_from := panel.node_from
		var node_to := panel.node_to
		var fastest_sq := 0.0
		for i in range(node_from, node_to):
			if pinned[i] != 0:
				continue
			var here := pos[i]
			var step := (here - prev[i]) * DAMPING
			var step_sq := step.length_squared()
			if step_sq > max_move_sq:
				step = step * (max_move / sqrt(step_sq))
				step_sq = max_move_sq
			if step_sq > fastest_sq:
				fastest_sq = step_sq
			var next := here + step + gravity_step + (rest[i] - here) * RECOVERY
			if next.y < 0.0:
				next.y = 0.0
			prev[i] = here
			pos[i] = next

		# 2. Position based distance constraints, solved Gauss-Seidel: each
		# constraint reads the corrections the earlier ones in the same pass have
		# already written, which is what lets an impulse travel more than one cord
		# per pass rather than exactly one.
		#
		# The three loops below are the same equation specialised on which end is
		# allowed to move. Writing it once with a weight of zero for the welded end
		# would be shorter, but it costs an extra vector scale and two array reads
		# on every constraint, and this loop runs about nine thousand times per
		# substep.
		var batch_from := panel.batch_from
		var batch_to := panel.batch_to
		var batch_wa := panel.batch_wa
		var batch_wb := panel.batch_wb
		var batch_count := batch_from.size()
		var passes := RELAX_ITERATIONS if fastest_sq > ripple_move_sq else 1
		for _pass_index in passes:
			for batch in batch_count:
				var from_index := batch_from[batch]
				var to_index := batch_to[batch]
				var weight_a := batch_wa[batch]
				var weight_b := batch_wb[batch]
				if weight_b == 0.0:
					for k in range(from_index, to_index):
						var a := con_a[k]
						var pa := pos[a]
						var d := pos[con_b[k]] - pa
						var length := d.length()
						if length < 0.000001:
							continue
						pos[a] = pa + d * ((length - con_rest[k]) / length * weight_a)
				elif weight_a == 0.0:
					for k in range(from_index, to_index):
						var b := con_b[k]
						var pb := pos[b]
						var d := pb - pos[con_a[k]]
						var length := d.length()
						if length < 0.000001:
							continue
						pos[b] = pb - d * ((length - con_rest[k]) / length * weight_b)
				else:
					for k in range(from_index, to_index):
						var a := con_a[k]
						var b := con_b[k]
						var pa := pos[a]
						var pb := pos[b]
						var d := pb - pa
						var length := d.length()
						if length < 0.000001:
							continue
						var correction := d * ((length - con_rest[k]) / length * weight_a)
						pos[a] = pa + correction
						pos[b] = pb - correction

		panel.dirty = true

		# 3. Sleep bookkeeping. The panel must be quiet for a while, not just for
		# a single step at the top of a swing where every node momentarily stops.
		if fastest_sq <= sleep_move_sq:
			panel.still_steps += 1
			if panel.still_steps >= SLEEP_STEPS:
				panel.awake = false
				# Kill the residual drift so a sleeping panel is exactly static.
				for i in range(node_from, node_to):
					prev[i] = pos[i]
		else:
			panel.still_steps = 0

	if touched_anything:
		_pos = pos
		_prev = prev


# --- net construction -------------------------------------------------------


func _build_net_grids() -> void:
	_pos = PackedVector3Array()
	_prev = PackedVector3Array()
	_rest = PackedVector3Array()
	_pinned = PackedByteArray()
	_con_a = PackedInt32Array()
	_con_b = PackedInt32Array()
	_con_rest = PackedFloat32Array()
	_panels = []

	_add_panel(PANEL_BACK, BACK_COLS, BACK_ROWS, Vector3.BACK, 0.25)
	_add_panel(PANEL_ROOF, ROOF_COLS, ROOF_ROWS, Vector3.DOWN, 0.0)
	_add_panel(PANEL_SIDE_LEFT, SIDE_COLS, SIDE_ROWS, Vector3.RIGHT, 0.25)
	_add_panel(PANEL_SIDE_RIGHT, SIDE_COLS, SIDE_ROWS, Vector3.LEFT, 0.25)


## Grid point of a panel in the goal's local space. All four panels are described
## here rather than in four separate builders, because they share one envelope:
## the mouth at z = 0, the back plane at z = NET_Z_BACK, and a roof that slides
## from the underside of the bar down to the back stanchion.
func _panel_point(id: int, i: int, j: int, cols: int, rows: int) -> Vector3:
	var u := float(i) / float(cols)
	var v := float(j) / float(rows)
	match id:
		PANEL_BACK:
			return Vector3(lerpf(-NET_HALF_X, NET_HALF_X, u), Field.NET_BACK_TOP * v, NET_Z_BACK)
		PANEL_ROOF:
			return Vector3(
				lerpf(-NET_HALF_X, NET_HALF_X, u),
				lerpf(ROOF_Y_FRONT, ROOF_Y_BACK, v),
				lerpf(NET_Z_FRONT, NET_Z_BACK, v)
			)
		PANEL_SIDE_LEFT, PANEL_SIDE_RIGHT:
			var side := -1.0 if id == PANEL_SIDE_LEFT else 1.0
			var top := lerpf(ROOF_Y_FRONT, ROOF_Y_BACK, u)
			return Vector3(side * NET_HALF_X, top * v, lerpf(NET_Z_FRONT, NET_Z_BACK, u))
		_:
			return Vector3.ZERO


## Texture coordinate of a grid point. Constant in grid space, so it is computed
## once at build time and never touched again. Deriving it from the world
## position rather than from (i, j) keeps the cord pattern continuous across the
## seam between two panels of different resolutions.
func _panel_uv(id: int, p: Vector3) -> Vector2:
	match id:
		PANEL_BACK:
			return Vector2(p.x, p.y) / UV_METRES
		PANEL_ROOF:
			return Vector2(p.x, -p.z) / UV_METRES
		PANEL_SIDE_LEFT:
			return Vector2(p.z, p.y) / UV_METRES
		PANEL_SIDE_RIGHT:
			return Vector2(-p.z, p.y) / UV_METRES
		_:
			return Vector2.ZERO


func _add_panel(id: int, cols: int, rows: int, facing: Vector3, up_bias: float) -> void:
	var panel := NetPanel.new()
	panel.id = id
	panel.cols = cols
	panel.rows = rows
	panel.facing = facing
	panel.up_bias = up_bias
	panel.node_from = _pos.size()

	var wide := cols + 1
	var tall := rows + 1
	var total := wide * tall
	_pos.resize(panel.node_from + total)
	_prev.resize(panel.node_from + total)
	_rest.resize(panel.node_from + total)
	_pinned.resize(panel.node_from + total)
	panel.uv.resize(total)

	for j in tall:
		for i in wide:
			var local := j * wide + i
			var index := panel.node_from + local
			var p := _panel_point(id, i, j, cols, rows)
			_pos[index] = p
			_prev[index] = p
			_rest[index] = p
			# Every panel boundary sits on a frame member: the posts and the bar at
			# the front, the back stanchion at the rear, the side rails on top and
			# the ground pegs at the bottom. So the whole border is pinned, and the
			# interior is what moves.
			var edge := i == 0 or i == cols or j == 0 or j == rows
			_pinned[index] = 1 if edge else 0
			panel.uv[local] = _panel_uv(id, p)

	panel.node_to = _pos.size()
	panel.con_from = _con_a.size()
	_add_panel_springs(panel)
	panel.con_to = _con_a.size()

	panel.tris = _build_indices(cols, rows)
	panel.tans = _build_tangents(panel)

	panel.mesh = ArrayMesh.new()
	panel.instance = MeshInstance3D.new()
	panel.instance.name = "NetPanel%d" % id
	panel.instance.mesh = panel.mesh
	# The net is a thin cut out sheet: it must not cast the hard shadow of a solid
	# quad across the turf, but it should still take light.
	panel.instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_net_root.add_child(panel.instance)

	_panels.append(panel)


## Builds the three spring families of one panel and lays them out in batches.
##
## A batch is a run of constraints that share a stiffness and a pin pattern, so
## the solver can hoist both correction weights out of the inner loop and drop
## every per constraint branch. There are at most nine of them per panel: three
## families crossed with three pin patterns (both ends free, only the first free,
## only the second free). Constraints with both ends welded to the frame are
## dropped entirely, since they can never move anything.
func _add_panel_springs(panel: NetPanel) -> void:
	var cols := panel.cols
	var rows := panel.rows
	var stiffness: PackedFloat32Array = [STIFF_STRUCT, STIFF_SHEAR, STIFF_BEND]
	var tension: PackedFloat32Array = [PRETENSION, PRETENSION, 1.0]

	# Nine buckets of (a, b) pairs, flattened.
	var buckets: Array = []
	for slot in 9:
		buckets.append(PackedInt32Array())

	for j in rows + 1:
		for i in cols + 1:
			# Structural: the cord itself. It sets the mesh size.
			if i < cols:
				_bucket_spring(buckets, 0, panel.at(i, j), panel.at(i + 1, j))
			if j < rows:
				_bucket_spring(buckets, 0, panel.at(i, j), panel.at(i, j + 1))
			# Shear: the two diagonals of the cell. These are what stop the square
			# mesh from collapsing into a parallelogram under a sideways load.
			if i < cols and j < rows:
				_bucket_spring(buckets, 1, panel.at(i, j), panel.at(i + 1, j + 1))
				_bucket_spring(buckets, 1, panel.at(i + 1, j), panel.at(i, j + 1))
			# Bend: two cords along. They resist a sharp fold across a cord line.
			# At rest length exactly, not pre-tensioned: their job is to keep the
			# surface smooth, not to add tension on top of the structural springs.
			if i < cols - 1:
				_bucket_spring(buckets, 2, panel.at(i, j), panel.at(i + 2, j))
			if j < rows - 1:
				_bucket_spring(buckets, 2, panel.at(i, j), panel.at(i, j + 2))

	for slot in 9:
		var pairs: PackedInt32Array = buckets[slot]
		if pairs.is_empty():
			continue
		var family := slot / 3
		var pattern := slot % 3
		var stiff := stiffness[family]
		var stretch := tension[family]
		var weight_a := 0.0
		var weight_b := 0.0
		match pattern:
			0:  # both free, the correction is shared
				weight_a = stiff * 0.5
				weight_b = stiff * 0.5
			1:  # b is welded, a takes all of it
				weight_a = stiff
			_:  # a is welded, b takes all of it
				weight_b = stiff

		var from_index := _con_a.size()
		var count := pairs.size() / 2
		for n in count:
			var a := pairs[n * 2]
			var b := pairs[n * 2 + 1]
			_con_a.append(a)
			_con_b.append(b)
			_con_rest.append(_rest[a].distance_to(_rest[b]) * stretch)
		panel.batch_from.append(from_index)
		panel.batch_to.append(_con_a.size())
		panel.batch_wa.append(weight_a)
		panel.batch_wb.append(weight_b)


## Tangent frame of a panel, taken from its rest shape. The u tangent is the
## direction the texture's u axis runs in, which on every one of these grids is
## simply the direction of increasing i.
func _build_tangents(panel: NetPanel) -> PackedFloat32Array:
	var cols := panel.cols
	var rows := panel.rows
	var wide := cols + 1
	var out := PackedFloat32Array()
	out.resize(panel.node_count() * 4)
	for j in rows + 1:
		var row_base := j * wide
		for i in wide:
			var low := panel.node_from + row_base + maxi(i - 1, 0)
			var high := panel.node_from + row_base + mini(i + 1, cols)
			var tangent := _rest[high] - _rest[low]
			if tangent.length_squared() < 1e-12:
				tangent = Vector3.RIGHT
			tangent = tangent.normalized()
			var slot := (row_base + i) * 4
			out[slot] = tangent.x
			out[slot + 1] = tangent.y
			out[slot + 2] = tangent.z
			out[slot + 3] = 1.0
	return out


func _bucket_spring(buckets: Array, family: int, a: int, b: int) -> void:
	var a_free := _pinned[a] == 0
	var b_free := _pinned[b] == 0
	if not a_free and not b_free:
		return
	var pattern := 0 if a_free and b_free else (1 if a_free else 2)
	var pairs: PackedInt32Array = buckets[family * 3 + pattern]
	pairs.append(a)
	pairs.append(b)
	buckets[family * 3 + pattern] = pairs


## Triangle list of a cols x rows grid, wound clockwise in grid space, which is
## the order Godot treats as front facing. The cord material is two sided, so the
## winding only decides which side the engine calls the front; the side that gets
## lit is decided by the vertex normals, which _rebuild_panel_mesh orients
## explicitly.
func _build_indices(cols: int, rows: int) -> PackedInt32Array:
	var out := PackedInt32Array()
	out.resize(cols * rows * 6)
	var wide := cols + 1
	var cursor := 0
	for j in rows:
		for i in cols:
			var n00 := j * wide + i
			var n10 := n00 + 1
			var n01 := n00 + wide
			var n11 := n01 + 1
			out[cursor] = n00
			out[cursor + 1] = n01
			out[cursor + 2] = n11
			out[cursor + 3] = n00
			out[cursor + 4] = n11
			out[cursor + 5] = n10
			cursor += 6
	return out


# --- net rendering ----------------------------------------------------------


## Rebuilds one panel's surface from the current node positions.
##
## Normals are recomputed every frame from the grid tangents rather than by
## accumulating face normals. Both give the same answer on a regular grid, but the
## tangent form costs one cross product per vertex instead of one per triangle,
## which on these panels is a quarter of the work. UVs, tangents and the index
## list are all constant in grid space and were built once.
##
## The shading normal is forced to the side of the sheet that faces into the goal
## and then, on the vertical panels only, leaned partway towards the sky. That is
## not a fudge: the surface is an array of round cords, not a sheet, and the lit
## part of a horizontal cord faces the floodlights whatever the panel is doing.
## Without the lean the back panel is a flat grey wall under a light that grazes
## it, and the ripple is invisible in exactly the moment it matters.
func _rebuild_panel_mesh(panel: NetPanel) -> void:
	var cols := panel.cols
	var rows := panel.rows
	var wide := cols + 1
	var base := panel.node_from
	var total := panel.node_count()

	var facing := panel.facing
	var bias := panel.up_bias
	var counter_bias := 1.0 - bias
	var lean := Vector3.UP * bias

	var pos := _pos
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	verts.resize(total)
	norms.resize(total)

	for j in rows + 1:
		var row_base := j * wide
		var row_low := maxi(j - 1, 0) * wide
		var row_high := mini(j + 1, rows) * wide
		for i in wide:
			var local := row_base + i
			var i_low := maxi(i - 1, 0)
			var i_high := mini(i + 1, cols)

			var tangent_u := pos[base + row_base + i_high] - pos[base + row_base + i_low]
			var tangent_v := pos[base + row_high + i] - pos[base + row_low + i]

			var normal := tangent_u.cross(tangent_v)
			if normal.length_squared() < 1e-12:
				normal = facing
			else:
				normal = normal.normalized()
				if normal.dot(facing) < 0.0:
					normal = -normal
			if bias > 0.0:
				normal = (normal * counter_bias + lean).normalized()

			verts[local] = pos[base + local]
			norms[local] = normal

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_TANGENT] = panel.tans
	arrays[Mesh.ARRAY_TEX_UV] = panel.uv
	arrays[Mesh.ARRAY_INDEX] = panel.tris

	panel.mesh.clear_surfaces()
	panel.mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	# The material goes on the surface, not on the instance: clear_surfaces()
	# throws away the override slots, so an instance override would silently be
	# lost on the first rebuild and the net would render untextured.
	panel.mesh.surface_set_material(0, Mats.net())


# --- frame construction -----------------------------------------------------


func _build_frame() -> void:
	var post_length := BAR_CENTRE_Y + Field.POST_RADIUS
	var bar_length := Field.GOAL_WIDTH + 2.0 * Field.POST_RADIUS

	for side_index in 2:
		var side := -1.0 if side_index == 0 else 1.0
		_add_tube(
			Vector3(side * POST_HALF_X, post_length * 0.5, 0.0),
			Vector3.UP,
			post_length,
			Field.POST_RADIUS,
			Mats.post()
		)

	_add_tube(
		Vector3(0.0, BAR_CENTRE_Y, 0.0), Vector3.RIGHT, bar_length, Field.POST_RADIUS, Mats.post()
	)

	# Back frame. Without it the pinned rear edges of the cloth would hang in mid
	# air, which reads as a bug even to someone who has never seen a goal net.
	var back_z := -Field.NET_DEPTH
	var back_top := Field.NET_BACK_TOP
	var back_mat := _back_frame_material()
	for side_index in 2:
		var side := -1.0 if side_index == 0 else 1.0
		var x := side * POST_HALF_X
		# Rear upright.
		_add_tube(
			Vector3(x, back_top * 0.5, back_z),
			Vector3.UP,
			back_top,
			BACK_TUBE_RADIUS,
			back_mat
		)
		# Sloping side rail, from the top of the post back to the rear upright.
		var top_front := Vector3(x, BAR_CENTRE_Y, 0.0)
		var top_back := Vector3(x, back_top, back_z)
		var span := top_back - top_front
		_add_tube(
			(top_front + top_back) * 0.5,
			span.normalized(),
			span.length(),
			BACK_TUBE_RADIUS,
			back_mat
		)
		# Ground rail along the side, holding the bottom of the side panel down.
		_add_tube(
			Vector3(x, BACK_TUBE_RADIUS, back_z * 0.5),
			Vector3.BACK,
			Field.NET_DEPTH,
			BACK_TUBE_RADIUS,
			back_mat
		)

	# Rear top rail and rear ground rail.
	var rail_length := Field.GOAL_WIDTH + 2.0 * Field.POST_RADIUS
	_add_tube(
		Vector3(0.0, back_top, back_z), Vector3.RIGHT, rail_length, BACK_TUBE_RADIUS, back_mat
	)
	_add_tube(
		Vector3(0.0, BACK_TUBE_RADIUS, back_z),
		Vector3.RIGHT,
		rail_length,
		BACK_TUBE_RADIUS,
		back_mat
	)


## Painted metal of the back stanchions: the rear uprights, the sloping side
## rails and the two ground rails that the cloth is pinned to.
##
## NOT `Mats.steel()`, and the reason is the single most visible rendering fault
## the goal ever had. That material is 0.88 metallic, which is correct for a
## galvanised floodlight mast lit by four spots and completely wrong here. A
## metal has no diffuse term at all: everything it shows is a reflection, so a
## dark grey metal with nothing bright to reflect renders BLACK. Seen from behind
## the goal against a pale afternoon sky, these eight tubes drew as thick
## near black bars filling the lower two thirds of the frame, and they read as a
## broken shader rather than as shadow. `Stadium._member_material` had already
## learned the same lesson on its handrails.
##
## A real goal's back frame is painted the same white as the uprights, in a
## lighter section. So it is painted here too: a dielectric (metallic 0), pulled a
## third of the way towards the steel colour so the secondary frame stays a step
## under the posts on the contrast ladder instead of competing with them, and
## rougher than the posts because the back of a goal is not polished. The tiny
## emission floor is the same trick `Mats.post()` uses, at a third of its size:
## enough that the tube never reaches pure black inside the net, small enough that
## the cylindrical shading survives.
##
## Built here rather than in `Mats` because it is the only surface in the game
## that wants it, and it is cached per GoalFrame so the eight tubes share one.
func _back_frame_material() -> StandardMaterial3D:
	if _back_frame_mat != null:
		return _back_frame_mat
	var mat := Mats.post().duplicate() as StandardMaterial3D
	var tint := Palette.mix(Palette.POST_WHITE, Palette.STEEL, 0.34)
	mat.albedo_color = tint
	mat.metallic = 0.0
	mat.metallic_specular = 0.42
	mat.roughness = 0.48
	mat.clearcoat_enabled = false
	mat.emission_enabled = true
	mat.emission = tint
	mat.emission_energy_multiplier = 0.012
	_back_frame_mat = mat
	return _back_frame_mat


func _add_tube(
	centre: Vector3, axis: Vector3, length: float, radius: float, material: Material
) -> void:
	var instance := MeshInstance3D.new()
	instance.mesh = Meshes.post_mesh(length, radius, axis)
	instance.position = centre
	if material != null:
		instance.material_override = material
	_frame_root.add_child(instance)


func _build_colliders() -> void:
	var frame_body := StaticBody3D.new()
	frame_body.name = "FrameBody"
	frame_body.collision_layer = Layers.GOAL
	# Static scenery detects nothing, it is only ever detected.
	frame_body.collision_mask = 0
	add_child(frame_body)

	var post_length := BAR_CENTRE_Y + Field.POST_RADIUS
	for side_index in 2:
		var side := -1.0 if side_index == 0 else 1.0
		_add_cylinder_shape(
			frame_body,
			Vector3(side * POST_HALF_X, post_length * 0.5, 0.0),
			Basis.IDENTITY,
			post_length,
			Field.POST_RADIUS
		)
	_add_cylinder_shape(
		frame_body,
		Vector3(0.0, BAR_CENTRE_Y, 0.0),
		Basis(Vector3.BACK, PI * 0.5),
		Field.GOAL_WIDTH + 2.0 * Field.POST_RADIUS,
		Field.POST_RADIUS
	)

	# The net gets its own body on its own layer. The ball does its own swept
	# tests against the cloth, but anything else in the game (a rebound prop, a
	# challenge target) still needs something solid to hit.
	var net_body := StaticBody3D.new()
	net_body.name = "NetBody"
	net_body.collision_layer = Layers.NET
	net_body.collision_mask = 0
	add_child(net_body)

	var width := NET_HALF_X * 2.0
	var depth := NET_Z_FRONT - NET_Z_BACK
	var thickness := 0.03

	_add_box_shape(
		net_body,
		Vector3(0.0, Field.NET_BACK_TOP * 0.5, NET_Z_BACK),
		Basis.IDENTITY,
		Vector3(width, Field.NET_BACK_TOP, thickness)
	)

	var slope := atan2(ROOF_Y_FRONT - ROOF_Y_BACK, depth)
	var roof_span := Vector2(depth, ROOF_Y_FRONT - ROOF_Y_BACK).length()
	_add_box_shape(
		net_body,
		Vector3(0.0, (ROOF_Y_FRONT + ROOF_Y_BACK) * 0.5, (NET_Z_FRONT + NET_Z_BACK) * 0.5),
		Basis(Vector3.RIGHT, -slope),
		Vector3(width, thickness, roof_span)
	)

	# The side panels are trapezoids; a box of their mean height is close enough
	# for a collider that only ever catches a stray prop.
	var side_height := (ROOF_Y_FRONT + ROOF_Y_BACK) * 0.5
	for side_index in 2:
		var side := -1.0 if side_index == 0 else 1.0
		_add_box_shape(
			net_body,
			Vector3(side * NET_HALF_X, side_height * 0.5, (NET_Z_FRONT + NET_Z_BACK) * 0.5),
			Basis.IDENTITY,
			Vector3(thickness, side_height, depth)
		)


func _add_cylinder_shape(
	body: StaticBody3D, centre: Vector3, basis: Basis, height: float, radius: float
) -> void:
	var shape := CylinderShape3D.new()
	shape.height = height
	shape.radius = radius
	var node := CollisionShape3D.new()
	node.shape = shape
	node.transform = Transform3D(basis, centre)
	body.add_child(node)


func _add_box_shape(body: StaticBody3D, centre: Vector3, basis: Basis, size: Vector3) -> void:
	var shape := BoxShape3D.new()
	shape.size = size
	var node := CollisionShape3D.new()
	node.shape = shape
	node.transform = Transform3D(basis, centre)
	body.add_child(node)


func _discard() -> void:
	_built = false
	_panels = []
	_pos = PackedVector3Array()
	_prev = PackedVector3Array()
	_rest = PackedVector3Array()
	_pinned = PackedByteArray()
	_con_a = PackedInt32Array()
	_con_b = PackedInt32Array()
	_con_rest = PackedFloat32Array()
	_accumulator = 0.0
	_frame_root = null
	_net_root = null
	# Dropped with the tubes that held it, so a rebuild does not keep the old
	# material alive on nothing.
	_back_frame_mat = null
	for child in get_children():
		remove_child(child)
		child.queue_free()


