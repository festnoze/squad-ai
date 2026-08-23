class_name Layout
extends RefCounted
## Deterministic plan of the 4096 m Normandy pocket: sites, roads and rivers.
##
## The whole plan is built inside `_init` from a single integer seed and is
## considered IMMUTABLE afterwards, which makes it safe to read from the terrain
## worker threads. There is exactly one documented exception:
## `Heightfield.bake_sites()` fills `Site.ground` once, on the main thread,
## right after construction and before any worker runs.
##
## Compass convention used by the entire project:
##   NORTH = -Z, SOUTH = +Z, EAST = +X, WEST = -X.
## The wooded ridge sits in the north (z <= -1150), the marshes in the south
## west, the river runs from north to south, the sea is on the east edge.

# --- Site kinds -------------------------------------------------------------

const SITE_VILLAGE := 0
const SITE_FARM := 1
const SITE_CHURCH_TOWN := 2
const SITE_AIRFIELD := 3
const SITE_BUNKER := 4
const SITE_CAMP := 5
const SITE_CROSSROADS := 6
const SITE_BRIDGE := 7
const SITE_RUIN := 8

# --- Contract constants -----------------------------------------------------

const ROAD_HALF_WIDTH := 3.5
const ROAD_FADE := 5.0
const SITE_COUNT := 22

# --- Extra tuning constants (additions, nothing renamed) --------------------

## Half width and fade of a river bed, mirrored by Heightfield when carving.
const RIVER_HALF_WIDTH := 9.0
const RIVER_FADE := 26.0
## How far a road is kept from the water when it does not cross on a bridge.
const RIVER_BANK_CLEARANCE := 28.0
## Number of capturable sectors. Exactly this many sites carry `is_sector`.
const SECTOR_COUNT := 8
## Poisson disc constraint between two sites, in metres.
const MIN_SITE_DISTANCE := 180.0
## A site flattens the ground fully inside `radius * SITE_CORE` and fades out
## at `radius * SITE_OUTER`.
const SITE_CORE := 0.72
const SITE_OUTER := 1.35
const WORLD_HALF := 2048.0
## No site centre is ever placed closer than this to the world edge.
const PLACE_MARGIN := 210.0
## Broad phase acceleration grid: 128 m cells over the 4096 m square.
const CELL := 128.0
const GRID := 32

## Normandy sounding place names. Drawn without repetition (Fisher Yates on a
## copy), so two sites never share a name.
const NAMES: PackedStringArray = [
	"Sainte-Colombe", "Vierville", "Colleville", "Breville", "Graignes",
	"Montfarville", "Nehou", "Picauville", "Beuzeville", "Angoville",
	"Cerisy-la-Foret", "Trevieres", "Formigny", "Isigny-le-Vieux", "Lestre",
	"Quineville", "Ravenoville", "Auvers", "Sainte-Honorine", "Hebecrevon",
	"Marigny", "Camprond", "Periers-sur-Ay", "Vouilly", "Osmanville",
	"Gefosse", "Cricqueville", "Louvieres", "Vaubadon", "Blay",
	"Rubercy", "Tournieres", "Le Molay", "Etreham", "Neuilly-la-Foret",
	"La Cambe", "Surrain", "Mandeville", "Le Vast", "Sainte-Marguerite",
]

# --- Site --------------------------------------------------------------------

## One point of interest of the pocket. Plain data, never mutated after
## `Heightfield.bake_sites()`.
class Site extends RefCounted:
	var id: int = -1
	var kind: int = 0
	var center: Vector2 = Vector2.ZERO
	var radius: float = 40.0
	var ground: float = 0.0
	var rotation: float = 0.0
	var seed: int = 0
	var garrison: int = 0
	var display_name: String = ""
	var is_sector: bool = false

	## True once Heightfield.bake_sites() has written `ground`.
	var _ground_baked: bool = false

	## Called once by Heightfield.bake_sites(). Before that call `ground` is
	## meaningless and the site does not flatten anything at all.
	func set_ground(value: float) -> void:
		ground = value
		_ground_baked = true

	func has_ground() -> bool:
		return _ground_baked


## Internal placement recipe for one site, consumed by the Poisson pass.
class _Spec extends RefCounted:
	var kind: int
	var anchor: Vector2
	var region: float
	var is_sector: bool
	var radius_min: float
	var radius_max: float
	var garrison_min: int
	var garrison_max: int

	func _init(p_kind: int, ax: float, az: float, sector: bool,
			rmin: float, rmax: float, gmin: int, gmax: int, reg: float) -> void:
		kind = p_kind
		anchor = Vector2(ax, az)
		is_sector = sector
		radius_min = rmin
		radius_max = rmax
		garrison_min = gmin
		garrison_max = gmax
		region = reg

# --- Public state ------------------------------------------------------------

var world_seed: int = 0
var sites: Array[Site] = []
var roads: Array[PackedVector2Array] = []
var rivers: Array[PackedVector2Array] = []

# --- Private acceleration data (built once, read only afterwards) ------------

## Flat road segments, 4 floats each: x1, z1, x2, z2.
var _road_seg := PackedFloat32Array()
## Flat river segments, same packing.
var _river_seg := PackedFloat32Array()
## Cell -> indices into _road_seg / _river_seg / sites.
var _cell_roads: Array[PackedInt32Array] = []
var _cell_rivers: Array[PackedInt32Array] = []
var _cell_sites: Array[PackedInt32Array] = []
var _spawn := Vector2.ZERO
## Coarse 64 m occupancy mask of the river network, used at build time only as
## a prefilter for the "does this road ford the river" test.
var _river_mask := PackedByteArray()


func _init(new_seed: int) -> void:
	world_seed = new_seed
	var rng := RandomNumberGenerator.new()
	rng.seed = new_seed
	_build_rivers(rng)
	_build_sites(rng)
	_build_roads(rng)
	_build_grids()
	_pick_spawn(rng)

# --- Queries -----------------------------------------------------------------

func site_by_id(id: int) -> Site:
	if id < 0 or id >= sites.size():
		return null
	return sites[id]


func sector_ids() -> PackedInt32Array:
	var out := PackedInt32Array()
	for s: Site in sites:
		if s.is_sector:
			out.append(s.id)
	return out


## Sites whose footprint may touch the given 64 m tile. Cheap broad phase, the
## caller is expected to refine.
func sites_in_tile(tx: int, tz: int) -> Array[Site]:
	var out: Array[Site] = []
	var x0 := float(tx) * 64.0
	var z0 := float(tz) * 64.0
	var x1 := x0 + 64.0
	var z1 := z0 + 64.0
	for s: Site in sites:
		var cx := clampf(s.center.x, x0, x1)
		var cz := clampf(s.center.y, z0, z1)
		var dx := s.center.x - cx
		var dz := s.center.y - cz
		var reach := s.radius * SITE_OUTER
		if dx * dx + dz * dz <= reach * reach:
			out.append(s)
	return out


func nearest_site(x: float, z: float, kind: int = -1) -> Site:
	var best: Site = null
	var best_d := INF
	for s: Site in sites:
		if kind >= 0 and s.kind != kind:
			continue
		var dx := s.center.x - x
		var dz := s.center.y - z
		var d := dx * dx + dz * dz
		if d < best_d:
			best_d = d
			best = s
	return best


## 1.0 on the road centreline, fading to 0 at ROAD_HALF_WIDTH + ROAD_FADE.
func road_influence(x: float, z: float) -> float:
	var ids := _cell_roads[_cell_index(x, z)]
	if ids.is_empty():
		return 0.0
	var outer := ROAD_HALF_WIDTH + ROAD_FADE
	var limit := outer * outer
	var best := limit
	for i: int in ids:
		var b := i * 4
		var d2 := _seg_distance2(x, z, _road_seg[b], _road_seg[b + 1], _road_seg[b + 2], _road_seg[b + 3])
		if d2 < best:
			best = d2
	if best >= limit:
		return 0.0
	var d := sqrt(best)
	if d <= ROAD_HALF_WIDTH:
		return 1.0
	return smoothstep(0.0, 1.0, (outer - d) / ROAD_FADE)


## Same shape as road_influence, used to carve the river bed.
func river_influence(x: float, z: float) -> float:
	var ids := _cell_rivers[_cell_index(x, z)]
	if ids.is_empty():
		return 0.0
	var outer := RIVER_HALF_WIDTH + RIVER_FADE
	var limit := outer * outer
	var best := limit
	for i: int in ids:
		var b := i * 4
		var d2 := _seg_distance2(x, z, _river_seg[b], _river_seg[b + 1], _river_seg[b + 2], _river_seg[b + 3])
		if d2 < best:
			best = d2
	if best >= limit:
		return 0.0
	var d := sqrt(best)
	if d <= RIVER_HALF_WIDTH:
		return 1.0
	return smoothstep(0.0, 1.0, (outer - d) / RIVER_FADE)


## Weight (0..1) and target height of the strongest flattening site.
##
## Two deliberate behaviours, both required by the initialisation order:
##  - a site whose ground has not been baked yet returns a ZERO weight, so
##    `Heightfield.height_at()` falls back to the natural relief while
##    `bake_sites()` is still running;
##  - a SITE_BRIDGE never flattens anything, otherwise it would fill the river
##    bed it is supposed to span.
func site_flatten(x: float, z: float) -> Vector2:
	var ids := _cell_sites[_cell_index(x, z)]
	if ids.is_empty():
		return Vector2.ZERO
	var best_w := 0.0
	var best_h := 0.0
	for i: int in ids:
		var s := sites[i]
		if s.kind == SITE_BRIDGE or not s.has_ground():
			continue
		var dx := s.center.x - x
		var dz := s.center.y - z
		var outer := s.radius * SITE_OUTER
		var d2 := dx * dx + dz * dz
		if d2 >= outer * outer:
			continue
		var core := s.radius * SITE_CORE
		var d := sqrt(d2)
		var w := 1.0
		if d > core:
			w = smoothstep(0.0, 1.0, (outer - d) / maxf(1.0, outer - core))
		if w > best_w:
			best_w = w
			best_h = s.ground
	return Vector2(best_w, best_h)


## The player's starting point: the allied safehouse of the first village.
func spawn_point() -> Vector2:
	return _spawn


## The allied village the campaign starts from. Never null once built.
func start_site() -> Site:
	if sites.is_empty():
		return null
	return sites[0]

# --- Rivers ------------------------------------------------------------------

## One meandering river from the northern ridge down to the southern marshes,
## plus a short tributary coming out of the ridge. Both are polylines in world
## x, z, densified to roughly 16 m so the segment grid stays fine grained.
func _build_rivers(rng: RandomNumberGenerator) -> void:
	rivers = []
	var main := PackedVector2Array([
		Vector2(-110.0, -2140.0),
		Vector2(-60.0, -1760.0),
		Vector2(-185.0, -1400.0),
		Vector2(-90.0, -1040.0),
		Vector2(-230.0, -700.0),
		Vector2(-160.0, -380.0),
		Vector2(-315.0, -40.0),
		Vector2(-250.0, 320.0),
		Vector2(-425.0, 640.0),
		Vector2(-360.0, 980.0),
		Vector2(-555.0, 1300.0),
		Vector2(-520.0, 1660.0),
		Vector2(-700.0, 2140.0),
	])
	rivers.append(_smooth_curve(main, 16.0, rng, 9.0))
	var trib := PackedVector2Array([
		Vector2(-980.0, -1780.0),
		Vector2(-760.0, -1520.0),
		Vector2(-560.0, -1330.0),
		Vector2(-330.0, -1180.0),
		Vector2(-150.0, -1080.0),
		Vector2(-90.0, -1040.0),
	])
	rivers.append(_smooth_curve(trib, 16.0, rng, 6.0))
	_mark_river_mask()


## Flags every 64 m cell the river runs through, plus its neighbours. Build time
## prefilter only, never read by the game.
func _mark_river_mask() -> void:
	_river_mask = PackedByteArray()
	_river_mask.resize(64 * 64)
	_river_mask.fill(0)
	for line: PackedVector2Array in rivers:
		for p: Vector2 in line:
			var cx := clampi(floori((p.x + WORLD_HALF) / 64.0), 0, 63)
			var cz := clampi(floori((p.y + WORLD_HALF) / 64.0), 0, 63)
			for oz in range(-1, 2):
				for ox in range(-1, 2):
					var ax := clampi(cx + ox, 0, 63)
					var az := clampi(cz + oz, 0, 63)
					_river_mask[az * 64 + ax] = 1


func _near_river_cell(p: Vector2) -> bool:
	var cx := clampi(floori((p.x + WORLD_HALF) / 64.0), 0, 63)
	var cz := clampi(floori((p.y + WORLD_HALF) / 64.0), 0, 63)
	return _river_mask[cz * 64 + cx] != 0


## Catmull-Rom pass over `pts`, sampled every `step` metres, with a small
## deterministic wobble so no reach of the river is a perfect arc.
func _smooth_curve(pts: PackedVector2Array, step: float, rng: RandomNumberGenerator,
		wobble: float) -> PackedVector2Array:
	var out := PackedVector2Array()
	var n := pts.size()
	if n < 2:
		return pts
	var phase := rng.randf() * TAU
	var phase2 := rng.randf() * TAU
	for i in n - 1:
		var p0 := pts[maxi(i - 1, 0)]
		var p1 := pts[i]
		var p2 := pts[i + 1]
		var p3 := pts[mini(i + 2, n - 1)]
		var span := p1.distance_to(p2)
		var steps := maxi(2, int(ceil(span / step)))
		for k in steps:
			var t := float(k) / float(steps)
			var p := _catmull(p0, p1, p2, p3, t)
			var u := (float(i) + t) * 0.9
			var tangent := (p2 - p1).normalized()
			var perp := Vector2(-tangent.y, tangent.x)
			p += perp * (sin(u * 1.7 + phase) * 0.7 + sin(u * 4.1 + phase2) * 0.3) * wobble
			out.append(p)
	out.append(pts[n - 1])
	return out


static func _catmull(p0: Vector2, p1: Vector2, p2: Vector2, p3: Vector2, t: float) -> Vector2:
	var t2 := t * t
	var t3 := t2 * t
	return 0.5 * ((2.0 * p1) + (-p0 + p2) * t
			+ (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
			+ (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3)

# --- Sites -------------------------------------------------------------------

## Placement recipes. The order matters: index 0 is the allied safehouse
## village (garrison 0), indices 1 to 8 are the eight capturable sectors, the
## rest fills the bocage. Kinds add up to the contract minimum: 1 airfield,
## 2 bunkers, 1 church town, 5 farms, 2 bridges, 1 camp, 1 ruin.
func _site_specs() -> Array[_Spec]:
	var out: Array[_Spec] = []
	# Allied start: a quiet village in the western bocage, no garrison at all.
	out.append(_Spec.new(SITE_VILLAGE, -1250.0, -250.0, false, 66.0, 82.0, 0, 0, 165.0))
	# --- the eight sectors ---
	out.append(_Spec.new(SITE_CHURCH_TOWN, 350.0, -150.0, true, 96.0, 118.0, 20, 26, 165.0))
	out.append(_Spec.new(SITE_VILLAGE, 900.0, 700.0, true, 62.0, 78.0, 9, 14, 165.0))
	out.append(_Spec.new(SITE_VILLAGE, -1500.0, -1150.0, true, 60.0, 76.0, 8, 13, 165.0))
	out.append(_Spec.new(SITE_VILLAGE, 250.0, 1450.0, true, 62.0, 80.0, 9, 14, 165.0))
	out.append(_Spec.new(SITE_AIRFIELD, 1150.0, -900.0, true, 150.0, 176.0, 24, 30, 130.0))
	out.append(_Spec.new(SITE_BUNKER, 1790.0, -420.0, true, 26.0, 34.0, 10, 15, 105.0))
	out.append(_Spec.new(SITE_BUNKER, 1700.0, 1450.0, true, 26.0, 34.0, 10, 15, 105.0))
	out.append(_Spec.new(SITE_CAMP, -900.0, -1500.0, true, 58.0, 72.0, 16, 22, 150.0))
	# --- ordinary sites ---
	out.append(_Spec.new(SITE_VILLAGE, -620.0, 1780.0, false, 54.0, 70.0, 6, 11, 150.0))
	out.append(_Spec.new(SITE_VILLAGE, 1380.0, 320.0, false, 54.0, 70.0, 7, 12, 150.0))
	out.append(_Spec.new(SITE_FARM, -1720.0, 380.0, false, 34.0, 46.0, 2, 5, 150.0))
	out.append(_Spec.new(SITE_FARM, 760.0, -1500.0, false, 34.0, 46.0, 2, 5, 150.0))
	out.append(_Spec.new(SITE_FARM, -430.0, -1010.0, false, 34.0, 46.0, 2, 6, 150.0))
	out.append(_Spec.new(SITE_FARM, 980.0, 1650.0, false, 34.0, 46.0, 2, 5, 150.0))
	out.append(_Spec.new(SITE_FARM, -1150.0, 780.0, false, 34.0, 46.0, 2, 6, 150.0))
	out.append(_Spec.new(SITE_BRIDGE, 0.0, -500.0, false, 16.0, 22.0, 4, 8, 0.0))
	out.append(_Spec.new(SITE_BRIDGE, 0.0, 1000.0, false, 16.0, 22.0, 4, 8, 0.0))
	out.append(_Spec.new(SITE_RUIN, 1450.0, -1680.0, false, 30.0, 42.0, 0, 4, 150.0))
	out.append(_Spec.new(SITE_CROSSROADS, 600.0, -700.0, false, 18.0, 26.0, 3, 6, 170.0))
	out.append(_Spec.new(SITE_CROSSROADS, -800.0, 300.0, false, 18.0, 26.0, 3, 6, 170.0))
	out.append(_Spec.new(SITE_CROSSROADS, 1150.0, -100.0, false, 18.0, 26.0, 3, 6, 170.0))
	return out


func _build_sites(rng: RandomNumberGenerator) -> void:
	var specs := _site_specs()
	if specs.size() != SITE_COUNT:
		push_warning("Layout: expected %d specs, got %d" % [SITE_COUNT, specs.size()])
	var names := _draw_names(rng, specs.size())
	var placed := PackedVector2Array()
	var reach := PackedFloat32Array()
	sites = []
	for i in specs.size():
		var spec := specs[i]
		var pos := _place_site(spec, placed, reach, rng)
		placed.append(pos)
		reach.append(spec.radius_max * SITE_OUTER)
		var s := Site.new()
		s.id = i
		s.kind = spec.kind
		s.center = pos
		s.radius = rng.randf_range(spec.radius_min, spec.radius_max)
		s.rotation = rng.randf() * TAU
		s.seed = _mix_seed(world_seed, i * 7919 + 13)
		s.garrison = rng.randi_range(spec.garrison_min, spec.garrison_max)
		s.is_sector = spec.is_sector
		s.display_name = _decorate_name(spec.kind, names[i])
		sites.append(s)


## Deterministic Poisson dart throwing inside the recipe region. Bridges are a
## special case: they are snapped onto the main river instead.
func _place_site(spec: _Spec, placed: PackedVector2Array, reach: PackedFloat32Array,
		rng: RandomNumberGenerator) -> Vector2:
	if spec.kind == SITE_BRIDGE:
		return _river_anchor(spec.anchor.y, rng)
	var clearance := spec.radius_max * SITE_OUTER
	for attempt in 48:
		var angle := rng.randf() * TAU
		var radius := sqrt(rng.randf()) * spec.region
		var candidate := spec.anchor + Vector2(cos(angle), sin(angle)) * radius
		if _is_valid_site(candidate, placed, reach, spec.kind, clearance):
			return candidate
	# Fallback: the hand placed anchor, pushed out of the river and of any
	# neighbour that would break the minimum distance.
	return _relax(spec.anchor, placed, reach, clearance)


## Poisson disc test plus the world rules: footprints never overlap, never reach
## into the river bed, and only bunkers stand on the coastal strip.
func _is_valid_site(pos: Vector2, placed: PackedVector2Array, reach: PackedFloat32Array,
		kind: int, clearance: float) -> bool:
	if absf(pos.x) > WORLD_HALF - PLACE_MARGIN or absf(pos.y) > WORLD_HALF - PLACE_MARGIN:
		return false
	for i in placed.size():
		var need := maxf(MIN_SITE_DISTANCE, clearance + reach[i] + 15.0)
		if placed[i].distance_squared_to(pos) < need * need:
			return false
	if _river_distance(pos) < clearance + 25.0:
		return false
	# Only coastal fortifications belong on the eastern strip.
	if kind != SITE_BUNKER and pos.x > 1480.0:
		return false
	# Nothing but ruins stands in the middle of the marshes.
	if kind != SITE_RUIN and _marsh_score(pos) > 0.45:
		return false
	return true


func _relax(pos: Vector2, placed: PackedVector2Array, reach: PackedFloat32Array,
		clearance: float) -> Vector2:
	var out := pos
	var river := _river_closest(out)
	var river_need := clearance + 25.0
	var rd := river.distance_to(out)
	if rd < river_need and rd > 0.001:
		out = river + (out - river) / rd * river_need
	for i in placed.size():
		var need := maxf(MIN_SITE_DISTANCE, clearance + reach[i] + 15.0)
		var d := placed[i].distance_to(out)
		if d < need and d > 0.001:
			out = placed[i] + (out - placed[i]) / d * (need + 6.0)
	out.x = clampf(out.x, -(WORLD_HALF - PLACE_MARGIN), WORLD_HALF - PLACE_MARGIN)
	out.y = clampf(out.y, -(WORLD_HALF - PLACE_MARGIN), WORLD_HALF - PLACE_MARGIN)
	return out


## Nearest point of the main river to `target_z`, jittered a few samples along
## the course so the bridge is not always at the same spot.
func _river_anchor(target_z: float, rng: RandomNumberGenerator) -> Vector2:
	if rivers.is_empty() or rivers[0].size() < 2:
		return Vector2(0.0, target_z)
	var line := rivers[0]
	var best := 0
	var best_d := INF
	for i in line.size():
		var d := absf(line[i].y - target_z)
		if d < best_d:
			best_d = d
			best = i
	best = clampi(best + rng.randi_range(-3, 3), 1, line.size() - 2)
	return line[best]


## Coarse distance from a point to the river network. Build time only, so a
## plain loop over every polyline is fine.
func _river_distance(pos: Vector2) -> float:
	var best := INF
	for line: PackedVector2Array in rivers:
		for i in line.size() - 1:
			var d2 := _seg_distance2(pos.x, pos.y, line[i].x, line[i].y, line[i + 1].x, line[i + 1].y)
			if d2 < best:
				best = d2
	return sqrt(best)


## Closest river vertex to a point. Build time only.
func _river_closest(pos: Vector2) -> Vector2:
	var best := pos + Vector2(1.0e6, 0.0)
	var best_d := INF
	for line: PackedVector2Array in rivers:
		for p: Vector2 in line:
			var d := p.distance_squared_to(pos)
			if d < best_d:
				best_d = d
				best = p
	return best


## Coarse marsh footprint, used only to keep buildings out of the swamp.
## Heightfield owns the detailed version (same ellipse, plus noise).
func _marsh_score(pos: Vector2) -> float:
	var dx := (pos.x + 1250.0) / 700.0
	var dz := (pos.y - 1250.0) / 560.0
	return 1.0 - smoothstep(0.55, 1.0, sqrt(dx * dx + dz * dz))


func _draw_names(rng: RandomNumberGenerator, count: int) -> PackedStringArray:
	var pool := NAMES.duplicate()
	for i in range(pool.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var tmp := pool[i]
		pool[i] = pool[j]
		pool[j] = tmp
	var out := PackedStringArray()
	for i in count:
		out.append(pool[i % pool.size()])
	return out


## French display name, decorated by kind. Player facing text, so French.
func _decorate_name(kind: int, base: String) -> String:
	match kind:
		SITE_FARM:
			return "Ferme de %s" % base
		SITE_AIRFIELD:
			return "Terrain d'aviation de %s" % base
		SITE_BUNKER:
			return "Blockhaus de %s" % base
		SITE_CAMP:
			return "Camp de %s" % base
		SITE_CROSSROADS:
			return "Carrefour de %s" % base
		SITE_BRIDGE:
			return "Pont de %s" % base
		SITE_RUIN:
			return "Ruines de %s" % base
		SITE_CHURCH_TOWN:
			return base
		_:
			return base

# --- Roads -------------------------------------------------------------------

## Minimum spanning tree over the eight sectors, plus two extra edges to close
## loops, plus one spur per remaining site. Every edge becomes a wandering
## polyline; an edge that would ford the river is routed through a bridge.
func _build_roads(rng: RandomNumberGenerator) -> void:
	roads = []
	var sectors := PackedInt32Array()
	for s: Site in sites:
		if s.is_sector:
			sectors.append(s.id)
	if sectors.size() < 2:
		return
	var edges: Array[Vector2i] = []
	# --- Prim ---
	var in_tree := PackedInt32Array([sectors[0]])
	var pending := PackedInt32Array()
	for i in range(1, sectors.size()):
		pending.append(sectors[i])
	while not pending.is_empty():
		var best_a := -1
		var best_b := -1
		var best_d := INF
		for a: int in in_tree:
			for b: int in pending:
				var d := sites[a].center.distance_squared_to(sites[b].center)
				if d < best_d:
					best_d = d
					best_a = a
					best_b = b
		edges.append(Vector2i(best_a, best_b))
		in_tree.append(best_b)
		var next := PackedInt32Array()
		for b: int in pending:
			if b != best_b:
				next.append(b)
		pending = next
	# --- two extra edges to create loops ---
	var candidates: Array[Vector3] = []
	for i in sectors.size():
		for j in range(i + 1, sectors.size()):
			var a := sectors[i]
			var b := sectors[j]
			if _has_edge(edges, a, b):
				continue
			candidates.append(Vector3(sites[a].center.distance_to(sites[b].center), float(a), float(b)))
	candidates.sort_custom(func(u: Vector3, v: Vector3) -> bool: return u.x < v.x)
	for i in mini(2, candidates.size()):
		edges.append(Vector2i(int(candidates[i].y), int(candidates[i].z)))
	# --- spurs: every other site hangs off the closest connected one ---
	var connected := in_tree.duplicate()
	var rest := PackedInt32Array()
	for s: Site in sites:
		if not s.is_sector:
			rest.append(s.id)
	while not rest.is_empty():
		var best_r := -1
		var best_c := -1
		var best_d2 := INF
		for r: int in rest:
			for c: int in connected:
				var d := sites[r].center.distance_squared_to(sites[c].center)
				if d < best_d2:
					best_d2 = d
					best_r = r
					best_c = c
		edges.append(Vector2i(best_c, best_r))
		connected.append(best_r)
		var next_rest := PackedInt32Array()
		for r: int in rest:
			if r != best_r:
				next_rest.append(r)
		rest = next_rest
	# --- turn every edge into a polyline ---
	for e: Vector2i in edges:
		_add_road(sites[e.x].center, sites[e.y].center, rng)


static func _has_edge(edges: Array[Vector2i], a: int, b: int) -> bool:
	for e: Vector2i in edges:
		if (e.x == a and e.y == b) or (e.x == b and e.y == a):
			return true
	return false


## Adds one road between two sites. A leg that would ford the river is routed
## through the nearest bridge; if the wander itself still manages to cross the
## water somewhere else, the road is redrawn with a tighter amplitude, up to
## four times. Heightfield keeps a safety net in case even that fails.
func _add_road(from: Vector2, to: Vector2, rng: RandomNumberGenerator) -> void:
	var waypoints := PackedVector2Array([from])
	var bridge := _crossing_bridge(from, to)
	if bridge >= 0:
		waypoints.append(sites[bridge].center)
	waypoints.append(to)
	var line := PackedVector2Array()
	for attempt in 4:
		line = _repel_from_river(_compose_road(waypoints, rng, 1.0 - float(attempt) * 0.2))
		if not _fords_river(line):
			break
	if line.size() >= 2:
		roads.append(line)


## Pushes the road out of the river channel wherever it would run along the
## water, then relaxes the result. Points sitting on a bridge are pinned, since
## that is the one place a road is allowed to be above the stream.
func _repel_from_river(line: PackedVector2Array) -> PackedVector2Array:
	var count := line.size()
	if count < 3:
		return line
	var touches := false
	for p: Vector2 in line:
		if _near_river_cell(p):
			touches = true
			break
	if not touches:
		return line
	var out := line.duplicate()
	var pinned := PackedByteArray()
	pinned.resize(count)
	pinned.fill(0)
	pinned[0] = 1
	pinned[count - 1] = 1
	for i in count:
		for s: Site in sites:
			if s.kind == SITE_BRIDGE and s.center.distance_to(out[i]) < s.radius + 45.0:
				pinned[i] = 1
				break
	for iteration in 3:
		var moved := false
		for i in range(1, count - 1):
			if pinned[i] == 1 or not _near_river_cell(out[i]):
				continue
			var near := _river_projection(out[i])
			var away := out[i] - near
			var d := away.length()
			if d >= RIVER_BANK_CLEARANCE:
				continue
			if d < 0.01:
				away = Vector2(1.0, 0.0)
				d = 1.0
			out[i] = near + away / d * RIVER_BANK_CLEARANCE
			moved = true
		# Relax only when something actually moved, otherwise the smoothing pass
		# would iron the wander out of a road that never came near the water.
		if not moved:
			break
		var copy := out.duplicate()
		for i in range(1, count - 1):
			if pinned[i] == 1:
				continue
			out[i] = copy[i - 1] * 0.25 + copy[i] * 0.5 + copy[i + 1] * 0.25
	return out


## Closest point of the river network to `pos`, projected on the segments.
## Build time only.
func _river_projection(pos: Vector2) -> Vector2:
	var best := pos + Vector2(1.0e6, 0.0)
	var best_d := INF
	for line: PackedVector2Array in rivers:
		for i in line.size() - 1:
			var a := line[i]
			var v := line[i + 1] - a
			var len2 := v.length_squared()
			var t := 0.0
			if len2 > 0.000001:
				t = clampf((pos - a).dot(v) / len2, 0.0, 1.0)
			var p := a + v * t
			var d := p.distance_squared_to(pos)
			if d < best_d:
				best_d = d
				best = p
	return best


func _compose_road(waypoints: PackedVector2Array, rng: RandomNumberGenerator,
		amplitude: float) -> PackedVector2Array:
	var line := PackedVector2Array()
	for i in waypoints.size() - 1:
		var leg := _wander(waypoints[i], waypoints[i + 1], rng, amplitude)
		var start := 1 if i > 0 else 0
		for k in range(start, leg.size()):
			line.append(leg[k])
	return line


## True when the polyline crosses the water anywhere else than on a bridge.
func _fords_river(line: PackedVector2Array) -> bool:
	for i in line.size() - 1:
		var a := line[i]
		var b := line[i + 1]
		if not _near_river_cell(a) and not _near_river_cell(b):
			continue
		for river: PackedVector2Array in rivers:
			for k in river.size() - 1:
				if not _segments_cross(a, b, river[k], river[k + 1]):
					continue
				var covered := false
				for s: Site in sites:
					if s.kind == SITE_BRIDGE and s.center.distance_to(a) < s.radius + 30.0:
						covered = true
						break
				if not covered:
					return true
	return false


## Index of the bridge site closest to where segment (a, b) crosses the main
## river, or -1 when the segment never crosses it.
func _crossing_bridge(a: Vector2, b: Vector2) -> int:
	if rivers.is_empty():
		return -1
	var crossed := false
	var point := Vector2.ZERO
	var line := rivers[0]
	for i in line.size() - 1:
		if _segments_cross(a, b, line[i], line[i + 1]):
			crossed = true
			point = line[i]
			break
	if not crossed:
		return -1
	var best := -1
	var best_d := INF
	for s: Site in sites:
		if s.kind != SITE_BRIDGE:
			continue
		var d := s.center.distance_squared_to(point)
		if d < best_d:
			best_d = d
			best = s.id
	return best


static func _segments_cross(p1: Vector2, p2: Vector2, p3: Vector2, p4: Vector2) -> bool:
	var r := p2 - p1
	var s := p4 - p3
	var denom := r.cross(s)
	if absf(denom) < 0.000001:
		return false
	var t := (p3 - p1).cross(s) / denom
	var u := (p3 - p1).cross(r) / denom
	return t >= 0.0 and t <= 1.0 and u >= 0.0 and u <= 1.0


## A road leg: never a straight line. Two sine harmonics with random phases
## give a smooth wander whose amplitude vanishes at both ends, so legs join
## cleanly at a village or a bridge.
func _wander(from: Vector2, to: Vector2, rng: RandomNumberGenerator,
		amplitude: float = 1.0) -> PackedVector2Array:
	var out := PackedVector2Array()
	var span := from.distance_to(to)
	if span < 1.0:
		out.append(from)
		out.append(to)
		return out
	var dir := (to - from) / span
	var perp := Vector2(-dir.y, dir.x)
	var amp := minf(72.0, span * 0.11) * maxf(amplitude, 0.05)
	var a1 := rng.randf_range(0.45, 1.0) * amp
	var a2 := rng.randf_range(-0.5, 0.5) * amp
	var p1 := rng.randf() * TAU
	var p2 := rng.randf() * TAU
	var steps := maxi(4, int(span / 15.0))
	for k in steps + 1:
		var t := float(k) / float(steps)
		var envelope := sin(t * PI)
		var offset := envelope * (a1 * sin(t * 2.3 + p1) + a2 * sin(t * 5.1 + p2))
		out.append(from + dir * (span * t) + perp * offset)
	return out

# --- Spawn -------------------------------------------------------------------

## Inside the footprint of the allied village, well within its flattened core.
func _pick_spawn(rng: RandomNumberGenerator) -> void:
	if sites.is_empty():
		_spawn = Vector2.ZERO
		return
	var s := sites[0]
	var angle := rng.randf() * TAU
	_spawn = s.center + Vector2(cos(angle), sin(angle)) * (s.radius * 0.42)

# --- Acceleration grid -------------------------------------------------------

## Bins every road segment, river segment and site footprint into 128 m cells.
## Built once, read only afterwards, therefore thread safe.
func _build_grids() -> void:
	_cell_roads = []
	_cell_rivers = []
	_cell_sites = []
	_cell_roads.resize(GRID * GRID)
	_cell_rivers.resize(GRID * GRID)
	_cell_sites.resize(GRID * GRID)
	for i in GRID * GRID:
		_cell_roads[i] = PackedInt32Array()
		_cell_rivers[i] = PackedInt32Array()
		_cell_sites[i] = PackedInt32Array()
	_road_seg = PackedFloat32Array()
	for line: PackedVector2Array in roads:
		for i in line.size() - 1:
			var index := _road_seg.size() / 4
			_road_seg.append(line[i].x)
			_road_seg.append(line[i].y)
			_road_seg.append(line[i + 1].x)
			_road_seg.append(line[i + 1].y)
			_bin_segment(_cell_roads, index, line[i], line[i + 1], ROAD_HALF_WIDTH + ROAD_FADE)
	_river_seg = PackedFloat32Array()
	for line: PackedVector2Array in rivers:
		for i in line.size() - 1:
			var index := _river_seg.size() / 4
			_river_seg.append(line[i].x)
			_river_seg.append(line[i].y)
			_river_seg.append(line[i + 1].x)
			_river_seg.append(line[i + 1].y)
			_bin_segment(_cell_rivers, index, line[i], line[i + 1], RIVER_HALF_WIDTH + RIVER_FADE)
	for s: Site in sites:
		var reach := s.radius * SITE_OUTER
		_bin_segment(_cell_sites, s.id, s.center, s.center, reach)


static func _bin_segment(cells: Array[PackedInt32Array], index: int, a: Vector2, b: Vector2,
		pad: float) -> void:
	var x0 := _cell_axis(minf(a.x, b.x) - pad)
	var x1 := _cell_axis(maxf(a.x, b.x) + pad)
	var z0 := _cell_axis(minf(a.y, b.y) - pad)
	var z1 := _cell_axis(maxf(a.y, b.y) + pad)
	for cz in range(z0, z1 + 1):
		for cx in range(x0, x1 + 1):
			cells[cz * GRID + cx].append(index)


static func _cell_axis(v: float) -> int:
	return clampi(floori((v + WORLD_HALF) / CELL), 0, GRID - 1)


static func _cell_index(x: float, z: float) -> int:
	return _cell_axis(z) * GRID + _cell_axis(x)

# --- Maths helpers -----------------------------------------------------------

## Squared distance from (px, pz) to the segment (x1, z1) - (x2, z2).
## No allocation, no branch on Vector2, this is called from the terrain hot path.
static func _seg_distance2(px: float, pz: float, x1: float, z1: float,
		x2: float, z2: float) -> float:
	var vx := x2 - x1
	var vz := z2 - z1
	var wx := px - x1
	var wz := pz - z1
	var len2 := vx * vx + vz * vz
	var t := 0.0
	if len2 > 0.000001:
		t = clampf((wx * vx + wz * vz) / len2, 0.0, 1.0)
	var dx := wx - vx * t
	var dz := wz - vz * t
	return dx * dx + dz * dz


static func _mix_seed(base: int, salt: int) -> int:
	var h := (base ^ (salt * 374761393)) & 0x7FFFFFFF
	h = (h ^ (h >> 13)) * 1274126177
	return h & 0x7FFFFFFF
