## Procedural mesh library of CALL OF WAR. Every shape in the game is built
## here, once, and shared by every instance that needs it.
##
## One exception, added after the fact and quarantined in `CharacterModels`:
## when `assets/models` is installed, `soldier_body()` hands back an imported
## rigged character instead of the box man below. The box man is not dead code,
## it is the fallback the whole file is still written around: delete the folder
## and the game runs unchanged, exactly as it does without `assets/textures`.
##
## Style rules the whole file follows:
##
## - Lowpoly and angular, but never a grey box. A Normandy oak is a tapered
##   trunk plus four offset flattened canopy masses, a pine is stacked cones, a
##   hedge is an irregular slab with a jittered top ridge.
## - Every surface carries its material, taken from `MatLib` so that two props
##   sharing a material can still be batched.
## - Every vertex gets an explicit normal, computed from the primitive itself,
##   except where flat facets are wanted from raw geometry (the hedgerow, whose
##   top ridge is displaced) where `SurfaceTool.generate_normals()` does it.
## - Orientation conventions, relied upon by `Scatter`:
##     * linear props (hedge, fence, telegraph crossarm, wreck) run along +X;
##     * a soldier faces -Z, so its own right hand side is +X;
##     * a weapon points down -Z with its grip at the origin.
##
## Threading: the cache is a plain Dictionary, so `prop_mesh`, `box`, `cylinder`,
## `sphere`, `soldier_body` and `weapon_model` are MAIN THREAD ONLY. Terrain
## workers must stick to `Scatter`, which never touches this file.
class_name Meshes
extends RefCounted

# --- Mirrors of other modules ----------------------------------------------
#
# These mirror `War` and `WeaponDefs` exactly. They are duplicated on purpose:
# `War` is an autoload (unavailable under `--script`, see CONTRACTS section 6)
# and mirroring `WeaponDefs` keeps this file compiling on its own while other
# agents are still writing theirs.

const _F_ALLIED := 0
const _F_AXIS := 1
const _F_NEUTRAL := 2

const _W_M1_GARAND := 0
const _W_THOMPSON := 1
const _W_SPRINGFIELD := 2
const _W_M1911 := 3
const _W_MP40 := 4
const _W_KAR98K := 5
const _W_MG42 := 6
const _W_GRENADE := 7
# Added in v2. Appended, never renumbered: weapon ids are written into saves.
const _W_LUGER := 8
const _W_KAR98K_SCOPED := 9

# --- Prop kind mirror (Scatter) --------------------------------------------

const _P_TREE_OAK := 0
const _P_TREE_PINE := 1
const _P_TREE_APPLE := 2
const _P_BUSH := 3
const _P_HEDGE := 4
const _P_ROCK := 5
const _P_GRASS_TUFT := 6
const _P_WHEAT := 7
const _P_FENCE := 8
const _P_WRECK := 9
const _P_CRATER := 10
const _P_SANDBAG := 11
const _P_POLE := 12
const _P_HAYSTACK := 13

## How many distinct shapes each prop kind offers. `variant` wraps around it.
const _VARIANTS: PackedInt32Array = [3, 3, 2, 3, 3, 4, 2, 2, 2, 2, 2, 2, 1, 2]

## Linear prop lengths, kept in sync with the sampling steps in `Scatter`.
const HEDGE_LENGTH := 4.0
const FENCE_LENGTH := 3.2

static var _cache: Dictionary = {}


# --- Public API ------------------------------------------------------------

## Cached prop meshes, one per Scatter kind. Returns an ArrayMesh whose
## surfaces already carry their material. Never returns null: an unknown kind
## falls back to a small rock so a bad id shows up in game instead of crashing.
static func prop_mesh(kind: int, variant: int = 0) -> Mesh:
	var k: int = kind
	if k < 0 or k >= _VARIANTS.size():
		push_warning("Meshes.prop_mesh: unknown kind %d" % kind)
		k = _P_ROCK
	var v: int = absi(variant) % maxi(_VARIANTS[k], 1)
	var key: String = "prop:%d:%d" % [k, v]
	if _cache.has(key):
		return _cache[key]

	var mesh: Mesh
	match k:
		_P_TREE_OAK:
			mesh = _oak(v)
		_P_TREE_PINE:
			mesh = _pine(v)
		_P_TREE_APPLE:
			mesh = _apple(v)
		_P_BUSH:
			mesh = _bush(v)
		_P_HEDGE:
			mesh = _hedge(v)
		_P_ROCK:
			mesh = _rock(v)
		_P_GRASS_TUFT:
			mesh = _grass_tuft(v)
		_P_WHEAT:
			mesh = _wheat_clump(v)
		_P_FENCE:
			mesh = _fence(v)
		_P_WRECK:
			mesh = _wreck(v)
		_P_CRATER:
			mesh = _crater(v)
		_P_SANDBAG:
			mesh = _sandbag_stack(v)
		_P_POLE:
			mesh = _telegraph_pole(v)
		_P_HAYSTACK:
			mesh = _haystack(v)
		_:
			mesh = _rock(0)
	_cache[key] = mesh
	return mesh


## Simple building blocks, cached by their arguments. Centred on the origin.
static func box(size: Vector3, material_key: String) -> Mesh:
	var key: String = "box:%.3f,%.3f,%.3f:%s" % [size.x, size.y, size.z, material_key]
	if _cache.has(key):
		return _cache[key]
	var b := _Build.new()
	b.box(material_key, Transform3D.IDENTITY, size, Color.WHITE)
	var mesh: ArrayMesh = b.commit()
	_cache[key] = mesh
	return mesh


## Cylinder standing on Y, centred on the origin.
static func cylinder(radius: float, height: float, sides: int,
		material_key: String) -> Mesh:
	var n: int = clampi(sides, 3, 64)
	var key: String = "cyl:%.3f,%.3f,%d:%s" % [radius, height, n, material_key]
	if _cache.has(key):
		return _cache[key]
	var b := _Build.new()
	var base := Transform3D(Basis.IDENTITY, Vector3(0.0, -height * 0.5, 0.0))
	b.tube(material_key, base, radius, radius, height, n, Color.WHITE, true, true)
	var mesh: ArrayMesh = b.commit()
	_cache[key] = mesh
	return mesh


static func sphere(radius: float, material_key: String) -> Mesh:
	var key: String = "sph:%.3f:%s" % [radius, material_key]
	if _cache.has(key):
		return _cache[key]
	var b := _Build.new()
	b.ellipsoid(material_key, Vector3.ZERO, Vector3(radius, radius, radius),
			8, 14, Color.WHITE)
	var mesh: ArrayMesh = b.commit()
	_cache[key] = mesh
	return mesh


## A humanoid body. `faction` is War.ALLIED / War.AXIS / War.NEUTRAL.
##
## Two shapes can come back, and callers must cope with both:
##
## - When `assets/models` holds a model for `species`, this returns the imported
##   rigged character from `CharacterModels`: a skeleton driven by an
##   AnimationPlayer, with only "Weapon" reachable by name.
## - Otherwise it returns the box soldier built below, whose children are named
##   exactly "Hips","Torso","Head","Helmet","ArmL","ArmR","LegL","LegR","Weapon".
##   Those nine parts are DIRECT children, each a Node3D sitting on its own pivot
##   (shoulder for the arms, hip for the legs, neck for the head) with the
##   geometry hanging off it, so the AI only ever writes a local rotation.
##
## What both guarantee, and what `Soldier` relies on: feet on y = 0, a total
## height of about 1.80 m, facing -Z, and a "Weapon" node at the firing hand.
## `Soldier` tells the two apart by asking `CharacterAnim.attach()` for a driver.
static func soldier_body(faction: int, variant: int,
		species: int = CharacterModels.SPECIES_SOLDIER) -> Node3D:
	var f: int = faction
	if f != _F_AXIS and f != _F_NEUTRAL:
		f = _F_ALLIED
	var v: int = absi(variant) % 3

	var rigged := CharacterModels.build(species, f, v,
			weapon_model(_default_weapon(f, v)))
	if rigged != null:
		return rigged

	var root := Node3D.new()
	root.name = "SoldierBody"

	_attach(root, "Hips", Vector3(0.0, HIP_Y, 0.0), _soldier_part(f, v, "hips"))
	_attach(root, "Torso", Vector3(0.0, WAIST_Y, 0.0), _soldier_part(f, v, "torso"))
	_attach(root, "Head", Vector3(0.0, NECK_Y, 0.0), _soldier_part(f, v, "head"))
	_attach(root, "Helmet", Vector3(0.0, HELMET_Y, 0.0), _soldier_part(f, v, "helmet"))
	_attach(root, "ArmL", Vector3(-SHOULDER_X, SHOULDER_Y, 0.0),
			_soldier_part(f, v, "arm"))
	_attach(root, "ArmR", Vector3(SHOULDER_X, SHOULDER_Y, 0.0),
			_soldier_part(f, v, "arm"))
	_attach(root, "LegL", Vector3(-HIP_X, HIP_Y, 0.0), _soldier_part(f, v, "leg"))
	_attach(root, "LegR", Vector3(HIP_X, HIP_Y, 0.0), _soldier_part(f, v, "leg"))

	# The weapon rides in the right hand, muzzle down -Z, angled slightly in.
	var weapon := Node3D.new()
	weapon.name = "Weapon"
	weapon.position = Vector3(0.19, 1.19, -0.20)
	weapon.rotation = Vector3(0.0, 0.10, -0.06)
	var wm := MeshInstance3D.new()
	wm.name = "WeaponMesh"
	wm.mesh = weapon_model(_default_weapon(f, v))
	weapon.add_child(wm)
	root.add_child(weapon)
	return root


## Weapon world model (dropped or carried by AI), by weapon id from WeaponDefs.
## Grip at the origin, barrel down -Z, sights up +Y. Never returns null: an
## unknown id yields an empty mesh so a MeshInstance3D can take it safely.
static func weapon_model(weapon_id: int) -> Mesh:
	var key: String = "weapon:%d" % weapon_id
	if _cache.has(key):
		return _cache[key]
	var mesh: Mesh
	match weapon_id:
		_W_M1_GARAND:
			mesh = _rifle(0.45, 0.055, true, false)
		_W_KAR98K:
			mesh = _rifle(0.43, 0.052, false, false)
		_W_KAR98K_SCOPED:
			# Same rifle as above, scope flag on: one geometry, two weapons.
			mesh = _rifle(0.43, 0.052, false, true)
		_W_SPRINGFIELD:
			mesh = _rifle(0.44, 0.052, false, true)
		_W_THOMPSON:
			mesh = _thompson()
		_W_MP40:
			mesh = _mp40()
		_W_MG42:
			mesh = _mg42()
		_W_M1911:
			mesh = _pistol()
		_W_LUGER:
			mesh = _luger()
		_W_GRENADE:
			mesh = _grenade()
		_:
			mesh = ArrayMesh.new()
	_cache[key] = mesh
	return mesh


static func clear_cache() -> void:
	_cache.clear()


# --- Soldier skeleton constants --------------------------------------------

const HIP_Y := 0.90
const HIP_X := 0.105
const WAIST_Y := 1.00
const NECK_Y := 1.52
const HELMET_Y := 1.62
const SHOULDER_Y := 1.45
const SHOULDER_X := 0.235


# --- Trees -----------------------------------------------------------------

## Normandy oak: a slightly conical trunk, three raised limbs, and four to five
## offset flattened canopy masses. Never a single ball of leaves.
static func _oak(variant: int) -> ArrayMesh:
	var rng := _rng(101 + variant)
	var b := _Build.new()
	var lean := Vector3(rng.randf_range(-0.16, 0.16), 0.0, rng.randf_range(-0.16, 0.16))
	var trunk_h: float = 3.0 + rng.randf_range(-0.25, 0.7)
	var r0: float = 0.44 + rng.randf_range(-0.05, 0.07)

	# Flared root collar, then the trunk proper.
	b.tube("bark", Transform3D.IDENTITY, r0 * 1.5, r0 * 1.05, 0.30, 8,
			Color.WHITE, false, false)
	b.limb("bark", Vector3.ZERO, Vector3(0, trunk_h, 0) + lean, r0 * 1.05,
			r0 * 0.56, 8, Color.WHITE)

	# Six masses instead of four, each one wider and pushed out less far. The old
	# spread reached 1.6 m with a 1.35 m radius, so the outer blobs sat clear of
	# their neighbours and the crown was a ring of separate balls with sky
	# between them. Overlap is what makes a canopy read as one mass.
	var blobs: int = 6 + (variant % 2)
	var crown := Vector3(0, trunk_h, 0) + lean
	for i in blobs:
		var ang: float = TAU * float(i) / float(blobs) + rng.randf_range(-0.3, 0.3)
		var spread: float = 0.30 + rng.randf_range(0.0, 0.95)
		var lift: float = 0.50 + rng.randf_range(0.0, 1.55)
		var centre := crown + Vector3(cos(ang) * spread, lift, sin(ang) * spread)
		# Limbs reaching the outer masses: what makes it read as an oak.
		if spread > 0.7:
			b.limb("bark", crown + Vector3(0, -0.25, 0),
					centre + Vector3(0, -0.25, 0), 0.15, 0.07, 5, Color.WHITE)
		var rw: float = 1.65 + rng.randf_range(-0.15, 0.55)
		var rh: float = rw * rng.randf_range(0.58, 0.78)
		# Six rings by ten segments: at four by eight the facets were coarse
		# enough to read as folded paper rather than as a rounded crown.
		b.ellipsoid("canopy", centre, Vector3(rw, rh, rw * 0.94), 6, 10,
				_leaf_shade(rng))
	# A low mass filling the fork so the canopy does not float.
	b.ellipsoid("canopy", crown + Vector3(0, 0.55, 0), Vector3(1.95, 1.15, 1.95),
			6, 10, _leaf_shade(rng))
	return b.commit()


## Pine: a bare lower trunk with stacked, shrinking cone skirts.
static func _pine(variant: int) -> ArrayMesh:
	var rng := _rng(211 + variant)
	var b := _Build.new()
	var height: float = 8.0 + rng.randf_range(-0.8, 1.4)
	b.tube("bark", Transform3D.IDENTITY, 0.36, 0.30, 0.35, 7, Color.WHITE, false, false)
	b.tube("bark", Transform3D(Basis.IDENTITY, Vector3(0, 0.35, 0)), 0.30, 0.11,
			height - 0.35, 7, Color.WHITE, false, true)

	var tiers: int = 5 + (variant % 2)
	var base_y: float = height * 0.19
	var span: float = (height * 0.92 - base_y) / float(tiers)
	for i in tiers:
		var t: float = float(i) / float(tiers)
		var y: float = base_y + float(i) * span
		var radius: float = (2.15 - t * 1.55) * rng.randf_range(0.9, 1.08)
		var skirt: float = span * 1.85
		var off := Vector3(rng.randf_range(-0.08, 0.08), y, rng.randf_range(-0.08, 0.08))
		b.tube("canopy", Transform3D(Basis.IDENTITY, off), radius, radius * 0.12,
				skirt, 9, _leaf_shade(rng), true, false)
	# Sharp top spire.
	b.tube("canopy", Transform3D(Basis.IDENTITY, Vector3(0, height * 0.88, 0)),
			0.42, 0.0, height * 0.16, 8, _leaf_shade(rng), false, false)
	return b.commit()


## Apple tree: short, leaning trunk and a wide low crown. An orchard tree is
## pruned to be picked from the ground, so it is much broader than it is tall.
static func _apple(variant: int) -> ArrayMesh:
	var rng := _rng(307 + variant)
	var b := _Build.new()
	var lean := Vector3(rng.randf_range(-0.14, 0.14), 0.0, rng.randf_range(-0.14, 0.14))
	var trunk_h: float = 1.10 + rng.randf_range(-0.1, 0.25)
	b.tube("bark", Transform3D.IDENTITY, 0.26, 0.19, 0.18, 7, Color.WHITE, false, false)
	b.limb("bark", Vector3(0, 0.15, 0), Vector3(0, trunk_h, 0) + lean, 0.19, 0.15,
			7, Color.WHITE)

	var fork := Vector3(0, trunk_h, 0) + lean
	var blobs: int = 5 + (variant % 2)
	for i in blobs:
		var ang: float = TAU * float(i) / float(blobs) + rng.randf_range(-0.25, 0.25)
		var spread: float = 0.45 + rng.randf_range(0.0, 0.42)
		var centre := fork + Vector3(cos(ang) * spread,
				0.40 + rng.randf_range(0.0, 0.42), sin(ang) * spread)
		b.limb("bark", fork, centre + Vector3(0, -0.2, 0), 0.11, 0.055, 5, Color.WHITE)
		var rw: float = 1.10 + rng.randf_range(-0.10, 0.30)
		b.ellipsoid("canopy", centre, Vector3(rw, rw * 0.66, rw * 0.92), 6, 10,
				_leaf_shade(rng))
	b.ellipsoid("canopy", fork + Vector3(0, 0.42, 0), Vector3(1.35, 0.72, 1.30),
			6, 10, _leaf_shade(rng))
	return b.commit()


static func _bush(variant: int) -> ArrayMesh:
	var rng := _rng(401 + variant)
	var b := _Build.new()
	var blobs: int = 4 + (variant % 2)
	for i in blobs:
		var ang: float = TAU * float(i) / float(blobs) + rng.randf_range(-0.4, 0.4)
		var spread: float = 0.14 + rng.randf_range(0.0, 0.20)
		var rw: float = 0.52 + rng.randf_range(-0.05, 0.16)
		var centre := Vector3(cos(ang) * spread, rw * 0.72 + rng.randf_range(-0.04, 0.10),
				sin(ang) * spread)
		b.ellipsoid("canopy", centre, Vector3(rw, rw * 0.82, rw * 0.95), 6, 10,
				_leaf_shade(rng))
	# A hint of woody stems at the base.
	b.tube("bark", Transform3D.IDENTITY, 0.07, 0.04, 0.22, 5, Color.WHITE, false, false)
	return b.commit()


# --- Hedgerow --------------------------------------------------------------

## One 4 m bocage segment, running along +X. Built as a slab whose TOP ridge
## vertices are displaced, so no two segments read the same, sitting on the
## earth bank that a real Normandy hedge is planted on.
##
## The foliage surface is the one place `generate_normals()` earns its keep:
## the ridge is irregular enough that hand computed normals would be wrong.
static func _hedge(variant: int) -> ArrayMesh:
	var rng := _rng(503 + variant)
	var mesh := ArrayMesh.new()

	var segments := 10
	var half_len: float = HEDGE_LENGTH * 0.5
	var base_half: float = 0.76
	var height: float = 1.72 + rng.randf_range(-0.12, 0.26)

	var top: Array[Vector3] = []      # ridge centre per station
	var top_half: PackedFloat32Array = PackedFloat32Array()
	for i in range(segments + 1):
		var t: float = float(i) / float(segments)
		var x: float = -half_len + HEDGE_LENGTH * t
		# Ends taper down a touch so two segments overlap without a hard step.
		var edge: float = minf(1.0, minf(t, 1.0 - t) * 5.0 + 0.55)
		var h: float = height * edge + rng.randf_range(-0.20, 0.26)
		var z: float = rng.randf_range(-0.10, 0.10)
		top.append(Vector3(x, h, z))
		top_half.append(base_half * rng.randf_range(0.62, 0.86))

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in segments:
		var a := top[i]
		var c := top[i + 1]
		var wa: float = top_half[i]
		var wc: float = top_half[i + 1]
		var xa: float = a.x
		var xc: float = c.x
		var bl_a := Vector3(xa, 0.0, -base_half)
		var bl_c := Vector3(xc, 0.0, -base_half)
		var br_a := Vector3(xa, 0.0, base_half)
		var br_c := Vector3(xc, 0.0, base_half)
		var tl_a := Vector3(xa, a.y, a.z - wa)
		var tl_c := Vector3(xc, c.y, c.z - wc)
		var tr_a := Vector3(xa, a.y, a.z + wa)
		var tr_c := Vector3(xc, c.y, c.z + wc)
		# Left wall, right wall, ridge. Winding chosen so the generated normals
		# point outwards (the foliage material is cull disabled anyway, but the
		# lighting has to be right).
		_raw_quad(st, bl_a, tl_a, tl_c, bl_c)
		_raw_quad(st, br_a, br_c, tr_c, tr_a)
		_raw_quad(st, tl_a, tr_a, tr_c, tl_c)
	# End caps.
	_raw_quad(st, Vector3(-half_len, 0.0, -base_half),
			Vector3(-half_len, 0.0, base_half),
			Vector3(-half_len, top[0].y, top[0].z + top_half[0]),
			Vector3(-half_len, top[0].y, top[0].z - top_half[0]))
	var last: int = segments
	_raw_quad(st, Vector3(half_len, 0.0, base_half),
			Vector3(half_len, 0.0, -base_half),
			Vector3(half_len, top[last].y, top[last].z - top_half[last]),
			Vector3(half_len, top[last].y, top[last].z + top_half[last]))
	st.generate_normals()
	st.set_material(MatLib.get_material("canopy"))
	st.commit(mesh)

	# The earth bank underneath, vertex coloured like the surrounding dirt.
	var bank := _Build.new()
	bank.trapezoid("terrain", Vector3(0, 0.0, 0), HEDGE_LENGTH * 1.02, 0.42,
			base_half * 2.25, base_half * 1.5, Palette.MUD)
	var bank_mesh: ArrayMesh = bank.commit()
	for s in bank_mesh.get_surface_count():
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,
				bank_mesh.surface_get_arrays(s))
		mesh.surface_set_material(mesh.get_surface_count() - 1,
				MatLib.terrain_material())
	return mesh


# --- Rock ------------------------------------------------------------------

## An icosphere, subdivided once and displaced: a chunky, faceted boulder.
static func _rock(variant: int) -> ArrayMesh:
	var rng := _rng(601 + variant)
	var b := _Build.new()
	var squash := Vector3(1.0, rng.randf_range(0.52, 0.82), rng.randf_range(0.78, 1.05))
	b.rock("stone", Vector3(0, 0.34 * squash.y, 0), 0.72, squash,
			1 if variant < 2 else 0, 619 + variant * 7, Color.WHITE)
	return b.commit()


# --- Ground cover ----------------------------------------------------------

static func _grass_tuft(variant: int) -> ArrayMesh:
	var rng := _rng(701 + variant)
	var b := _Build.new()
	var blades: int = 6 + variant
	for i in blades:
		var yaw: float = TAU * float(i) / float(blades) + rng.randf_range(-0.3, 0.3)
		var h: float = 0.42 + rng.randf_range(0.0, 0.26)
		var w: float = 0.115 + rng.randf_range(-0.025, 0.05)
		var lean := Vector3(rng.randf_range(-0.12, 0.12), 0.0, rng.randf_range(-0.12, 0.12))
		b.blade("blade", Vector3(rng.randf_range(-0.16, 0.16), 0.0,
				rng.randf_range(-0.16, 0.16)), w, h, yaw, lean, Color.WHITE)
	return b.commit()


static func _wheat_clump(variant: int) -> ArrayMesh:
	var rng := _rng(809 + variant)
	var b := _Build.new()
	# A standing crop has to close up, not stand as separate tufts. One instance
	# is planted every 1.5 m by the scatter, so a clump has to cover roughly that
	# much ground on its own: more stalks, spread wider. The cost is geometry
	# inside a MultiMesh, which is far cheaper than more instances.
	var blades: int = 9 + variant * 2
	for i in blades:
		var yaw: float = TAU * float(i) / float(blades) + rng.randf_range(-0.35, 0.35)
		var h: float = 0.92 + rng.randf_range(0.0, 0.28)
		var w: float = 0.085 + rng.randf_range(-0.02, 0.035)
		# Ripe wheat leans with the wind, all in roughly the same direction.
		var lean := Vector3(0.10 + rng.randf_range(-0.05, 0.09), 0.0,
				rng.randf_range(-0.06, 0.06))
		b.blade("wheat", Vector3(rng.randf_range(-0.34, 0.34), 0.0,
				rng.randf_range(-0.34, 0.34)), w, h, yaw, lean, Color.WHITE)
	return b.commit()


# --- Built props -----------------------------------------------------------

## Post and rail fence, one 3.2 m bay running along +X.
static func _fence(variant: int) -> ArrayMesh:
	var rng := _rng(907 + variant)
	var b := _Build.new()
	var half: float = FENCE_LENGTH * 0.5
	for side in 2:
		var x: float = -half if side == 0 else half
		var tilt: float = rng.randf_range(-0.07, 0.07)
		var post := Transform3D(Basis(Vector3(0, 0, 1), tilt), Vector3(x, 0.62, 0))
		b.box("wood", post, Vector3(0.10, 1.24, 0.10), Color.WHITE)
	var rails: int = 2 + (variant % 2)
	for i in rails:
		var y: float = 0.42 + float(i) * (0.66 / maxf(float(rails - 1), 1.0)) \
				+ rng.randf_range(-0.03, 0.03)
		var sag: float = rng.randf_range(-0.04, 0.01)
		var rail := Transform3D(Basis(Vector3(0, 0, 1), sag),
				Vector3(0, y, rng.randf_range(-0.02, 0.02)))
		b.box("wood", rail, Vector3(FENCE_LENGTH, 0.075, 0.045), Color.WHITE)
	return b.commit()


## Burnt out vehicle. Variant 0 is a supply truck, variant 1 a tank hull with
## its turret knocked askew. Both run along +X and sit on the ground.
static func _wreck(variant: int) -> ArrayMesh:
	var rng := _rng(1009 + variant)
	var b := _Build.new()
	if variant == 0:
		# Chassis and burnt cargo bed.
		b.box("rust", Transform3D(Basis.IDENTITY, Vector3(0.15, 0.78, 0)),
				Vector3(4.5, 0.34, 1.85), Color.WHITE)
		b.box("rust", Transform3D(Basis(Vector3(0, 0, 1), 0.05),
				Vector3(-1.55, 1.35, 0)), Vector3(1.4, 1.05, 1.80), Color.WHITE)
		# Bed side boards, one of them torn off.
		b.box("wood", Transform3D(Basis.IDENTITY, Vector3(0.75, 1.22, -0.86)),
				Vector3(3.0, 0.60, 0.10), Color.WHITE)
		b.box("wood", Transform3D(Basis(Vector3(1, 0, 0), 0.55),
				Vector3(0.9, 1.10, 0.90)), Vector3(2.2, 0.55, 0.10), Color.WHITE)
		b.box("rust", Transform3D(Basis.IDENTITY, Vector3(2.28, 1.10, 0)),
				Vector3(0.16, 0.9, 1.7), Color.WHITE)
		# Wheels: three left, one blown off, so it leans.
		var spots: Array[Vector3] = [
			Vector3(-1.5, 0.48, -0.92), Vector3(-1.5, 0.48, 0.92),
			Vector3(1.5, 0.48, -0.92),
		]
		for p in spots:
			var w := Transform3D(Basis(Vector3(0, 0, 1), PI * 0.5),
					p - Vector3(0, 0, 0.14))
			b.tube("metal", w, 0.48, 0.48, 0.28, 10, Color.WHITE, true, true)
	else:
		# Tank hull.
		b.box("rust", Transform3D(Basis(Vector3(0, 0, 1), 0.04),
				Vector3(0, 1.05, 0)), Vector3(5.0, 0.85, 2.35), Color.WHITE)
		b.box("rust", Transform3D(Basis.IDENTITY, Vector3(0, 1.62, 0)),
				Vector3(3.6, 0.35, 2.0), Color.WHITE)
		for side in 2:
			var z: float = -1.32 if side == 0 else 1.32
			b.box("metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.62, z)),
					Vector3(5.3, 0.72, 0.42), Color.WHITE)
			for i in 5:
				var wx: float = -2.0 + float(i) * 1.0
				var road := Transform3D(Basis(Vector3(0, 0, 1), PI * 0.5),
						Vector3(wx, 0.52, z - (0.16 if side == 0 else -0.16)))
				b.tube("metal", road, 0.34, 0.34, 0.24, 8, Color.WHITE, true, true)
		# Turret, blown round and tipped.
		var yaw: float = rng.randf_range(0.7, 2.2)
		var turret := Transform3D(Basis(Vector3(0, 1, 0), yaw)
				* Basis(Vector3(1, 0, 0), 0.13), Vector3(-0.25, 2.15, 0))
		b.box("rust", turret, Vector3(2.05, 0.72, 1.75), Color.WHITE)
		var gun_dir := (Basis(Vector3(0, 1, 0), yaw) * Vector3(-1, 0.12, 0)).normalized()
		b.limb("metal", Vector3(-0.25, 2.15, 0),
				Vector3(-0.25, 2.15, 0) + gun_dir * 2.5, 0.11, 0.075, 8, Color.WHITE)
	return b.commit()


## Shell crater: a radial bowl with a raised lip, vertex coloured on the
## terrain material so it blends with the ground it is dropped on.
static func _crater(variant: int) -> ArrayMesh:
	var rng := _rng(1103 + variant)
	var b := _Build.new()
	var radius: float = 2.5 + float(variant) * 0.5
	# (radius factor, height, colour blend towards mud)
	var profile: Array[Vector3] = [
		Vector3(0.00, -0.80, 1.0),
		Vector3(0.30, -0.70, 1.0),
		Vector3(0.58, -0.42, 0.85),
		Vector3(0.82, -0.06, 0.55),
		Vector3(1.00, 0.22, 0.35),
		Vector3(1.22, 0.02, 0.0),
	]
	b.bowl("terrain", radius, profile, 16, Palette.MUD, Palette.DIRT, rng)
	return b.commit()


## A short arc of sandbags, three courses high.
static func _sandbag_stack(variant: int) -> ArrayMesh:
	var rng := _rng(1201 + variant)
	var b := _Build.new()
	var arc: float = 2.4 if variant == 0 else 3.1
	var radius: float = 1.15
	var courses := 3
	for c in courses:
		var y: float = 0.14 + float(c) * 0.27
		var span: float = arc * (1.0 - float(c) * 0.09)
		var count: int = 7 - c
		for i in count:
			var t: float = (float(i) + 0.5) / float(count) - 0.5
			var ang: float = t * span + (0.14 if (c % 2) == 1 else 0.0)
			var pos := Vector3(cos(ang) * radius, y, sin(ang) * radius)
			var basis := Basis(Vector3(0, 1, 0), -ang + rng.randf_range(-0.12, 0.12))
			b.box("sandbag", Transform3D(basis, pos),
					Vector3(0.26, 0.24, 0.50) * rng.randf_range(0.93, 1.08),
					Color.WHITE)
	return b.commit()


## Telegraph pole: shaft, two crossarms along +X and their insulators.
static func _telegraph_pole(variant: int) -> ArrayMesh:
	var b := _Build.new()
	var height := 7.6
	b.tube("wood", Transform3D.IDENTITY, 0.16, 0.10, height, 7, Color.WHITE,
			false, true)
	var arms: Array[float] = [height - 0.45, height - 1.15]
	for a in arms.size():
		var y: float = arms[a]
		var span: float = 1.70 - float(a) * 0.25
		b.box("wood", Transform3D(Basis.IDENTITY, Vector3(0, y, 0)),
				Vector3(span, 0.09, 0.11), Color.WHITE)
		var pegs := 4
		for i in pegs:
			var x: float = (float(i) / float(pegs - 1) - 0.5) * (span - 0.18)
			b.tube("glass", Transform3D(Basis.IDENTITY, Vector3(x, y + 0.045, 0)),
					0.045, 0.038, 0.11, 6, Color.WHITE, false, true)
		# Diagonal brace under the arm.
		b.limb("wood", Vector3(-span * 0.32, y - 0.03, 0), Vector3(0, y - 0.55, 0),
				0.035, 0.035, 4, Color.WHITE)
		b.limb("wood", Vector3(span * 0.32, y - 0.03, 0), Vector3(0, y - 0.55, 0),
				0.035, 0.035, 4, Color.WHITE)
	return b.commit()


## Round haystack. Uses the sandbag (hessian) material: it is the only shared
## material in MatLib with the right straw tone, and hay is not worth a key of
## its own.
static func _haystack(variant: int) -> ArrayMesh:
	var rng := _rng(1301 + variant)
	var b := _Build.new()
	var r: float = 1.55 + rng.randf_range(-0.1, 0.25)
	var body: float = 1.25 + rng.randf_range(-0.1, 0.25)
	# Nine sides, so the silhouette is lumpy rather than machined.
	b.tube("sandbag", Transform3D.IDENTITY, r * 0.88, r, body, 9, Color.WHITE,
			false, false)
	b.tube("sandbag", Transform3D(Basis.IDENTITY, Vector3(0, body, 0)), r * 1.04,
			0.0, 1.25 + rng.randf_range(-0.1, 0.3), 9, Color.WHITE, false, false)
	if variant == 1:
		# A tarpaulin thrown over one flank.
		b.box("cloth", Transform3D(Basis(Vector3(0, 0, 1), 0.25),
				Vector3(r * 0.5, body * 0.8, 0)), Vector3(0.06, 1.0, 1.4), Color.WHITE)
	return b.commit()


# --- Soldier parts ---------------------------------------------------------

static func _attach(root: Node3D, node_name: String, pivot: Vector3, mesh: Mesh) -> void:
	var part := Node3D.new()
	part.name = node_name
	part.position = pivot
	var mi := MeshInstance3D.new()
	mi.name = "Mesh"
	mi.mesh = mesh
	part.add_child(mi)
	root.add_child(part)


## One cached body part. Geometry is expressed RELATIVE to the part pivot.
static func _soldier_part(faction: int, variant: int, part: String) -> Mesh:
	var key: String = "sold:%d:%d:%s" % [faction, variant, part]
	if _cache.has(key):
		return _cache[key]
	var b := _Build.new()
	var uni: String = _uniform_key(faction)
	# Girth per variant: same 1.8 m height for everyone (hitboxes stay
	# comparable), only the build changes.
	var girth: float = [1.0, 0.93, 1.10][variant]

	match part:
		"hips":
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.02, 0)),
					Vector3(0.34 * girth, 0.24, 0.25 * girth), Color.WHITE)
			b.box("wood", Transform3D(Basis.IDENTITY, Vector3(0, 0.05, 0)),
					Vector3(0.36 * girth, 0.07, 0.27 * girth), Color.WHITE)
			if faction == _F_AXIS:
				# Bread bag and canteen on the left hip.
				b.box("cloth", Transform3D(Basis.IDENTITY, Vector3(-0.20, -0.02, 0.06)),
						Vector3(0.09, 0.17, 0.13), Color.WHITE)
				b.box("metal", Transform3D(Basis.IDENTITY, Vector3(0.19, -0.03, 0.08)),
						Vector3(0.07, 0.15, 0.10), Color.WHITE)
			else:
				b.box("cloth", Transform3D(Basis.IDENTITY, Vector3(0.20, -0.02, 0.05)),
						Vector3(0.09, 0.16, 0.12), Color.WHITE)
		"torso":
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, 0.27, 0)),
					Vector3(0.42 * girth, 0.52, 0.25 * girth), Color.WHITE)
			# Shoulders, a touch wider than the chest.
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, 0.47, 0)),
					Vector3(0.48 * girth, 0.14, 0.26 * girth), Color.WHITE)
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, 0.55, 0)),
					Vector3(0.22, 0.07, 0.20), Color.WHITE)
			# Y straps.
			for side in 2:
				var sx: float = -0.11 if side == 0 else 0.11
				b.box("wood", Transform3D(Basis(Vector3(0, 0, 1),
						0.10 if side == 0 else -0.10), Vector3(sx, 0.30, -0.135)),
						Vector3(0.055, 0.44, 0.03), Color.WHITE)
			if faction == _F_AXIS or variant == 1:
				b.box("cloth", Transform3D(Basis.IDENTITY, Vector3(0, 0.34, 0.20)),
						Vector3(0.30, 0.28, 0.16), Color.WHITE)
			if faction == _F_NEUTRAL:
				# Resistance armband, the only bright thing on a civilian.
				b.box("flag_allied", Transform3D(Basis.IDENTITY,
						Vector3(-0.215 * girth, 0.40, 0)),
						Vector3(0.03, 0.11, 0.24), Color.WHITE)
		"head":
			b.box("skin", Transform3D(Basis.IDENTITY, Vector3(0, 0.105, 0)),
					Vector3(0.185, 0.215, 0.20), Color.WHITE)
			b.box("skin", Transform3D(Basis.IDENTITY, Vector3(0, 0.09, -0.115)),
					Vector3(0.055, 0.06, 0.04), Color.WHITE)
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, 0.005, 0)),
					Vector3(0.15, 0.05, 0.17), Color.WHITE)
		"helmet":
			_build_helmet(b, faction, variant)
		"arm":
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.155, 0)),
					Vector3(0.135 * girth, 0.32, 0.145 * girth), Color.WHITE)
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.45, -0.01)),
					Vector3(0.115 * girth, 0.28, 0.125 * girth), Color.WHITE)
			b.box("skin", Transform3D(Basis.IDENTITY, Vector3(0, -0.625, -0.02)),
					Vector3(0.095, 0.10, 0.095), Color.WHITE)
		"leg":
			b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.22, 0)),
					Vector3(0.165 * girth, 0.46, 0.185 * girth), Color.WHITE)
			if faction == _F_AXIS:
				# Jackboots: the shaft climbs the calf, a strong silhouette cue.
				b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.52, 0)),
						Vector3(0.145 * girth, 0.16, 0.16 * girth), Color.WHITE)
				b.box("wood", Transform3D(Basis.IDENTITY, Vector3(0, -0.71, 0.005)),
						Vector3(0.155, 0.28, 0.17), Color.WHITE)
			else:
				b.box(uni, Transform3D(Basis.IDENTITY, Vector3(0, -0.60, 0)),
						Vector3(0.145 * girth, 0.32, 0.16 * girth), Color.WHITE)
				# Canvas leggings.
				b.box("cloth", Transform3D(Basis.IDENTITY, Vector3(0, -0.755, 0.005)),
						Vector3(0.155, 0.13, 0.17), Color.WHITE)
			b.box("wood", Transform3D(Basis.IDENTITY, Vector3(0, -0.845, -0.045)),
					Vector3(0.16, 0.11, 0.29), Color.WHITE)
		_:
			push_warning("Meshes: unknown soldier part " + part)

	var mesh: ArrayMesh = b.commit()
	_cache[key] = mesh
	return mesh


## The single most important read in the game: which side is that man on.
##
## - Axis: Stahlhelm. Wide, square, and above all a brim that FLARES DOWN and
##   out all round, deepest at the back and over the ears.
## - Allied: M1. A rounded pot with a shallow, even lip.
## - Resistance: no helmet at all, a flat cap.
static func _build_helmet(b: _Build, faction: int, variant: int) -> void:
	match faction:
		_F_AXIS:
			var shell := "uniform_axis"
			b.ellipsoid(shell, Vector3(0, 0.035, -0.005),
					Vector3(0.158, 0.135, 0.168), 5, 12, Color.WHITE)
			# The flared skirt, stretched along Z so it juts out at the neck.
			var skirt := Transform3D(
					Basis(Vector3(1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1.10)),
					Vector3(0, -0.045, -0.012))
			b.tube(shell, skirt, 0.196, 0.152, 0.082, 12, Color.WHITE, false, false)
			# Squared off front peak: the visor that reads as German at 80 m.
			b.box(shell, Transform3D(Basis(Vector3(1, 0, 0), -0.30),
					Vector3(0, -0.012, -0.175)), Vector3(0.30, 0.05, 0.09), Color.WHITE)
			if variant == 2:
				# Chicken wire cover, suggested by two thin bands.
				b.tube("barbed_wire", Transform3D(Basis.IDENTITY, Vector3(0, 0.04, 0)),
						0.163, 0.163, 0.02, 12, Color.WHITE, false, false)
		_F_NEUTRAL:
			# Flat cap, no steel: a civilian who picked up a rifle.
			b.ellipsoid("cloth", Vector3(0, -0.01, 0.01),
					Vector3(0.132, 0.062, 0.140), 4, 10, Color.WHITE)
			b.box("cloth", Transform3D(Basis(Vector3(1, 0, 0), -0.16),
					Vector3(0, -0.028, -0.135)), Vector3(0.20, 0.025, 0.10), Color.WHITE)
		_:
			var shell_a := "uniform_allied"
			b.ellipsoid(shell_a, Vector3(0, 0.028, 0.0),
					Vector3(0.142, 0.130, 0.152), 5, 12, Color.WHITE)
			# Shallow, even lip all round: nothing like the German skirt.
			var brim := Transform3D(Basis.IDENTITY, Vector3(0, -0.052, 0))
			b.tube(shell_a, brim, 0.163, 0.143, 0.032, 12, Color.WHITE, false, false)
			if variant != 0:
				b.box("cloth", Transform3D(Basis.IDENTITY, Vector3(0, 0.02, 0.148)),
						Vector3(0.10, 0.05, 0.02), Color.WHITE)


static func _uniform_key(faction: int) -> String:
	match faction:
		_F_AXIS:
			return "uniform_axis"
		_F_NEUTRAL:
			return "uniform_resistance"
		_:
			return "uniform_allied"


## What an AI soldier of that faction carries by default.
static func _default_weapon(faction: int, variant: int) -> int:
	match faction:
		_F_AXIS:
			return _W_MP40 if variant == 1 else _W_KAR98K
		_F_NEUTRAL:
			return _W_THOMPSON if variant == 1 else _W_KAR98K
		_:
			return _W_THOMPSON if variant == 1 else _W_M1_GARAND


# --- Weapons ---------------------------------------------------------------

## Shared bolt / semi auto rifle body. `wood_len` is the length of the forestock
## ahead of the receiver, which is what makes a Garand or a Kar98k read as a
## rifle rather than a stick.
static func _rifle(wood_len: float, stock_h: float, garand: bool,
		scope: bool) -> ArrayMesh:
	var b := _Build.new()
	# Butt and comb.
	b.box("gun_wood", Transform3D(Basis(Vector3(1, 0, 0), 0.0),
			Vector3(0, -0.012, 0.245)), Vector3(0.048, 0.105, 0.30), Color.WHITE)
	b.box("gun_wood", Transform3D(Basis.IDENTITY, Vector3(0, 0.012, 0.075)),
			Vector3(0.046, stock_h + 0.02, 0.26), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.06, 0.40)),
			Vector3(0.05, 0.11, 0.02), Color.WHITE)
	# Receiver.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.018, -0.075)),
			Vector3(0.044, 0.072, 0.24), Color.WHITE)
	# Forestock: the long slim wooden fore end.
	b.box("gun_wood", Transform3D(Basis.IDENTITY,
			Vector3(0, -0.012, -0.20 - wood_len * 0.5)),
			Vector3(0.042, 0.058, wood_len), Color.WHITE)
	# Thin barrel poking out past the wood.
	var muzzle: float = -0.20 - wood_len - 0.15
	b.tube_z("gun_metal", 0.0, 0.020, -0.20, muzzle, 0.0105, 0.0095, 8, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.042, muzzle + 0.05)),
			Vector3(0.014, 0.032, 0.024), Color.WHITE)   # front sight
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.058, 0.02)),
			Vector3(0.028, 0.022, 0.02), Color.WHITE)    # rear sight
	# Trigger guard and grip swell.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.055, -0.015)),
			Vector3(0.026, 0.045, 0.10), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.032, -0.145)),
			Vector3(0.03, 0.03, 0.09), Color.WHITE)      # barrel band
	if garand:
		# Op rod down the right side, and the en bloc magazine bulge.
		b.tube_z("gun_metal", 0.030, -0.028, -0.16, muzzle + 0.12, 0.009, 0.009,
				6, Color.WHITE)
		b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.038, -0.06)),
				Vector3(0.04, 0.045, 0.11), Color.WHITE)
	elif scope:
		# Turned down bolt handle: a straight one would foul the scope tube, and
		# the bent one is what every sniper conversion of the era carries.
		b.limb("gun_metal", Vector3(0.02, 0.028, 0.01), Vector3(0.072, 0.018, 0.02),
				0.011, 0.010, 6, Color.WHITE)
		b.limb("gun_metal", Vector3(0.072, 0.018, 0.02), Vector3(0.082, -0.028, 0.024),
				0.010, 0.010, 6, Color.WHITE)
		b.ellipsoid("gun_metal", Vector3(0.084, -0.038, 0.025),
				Vector3(0.020, 0.020, 0.020), 4, 7, Color.WHITE)
	else:
		# Straight bolt handle sticking out to the right.
		b.limb("gun_metal", Vector3(0.02, 0.028, 0.01), Vector3(0.10, 0.012, 0.03),
				0.011, 0.011, 6, Color.WHITE)
		b.ellipsoid("gun_metal", Vector3(0.108, 0.010, 0.033),
				Vector3(0.022, 0.022, 0.022), 4, 7, Color.WHITE)
	if scope:
		_scope(b)
	return b.commit()


## The x4 telescopic sight, shared by the Springfield and the scoped Kar98k.
## Sits high enough over the receiver for daylight to show under the tube: that
## gap, plus the bell of the objective, is what makes a sniper readable in
## silhouette from the far end of a street.
static func _scope(b: _Build) -> void:
	var y: float = 0.088
	# Main tube, ocular bell at the rear, wider objective bell at the front.
	b.tube_z("gun_metal", 0.0, y, 0.040, -0.225, 0.0165, 0.0165, 10, Color.WHITE)
	b.tube_z("gun_metal", 0.0, y, 0.055, 0.030, 0.0215, 0.0175, 10, Color.WHITE)
	b.tube_z("gun_metal", 0.0, y, -0.212, -0.256, 0.0195, 0.0255, 10, Color.WHITE)
	# Two rings, each a collar around the tube on a block bolted to the receiver.
	for z: float in [-0.030, -0.155]:
		b.tube_z("gun_metal", 0.0, y, z + 0.010, z - 0.010, 0.021, 0.021, 10,
				Color.WHITE)
		b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0.0, 0.064, z)),
				Vector3(0.020, 0.030, 0.024), Color.WHITE)
	# Elevation turret on top of the tube.
	b.tube("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0.0, y + 0.008, -0.075)),
			0.012, 0.010, 0.018, 8, Color.WHITE, false, true)


static func _thompson() -> ArrayMesh:
	var b := _Build.new()
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.005, -0.11)),
			Vector3(0.052, 0.088, 0.34), Color.WHITE)
	b.box("gun_wood", Transform3D(Basis.IDENTITY, Vector3(0, -0.005, 0.21)),
			Vector3(0.05, 0.105, 0.30), Color.WHITE)
	# Pistol grip.
	b.box("gun_wood", Transform3D(Basis(Vector3(1, 0, 0), -0.22),
			Vector3(0, -0.115, 0.045)), Vector3(0.044, 0.155, 0.058), Color.WHITE)
	# The vertical foregrip and the stick magazine: the Thompson's two tells.
	b.box("gun_wood", Transform3D(Basis(Vector3(1, 0, 0), 0.10),
			Vector3(0, -0.115, -0.255)), Vector3(0.046, 0.155, 0.055), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.135, -0.075)),
			Vector3(0.034, 0.185, 0.055), Color.WHITE)
	# Finned barrel.
	b.tube_z("gun_metal", 0.0, 0.02, -0.28, -0.50, 0.013, 0.012, 8, Color.WHITE)
	for i in 4:
		b.tube_z("gun_metal", 0.0, 0.02, -0.31 - float(i) * 0.045,
				-0.325 - float(i) * 0.045, 0.021, 0.021, 8, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.062, -0.44)),
			Vector3(0.012, 0.026, 0.02), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.062, -0.03)),
			Vector3(0.024, 0.04, 0.09), Color.WHITE)
	return b.commit()


static func _mp40() -> ArrayMesh:
	var b := _Build.new()
	# Tubular receiver.
	b.tube_z("gun_metal", 0.0, 0.015, 0.02, -0.30, 0.024, 0.022, 10, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.015, -0.13)),
			Vector3(0.046, 0.05, 0.22), Color.WHITE)
	# Long straight magazine, hanging vertically. Unmistakable.
	b.box("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), -0.04),
			Vector3(0, -0.155, -0.075)), Vector3(0.030, 0.26, 0.050), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.035, -0.075)),
			Vector3(0.042, 0.075, 0.07), Color.WHITE)
	# Bakelite grip and lower housing.
	b.box("cloth", Transform3D(Basis(Vector3(1, 0, 0), -0.20),
			Vector3(0, -0.105, 0.055)), Vector3(0.040, 0.145, 0.055), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.045, 0.0)),
			Vector3(0.030, 0.05, 0.13), Color.WHITE)
	# Folding tubular stock: two rails plus a butt plate.
	for side in 2:
		var x: float = -0.028 if side == 0 else 0.028
		b.tube_z("gun_metal", x, -0.02, 0.10, 0.35, 0.010, 0.010, 6, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.02, 0.365)),
			Vector3(0.09, 0.035, 0.025), Color.WHITE)
	# Barrel and the resting bar under the muzzle.
	b.tube_z("gun_metal", 0.0, 0.015, -0.28, -0.44, 0.011, 0.011, 8, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.008, -0.30)),
			Vector3(0.032, 0.03, 0.045), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.046, -0.42)),
			Vector3(0.012, 0.026, 0.02), Color.WHITE)
	return b.commit()


static func _mg42() -> ArrayMesh:
	var b := _Build.new()
	# Deep receiver.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.0, -0.08)),
			Vector3(0.068, 0.115, 0.42), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.062, -0.13)),
			Vector3(0.075, 0.035, 0.26), Color.WHITE)     # feed tray cover
	# Perforated barrel shroud, suggested by stacked rings.
	b.tube_z("gun_metal", 0.0, 0.0, -0.29, -0.70, 0.043, 0.040, 10, Color.WHITE)
	for i in 6:
		b.tube_z("gun_metal", 0.0, 0.0, -0.31 - float(i) * 0.062,
				-0.335 - float(i) * 0.062, 0.049, 0.049, 10, Color.WHITE)
	# Heavy barrel poking past the shroud.
	b.tube_z("gun_metal", 0.0, 0.0, -0.70, -0.82, 0.019, 0.017, 8, Color.WHITE)
	# Stock and grip.
	b.box("gun_wood", Transform3D(Basis.IDENTITY, Vector3(0, -0.01, 0.26)),
			Vector3(0.052, 0.095, 0.30), Color.WHITE)
	b.box("cloth", Transform3D(Basis(Vector3(1, 0, 0), -0.24),
			Vector3(0, -0.115, 0.10)), Vector3(0.042, 0.15, 0.055), Color.WHITE)
	# Bipod, splayed forward and down.
	for side in 2:
		var x: float = -0.02 if side == 0 else 0.02
		var foot: float = -0.20 if side == 0 else 0.20
		b.limb("gun_metal", Vector3(x, -0.03, -0.62),
				Vector3(foot, -0.34, -0.50), 0.011, 0.009, 6, Color.WHITE)
	# Belt of ammunition hanging out of the feed tray.
	for i in 6:
		b.box("gun_metal", Transform3D(Basis(Vector3(0, 0, 1), 0.10 * float(i)),
				Vector3(-0.05 - float(i) * 0.012, 0.02 - float(i) * 0.031, -0.14)),
				Vector3(0.02, 0.032, 0.055), Color.WHITE)
	return b.commit()


static func _pistol() -> ArrayMesh:
	var b := _Build.new()
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.022, -0.055)),
			Vector3(0.026, 0.046, 0.195), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.004, -0.03)),
			Vector3(0.028, 0.03, 0.13), Color.WHITE)
	b.box("gun_wood", Transform3D(Basis(Vector3(1, 0, 0), 0.28),
			Vector3(0, -0.072, 0.036)), Vector3(0.030, 0.125, 0.048), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, -0.032, -0.012)),
			Vector3(0.022, 0.035, 0.045), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.048, -0.14)),
			Vector3(0.009, 0.014, 0.014), Color.WHITE)
	return b.commit()


## Luger P08. Everything here exists to keep it from reading as the M1911,
## which is a stubby rectangular slab: the barrel is thin and long, the toggle
## action breaks upwards in a chevron over the breech instead of a flat slide,
## and the grip is raked far back. About 0.22 m from muzzle to butt.
static func _luger() -> ArrayMesh:
	var b := _Build.new()
	# Frame: the flat body carrying the trigger, below the action.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.008, 0.002)),
			Vector3(0.030, 0.036, 0.100), Color.WHITE)
	# Barrel extension: the squared block the toggle is hinged on.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.032, -0.018)),
			Vector3(0.028, 0.040, 0.062), Color.WHITE)
	# Slim tapered barrel. Half the M1911 slide in section, twice as elegant.
	b.tube_z("gun_metal", 0.0, 0.032, -0.040, -0.135, 0.0105, 0.0080, 8, Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.050, -0.127)),
			Vector3(0.006, 0.016, 0.010), Color.WHITE)      # front sight blade
	# The toggle action: two links breaking upwards into a knee, with the
	# knurled knobs on the joint. This is the whole silhouette of the weapon.
	b.box("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), -0.683),
			Vector3(0, 0.057, 0.000)), Vector3(0.024, 0.013, 0.045), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), 0.564),
			Vector3(0, 0.058, 0.035)), Vector3(0.024, 0.013, 0.049), Color.WHITE)
	b.tube("gun_metal", Transform3D(Basis(Vector3(0, 0, 1), -PI * 0.5),
			Vector3(-0.014, 0.070, 0.016)), 0.012, 0.012, 0.028, 8, Color.WHITE,
			true, true)
	# Breech block closing the rear of the action, with the sight notch on top.
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.042, 0.056)),
			Vector3(0.026, 0.032, 0.030), Color.WHITE)
	b.box("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.061, 0.052)),
			Vector3(0.016, 0.008, 0.012), Color.WHITE)      # rear sight
	# Round trigger guard, drawn as an arc of rods.
	var guard_c := Vector3(0.0, -0.012, -0.006)
	var guard_r: float = 0.026
	var prev: Vector3 = guard_c + Vector3(0.0, 0.0, guard_r)
	for i in range(1, 7):
		var t: float = PI * float(i) / 6.0
		var p: Vector3 = guard_c + Vector3(0.0, -sin(t) * guard_r * 0.85,
				cos(t) * guard_r)
		b.limb("gun_metal", prev, p, 0.0042, 0.0042, 5, Color.WHITE)
		prev = p
	b.box("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), -0.12),
			Vector3(0, -0.024, -0.002)), Vector3(0.007, 0.024, 0.008), Color.WHITE)
	# Grip, raked well back. The M1911 grip stands almost upright; this one
	# leans about 32 degrees, which is what the eye actually picks up at range.
	var grip := Transform3D(Basis(Vector3(1, 0, 0), -0.55), Vector3(0, -0.050, 0.036))
	b.box("gun_metal", grip, Vector3(0.026, 0.092, 0.046), Color.WHITE)
	for side in 2:
		var x: float = -0.015 if side == 0 else 0.015
		b.box("gun_wood", grip.translated_local(Vector3(x, -0.002, 0.0)),
				Vector3(0.008, 0.080, 0.042), Color.WHITE)
	b.box("gun_metal", grip.translated_local(Vector3(0.0, -0.048, 0.0)),
			Vector3(0.030, 0.008, 0.050), Color.WHITE)      # magazine floorplate
	return b.commit()


static func _grenade() -> ArrayMesh:
	var b := _Build.new()
	# Few segments on purpose: the facets read as the cast iron grooves.
	b.ellipsoid("gun_metal", Vector3(0, 0.0, 0), Vector3(0.033, 0.048, 0.033),
			4, 6, Color.WHITE)
	b.tube("gun_metal", Transform3D(Basis.IDENTITY, Vector3(0, 0.040, 0)),
			0.016, 0.014, 0.028, 6, Color.WHITE, false, true)
	b.box("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), 0.06),
			Vector3(0, 0.020, -0.030)), Vector3(0.014, 0.075, 0.008), Color.WHITE)
	b.tube("gun_metal", Transform3D(Basis(Vector3(1, 0, 0), PI * 0.5),
			Vector3(0.020, 0.046, 0)), 0.011, 0.011, 0.004, 6, Color.WHITE, true, true)
	return b.commit()


# --- Shared helpers --------------------------------------------------------

## A deterministic RNG for a shape. The mesh library must produce the same
## geometry on every launch, otherwise a saved game reloads a different forest.
static func _rng(shape_seed: int) -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = shape_seed * 2654435761
	return rng


## Slight per blob shading. Harmless when the foliage material ignores vertex
## colour, welcome variety when it uses it as an albedo multiplier.
static func _leaf_shade(rng: RandomNumberGenerator) -> Color:
	var k: float = rng.randf_range(0.80, 1.0)
	return Color(k * rng.randf_range(0.92, 1.02), k, k * rng.randf_range(0.88, 1.0), 1.0)


## Raw quad with no attributes but the position, for surfaces finished with
## `generate_normals()`.
static func _raw_quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3,
		d: Vector3) -> void:
	st.set_uv(Vector2(0, 0))
	st.add_vertex(a)
	st.set_uv(Vector2(1, 0))
	st.add_vertex(b)
	st.set_uv(Vector2(1, 1))
	st.add_vertex(c)
	st.set_uv(Vector2(0, 0))
	st.add_vertex(a)
	st.set_uv(Vector2(1, 1))
	st.add_vertex(c)
	st.set_uv(Vector2(0, 1))
	st.add_vertex(d)


# --- Geometry accumulator --------------------------------------------------

## Accumulates geometry into one SurfaceTool per material key, then commits an
## ArrayMesh with one surface per material. Keeping a prop down to three or
## four surfaces is what lets a MultiMesh of a thousand oaks stay cheap.
##
## Every primitive writes its own normals, so no surface ever mixes generated
## and explicit normals (which SurfaceTool refuses).
class _Build extends RefCounted:
	var _tools: Dictionary = {}
	var _order: PackedStringArray = PackedStringArray()

	func tool_for(key: String) -> SurfaceTool:
		if _tools.has(key):
			return _tools[key]
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		_tools[key] = st
		_order.append(key)
		return st

	func _vertex(st: SurfaceTool, p: Vector3, n: Vector3, uv: Vector2,
			c: Color) -> void:
		st.set_normal(n)
		st.set_uv(uv)
		st.set_color(c)
		st.add_vertex(p)

	## Flat shaded quad, wound a -> b -> c -> d.
	func quad(key: String, a: Vector3, b: Vector3, c: Vector3, d: Vector3,
			uv_size: Vector2, color: Color) -> void:
		var n: Vector3 = (b - a).cross(c - a)
		if n.length_squared() < 1e-12:
			return
		n = n.normalized()
		var st: SurfaceTool = tool_for(key)
		var u: float = uv_size.x
		var v: float = uv_size.y
		_vertex(st, a, n, Vector2(0, 0), color)
		_vertex(st, b, n, Vector2(u, 0), color)
		_vertex(st, c, n, Vector2(u, v), color)
		_vertex(st, a, n, Vector2(0, 0), color)
		_vertex(st, c, n, Vector2(u, v), color)
		_vertex(st, d, n, Vector2(0, v), color)

	## Smooth shaded quad with per corner normals.
	func quad_n(key: String, a: Vector3, b: Vector3, c: Vector3, d: Vector3,
			na: Vector3, nb: Vector3, nc: Vector3, nd: Vector3,
			ua: Vector2, ub: Vector2, uc: Vector2, ud: Vector2,
			color: Color) -> void:
		var st: SurfaceTool = tool_for(key)
		if a.distance_squared_to(b) > 1e-10:
			_vertex(st, a, na, ua, color)
			_vertex(st, b, nb, ub, color)
			_vertex(st, c, nc, uc, color)
		if c.distance_squared_to(d) > 1e-10:
			_vertex(st, a, na, ua, color)
			_vertex(st, c, nc, uc, color)
			_vertex(st, d, nd, ud, color)

	## Axis aligned box placed by `xf`, centred on the transform origin.
	func box(key: String, xf: Transform3D, size: Vector3, color: Color) -> void:
		var h: Vector3 = size * 0.5
		var p: Array[Vector3] = [
			xf * Vector3(-h.x, -h.y, -h.z), xf * Vector3(h.x, -h.y, -h.z),
			xf * Vector3(h.x, h.y, -h.z), xf * Vector3(-h.x, h.y, -h.z),
			xf * Vector3(-h.x, -h.y, h.z), xf * Vector3(h.x, -h.y, h.z),
			xf * Vector3(h.x, h.y, h.z), xf * Vector3(-h.x, h.y, h.z),
		]
		quad(key, p[4], p[5], p[6], p[7], Vector2(size.x, size.y), color)  # +Z
		quad(key, p[1], p[0], p[3], p[2], Vector2(size.x, size.y), color)  # -Z
		quad(key, p[5], p[1], p[2], p[6], Vector2(size.z, size.y), color)  # +X
		quad(key, p[0], p[4], p[7], p[3], Vector2(size.z, size.y), color)  # -X
		quad(key, p[3], p[7], p[6], p[2], Vector2(size.x, size.z), color)  # +Y
		quad(key, p[0], p[1], p[5], p[4], Vector2(size.x, size.z), color)  # -Y

	## Box with a smaller top face, for earth banks and berms. Runs along X.
	func trapezoid(key: String, centre: Vector3, length: float, height: float,
			bottom_width: float, top_width: float, color: Color) -> void:
		var hl: float = length * 0.5
		var hb: float = bottom_width * 0.5
		var ht: float = top_width * 0.5
		var y0: float = centre.y
		var y1: float = centre.y + height
		var b0 := centre + Vector3(-hl, 0, -hb)
		var b1 := centre + Vector3(hl, 0, -hb)
		var b2 := centre + Vector3(hl, 0, hb)
		var b3 := centre + Vector3(-hl, 0, hb)
		b0.y = y0
		b1.y = y0
		b2.y = y0
		b3.y = y0
		var t0 := Vector3(centre.x - hl, y1, centre.z - ht)
		var t1 := Vector3(centre.x + hl, y1, centre.z - ht)
		var t2 := Vector3(centre.x + hl, y1, centre.z + ht)
		var t3 := Vector3(centre.x - hl, y1, centre.z + ht)
		quad(key, b0, t0, t1, b1, Vector2(length, height), color)
		quad(key, b2, t2, t3, b3, Vector2(length, height), color)
		quad(key, t0, t3, t2, t1, Vector2(length, top_width), color)
		quad(key, b0, b3, t3, t0, Vector2(bottom_width, height), color)
		quad(key, b1, t1, t2, b2, Vector2(bottom_width, height), color)

	## Cone frustum standing on the transform origin, extending `height` along
	## the transform +Y. `r1` of zero makes a cone.
	func tube(key: String, xf: Transform3D, r0: float, r1: float, height: float,
			sides: int, color: Color, cap_bottom: bool = false,
			cap_top: bool = false) -> void:
		var n: int = clampi(sides, 3, 64)
		var slope: float = (r0 - r1) / maxf(height, 0.0001)
		var tip: bool = r1 < 0.0005
		var st: SurfaceTool = tool_for(key)
		var circumference: float = TAU * maxf(r0, r1)
		for i in n:
			var a0: float = TAU * float(i) / float(n)
			var a1: float = TAU * float(i + 1) / float(n)
			var c0 := Vector3(cos(a0), 0.0, sin(a0))
			var c1 := Vector3(cos(a1), 0.0, sin(a1))
			var p0: Vector3 = xf * (c0 * r0)
			var p1: Vector3 = xf * (c1 * r0)
			var n0: Vector3 = (xf.basis * Vector3(c0.x, slope, c0.z)).normalized()
			var n1: Vector3 = (xf.basis * Vector3(c1.x, slope, c1.z)).normalized()
			var u0: float = circumference * float(i) / float(n)
			var u1: float = circumference * float(i + 1) / float(n)
			if tip:
				var apex: Vector3 = xf * Vector3(0.0, height, 0.0)
				var na: Vector3 = (n0 + n1).normalized()
				_vertex(st, p0, n0, Vector2(u0, 0.0), color)
				_vertex(st, apex, na, Vector2((u0 + u1) * 0.5, height), color)
				_vertex(st, p1, n1, Vector2(u1, 0.0), color)
			else:
				var q0: Vector3 = xf * (c0 * r1 + Vector3(0.0, height, 0.0))
				var q1: Vector3 = xf * (c1 * r1 + Vector3(0.0, height, 0.0))
				quad_n(key, p0, q0, q1, p1, n0, n0, n1, n1,
						Vector2(u0, 0.0), Vector2(u0, height),
						Vector2(u1, height), Vector2(u1, 0.0), color)
		if cap_bottom:
			var down: Vector3 = (xf.basis * Vector3.DOWN).normalized()
			var centre0: Vector3 = xf * Vector3.ZERO
			for i in n:
				var a0: float = TAU * float(i) / float(n)
				var a1: float = TAU * float(i + 1) / float(n)
				var p0: Vector3 = xf * (Vector3(cos(a0), 0.0, sin(a0)) * r0)
				var p1: Vector3 = xf * (Vector3(cos(a1), 0.0, sin(a1)) * r0)
				_vertex(st, centre0, down, Vector2(0.0, 0.0), color)
				_vertex(st, p0, down, Vector2(cos(a0) * r0, sin(a0) * r0), color)
				_vertex(st, p1, down, Vector2(cos(a1) * r0, sin(a1) * r0), color)
		if cap_top and not tip:
			var up: Vector3 = (xf.basis * Vector3.UP).normalized()
			var centre1: Vector3 = xf * Vector3(0.0, height, 0.0)
			for i in n:
				var a0: float = TAU * float(i) / float(n)
				var a1: float = TAU * float(i + 1) / float(n)
				var p0: Vector3 = xf * (Vector3(cos(a0), 0.0, sin(a0)) * r1
						+ Vector3(0.0, height, 0.0))
				var p1: Vector3 = xf * (Vector3(cos(a1), 0.0, sin(a1)) * r1
						+ Vector3(0.0, height, 0.0))
				_vertex(st, centre1, up, Vector2(0.0, 0.0), color)
				_vertex(st, p1, up, Vector2(cos(a1) * r1, sin(a1) * r1), color)
				_vertex(st, p0, up, Vector2(cos(a0) * r1, sin(a0) * r1), color)

	## Tapered cylinder between two points: branches, gun barrels, bipod legs.
	func limb(key: String, from: Vector3, to: Vector3, r0: float, r1: float,
			sides: int, color: Color) -> void:
		var dir: Vector3 = to - from
		var length: float = dir.length()
		if length < 0.0005:
			return
		tube(key, Transform3D(_aim_basis(dir), from), r0, r1, length,
				sides, color, false, false)

	## Basis whose +Y axis points along `dir`, used to aim limbs and barrels.
	## Deliberately a method of the builder rather than a static of the outer
	## class: an inner class cannot reach an outer static without naming the
	## class, and that self reference will not resolve on a cold project whose
	## global class cache has not been built yet.
	func _aim_basis(dir: Vector3) -> Basis:
		var y: Vector3 = dir.normalized()
		if y.length_squared() < 0.5:
			return Basis.IDENTITY
		var ref := Vector3.RIGHT
		if absf(y.x) > 0.9:
			ref = Vector3.FORWARD
		var x: Vector3 = ref.cross(y).normalized()
		var z: Vector3 = x.cross(y)
		return Basis(x, y, z)

	## Cylinder running along -Z (weapon convention), from `z0` to `z1`.
	func tube_z(key: String, x: float, y: float, z0: float, z1: float,
			r0: float, r1: float, sides: int, color: Color) -> void:
		limb(key, Vector3(x, y, z0), Vector3(x, y, z1), r0, r1, sides, color)

	## Axis aligned ellipsoid: the flattened canopy masses and helmet shells.
	func ellipsoid(key: String, centre: Vector3, radii: Vector3, rings: int,
			segments: int, color: Color) -> void:
		var ri: int = clampi(rings, 2, 32)
		var se: int = clampi(segments, 3, 48)
		var inv := Vector3(1.0 / maxf(radii.x, 1e-4), 1.0 / maxf(radii.y, 1e-4),
				1.0 / maxf(radii.z, 1e-4))
		for i in ri:
			for j in se:
				var a: Vector3 = _ellipsoid_point(centre, radii, i, j, ri, se)
				var b: Vector3 = _ellipsoid_point(centre, radii, i, j + 1, ri, se)
				var c: Vector3 = _ellipsoid_point(centre, radii, i + 1, j + 1, ri, se)
				var d: Vector3 = _ellipsoid_point(centre, radii, i + 1, j, ri, se)
				quad_n(key, a, b, c, d,
						_ellipsoid_normal(a - centre, inv),
						_ellipsoid_normal(b - centre, inv),
						_ellipsoid_normal(c - centre, inv),
						_ellipsoid_normal(d - centre, inv),
						Vector2(float(j) / float(se), float(i) / float(ri)),
						Vector2(float(j + 1) / float(se), float(i) / float(ri)),
						Vector2(float(j + 1) / float(se), float(i + 1) / float(ri)),
						Vector2(float(j) / float(se), float(i + 1) / float(ri)),
						color)

	func _ellipsoid_point(centre: Vector3, radii: Vector3, i: int, j: int,
			rings: int, segments: int) -> Vector3:
		var theta: float = PI * float(i) / float(rings)
		var phi: float = TAU * float(j) / float(segments)
		return centre + Vector3(
			radii.x * sin(theta) * cos(phi),
			radii.y * cos(theta),
			radii.z * sin(theta) * sin(phi))

	func _ellipsoid_normal(local: Vector3, inv: Vector3) -> Vector3:
		var n := Vector3(local.x * inv.x * inv.x, local.y * inv.y * inv.y,
				local.z * inv.z * inv.z)
		if n.length_squared() < 1e-12:
			return Vector3.UP
		return n.normalized()

	## Deformed icosphere: the boulder. Flat facets, computed per triangle.
	func rock(key: String, centre: Vector3, radius: float, squash: Vector3,
			subdivisions: int, shape_seed: int, color: Color) -> void:
		var t := 1.618033988749895
		var verts: Array[Vector3] = [
			Vector3(-1, t, 0), Vector3(1, t, 0), Vector3(-1, -t, 0), Vector3(1, -t, 0),
			Vector3(0, -1, t), Vector3(0, 1, t), Vector3(0, -1, -t), Vector3(0, 1, -t),
			Vector3(t, 0, -1), Vector3(t, 0, 1), Vector3(-t, 0, -1), Vector3(-t, 0, 1),
		]
		for i in verts.size():
			verts[i] = verts[i].normalized()
		var faces: Array[Vector3i] = [
			Vector3i(0, 11, 5), Vector3i(0, 5, 1), Vector3i(0, 1, 7),
			Vector3i(0, 7, 10), Vector3i(0, 10, 11), Vector3i(1, 5, 9),
			Vector3i(5, 11, 4), Vector3i(11, 10, 2), Vector3i(10, 7, 6),
			Vector3i(7, 1, 8), Vector3i(3, 9, 4), Vector3i(3, 4, 2),
			Vector3i(3, 2, 6), Vector3i(3, 6, 8), Vector3i(3, 8, 9),
			Vector3i(4, 9, 5), Vector3i(2, 4, 11), Vector3i(6, 2, 10),
			Vector3i(8, 6, 7), Vector3i(9, 8, 1),
		]
		for pass_index in maxi(subdivisions, 0):
			var mids: Dictionary = {}
			var next: Array[Vector3i] = []
			for f in faces:
				var ab: int = _midpoint(verts, mids, f.x, f.y)
				var bc: int = _midpoint(verts, mids, f.y, f.z)
				var ca: int = _midpoint(verts, mids, f.z, f.x)
				next.append(Vector3i(f.x, ab, ca))
				next.append(Vector3i(f.y, bc, ab))
				next.append(Vector3i(f.z, ca, bc))
				next.append(Vector3i(ab, bc, ca))
			faces = next
		# Displace: two low frequency lobes plus a per vertex jitter, so the
		# rock has real shape instead of uniform noise.
		var rng := RandomNumberGenerator.new()
		rng.seed = shape_seed
		var s1: float = rng.randf() * TAU
		var s2: float = rng.randf() * TAU
		var s3: float = rng.randf() * TAU
		var moved: Array[Vector3] = []
		moved.resize(verts.size())
		for i in verts.size():
			var d: Vector3 = verts[i]
			var f: float = 1.0
			f += 0.20 * sin(d.x * 2.7 + s1) * cos(d.y * 2.1 + s2)
			f += 0.13 * sin(d.z * 3.4 + s3)
			f += 0.09 * (sin(float(i) * 12.9898 + s1) * 43758.5453
					- floor(sin(float(i) * 12.9898 + s1) * 43758.5453) - 0.5)
			moved[i] = centre + Vector3(d.x * squash.x, d.y * squash.y,
					d.z * squash.z) * radius * clampf(f, 0.55, 1.5)
		var st: SurfaceTool = tool_for(key)
		for f2 in faces:
			var a: Vector3 = moved[f2.x]
			var b: Vector3 = moved[f2.y]
			var c: Vector3 = moved[f2.z]
			var n: Vector3 = (b - a).cross(c - a)
			if n.length_squared() < 1e-12:
				continue
			n = n.normalized()
			_vertex(st, a, n, Vector2(a.x, a.z), color)
			_vertex(st, b, n, Vector2(b.x, b.z), color)
			_vertex(st, c, n, Vector2(c.x, c.z), color)

	func _midpoint(verts: Array[Vector3], cache: Dictionary, i: int, j: int) -> int:
		var key: int = (mini(i, j) << 16) | maxi(i, j)
		if cache.has(key):
			return cache[key]
		var v: Vector3 = ((verts[i] + verts[j]) * 0.5).normalized()
		verts.append(v)
		var index: int = verts.size() - 1
		cache[key] = index
		return index

	## Radial bowl from a (radius factor, height, mud blend) profile. Used for
	## the shell crater, which is vertex coloured on the terrain material.
	func bowl(key: String, radius: float, profile: Array[Vector3], segments: int,
			inner: Color, outer: Color, rng: RandomNumberGenerator) -> void:
		var se: int = clampi(segments, 6, 48)
		var rings: int = profile.size()
		# Per segment wobble so the rim is not a perfect circle.
		var wobble: PackedFloat32Array = PackedFloat32Array()
		for j in range(se + 1):
			wobble.append(1.0 if j == se else rng.randf_range(0.86, 1.14))
		wobble[se] = wobble[0]
		for i in range(rings - 1):
			var p0: Vector3 = profile[i]
			var p1: Vector3 = profile[i + 1]
			for j in se:
				var a0: float = TAU * float(j) / float(se)
				var a1: float = TAU * float(j + 1) / float(se)
				var w0: float = wobble[j]
				var w1: float = wobble[j + 1]
				var va: Vector3 = _bowl_point(radius, p0, a0, w0)
				var vb: Vector3 = _bowl_point(radius, p0, a1, w1)
				var vc: Vector3 = _bowl_point(radius, p1, a1, w1)
				var vd: Vector3 = _bowl_point(radius, p1, a0, w0)
				var n0: Vector3 = _bowl_normal(radius, p0, p1, a0)
				var n1: Vector3 = _bowl_normal(radius, p0, p1, a1)
				quad_n(key, va, vb, vc, vd, n0, n1, n1, n0,
						Vector2(va.x, va.z), Vector2(vb.x, vb.z),
						Vector2(vc.x, vc.z), Vector2(vd.x, vd.z),
						inner.lerp(outer, 1.0 - p0.z))

	func _bowl_point(radius: float, p: Vector3, angle: float, wobble: float) -> Vector3:
		var r: float = radius * p.x * wobble
		return Vector3(cos(angle) * r, p.y, sin(angle) * r)

	func _bowl_normal(radius: float, p0: Vector3, p1: Vector3, angle: float) -> Vector3:
		var dr: float = (p1.x - p0.x) * radius
		var dy: float = p1.y - p0.y
		var meridian := Vector2(-dy, dr).normalized()
		return Vector3(cos(angle) * meridian.x, meridian.y,
				sin(angle) * meridian.x).normalized()

	## Single leaning quad: one blade of grass or one ear of wheat.
	func blade(key: String, base: Vector3, width: float, height: float,
			yaw: float, lean: Vector3, color: Color) -> void:
		var dir := Vector3(cos(yaw), 0.0, sin(yaw)) * width * 0.5
		var top: Vector3 = base + Vector3(0.0, height, 0.0) + lean
		var a: Vector3 = base - dir
		var b: Vector3 = base + dir
		var c: Vector3 = top + dir * 0.55
		var d: Vector3 = top - dir * 0.55
		var n: Vector3 = (b - a).cross(c - a)
		if n.length_squared() < 1e-12:
			return
		n = n.normalized()
		var st: SurfaceTool = tool_for(key)
		_vertex(st, a, n, Vector2(0.0, 1.0), color)
		_vertex(st, b, n, Vector2(1.0, 1.0), color)
		_vertex(st, c, n, Vector2(1.0, 0.0), color)
		_vertex(st, a, n, Vector2(0.0, 1.0), color)
		_vertex(st, c, n, Vector2(1.0, 0.0), color)
		_vertex(st, d, n, Vector2(0.0, 0.0), color)

	## One surface per material key, in insertion order.
	func commit() -> ArrayMesh:
		var mesh := ArrayMesh.new()
		for key in _order:
			var st: SurfaceTool = _tools[key]
			st.set_material(MatLib.get_material(key))
			st.commit(mesh)
		return mesh
