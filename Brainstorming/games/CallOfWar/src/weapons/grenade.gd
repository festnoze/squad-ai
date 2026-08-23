## A thrown Mk 2 grenade: a small heavy rigid body with a burning fuse.
##
## It bounces badly on purpose (low restitution, high friction) so it stays
## where it lands instead of rolling down a hill, and it reports its contacts
## so a hard bounce off a wall makes the metallic clink that tells the player
## the throw came back at him.
##
## The blast itself is not computed here: `Ballistics.explode()` owns the
## falloff, the line of sight checks and the push, exactly like every other
## explosion in the game.
class_name Grenade
extends RigidBody3D

const FUSE := 3.6
## Collision sphere radius, in metres.
const BODY_RADIUS := 0.09
const BODY_MASS := 0.6
const BLAST_RADIUS := 9.0
const BLAST_DAMAGE := 130.0
## A contact below this speed is a roll, not a bounce: no sound.
const BOUNCE_SPEED := 2.4
const BOUNCE_COOLDOWN := 0.18

var _thrower: Node = null
var _fuse_left: float = FUSE
var _detonated: bool = false
var _pending_impulse: Vector3 = Vector3.ZERO
var _impulse_applied: bool = true
var _bounce_cooldown: float = 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.randomize()
	_build_body()
	if not is_in_group("grenade"):
		add_to_group("grenade")
	if not _impulse_applied:
		_impulse_applied = true
		apply_central_impulse(_pending_impulse)
	body_entered.connect(_on_body_entered)


## Arms the grenade and throws it. Safe to call before or after the grenade is
## added to the tree: the impulse waits for the body to exist.
func setup(thrower: Node, impulse: Vector3) -> void:
	_thrower = thrower
	_fuse_left = FUSE
	_detonated = false
	_pending_impulse = impulse
	if is_inside_tree():
		_impulse_applied = true
		apply_central_impulse(impulse)
		_add_thrower_exception()
	else:
		_impulse_applied = false


## Seconds of fuse left, for a cooking indicator on the HUD.
func time_left() -> float:
	return maxf(_fuse_left, 0.0)


func thrower() -> Node:
	return _thrower


func _physics_process(delta: float) -> void:
	if _bounce_cooldown > 0.0:
		_bounce_cooldown -= delta
	if _detonated:
		return
	_fuse_left -= delta
	if _fuse_left <= 0.0:
		detonate()


## Blast, effect, sound, then gone. Idempotent: a grenade caught by another
## explosion first does not detonate twice.
func detonate() -> void:
	if _detonated:
		return
	_detonated = true
	var here := global_position
	Ballistics.explode(get_world_3d(), here, BLAST_RADIUS, BLAST_DAMAGE, _thrower)
	var vfx_nodes := get_tree().get_nodes_in_group("vfx")
	if not vfx_nodes.is_empty():
		var vfx: Node = vfx_nodes[0]
		vfx.call("explosion", here, BLAST_RADIUS)
	_play_sound("explosion", here, 0.0, _rng.randf_range(0.93, 1.07))
	queue_free()

# --- Body ------------------------------------------------------------------

func _build_body() -> void:
	mass = BODY_MASS
	gravity_scale = 1.0
	continuous_cd = true
	contact_monitor = true
	max_contacts_reported = 4
	can_sleep = true
	collision_layer = Layers.PROP
	collision_mask = Layers.TERRAIN | Layers.STRUCTURE | Layers.PROP | Layers.VEHICLE

	var physics := PhysicsMaterial.new()
	physics.bounce = 0.20
	physics.friction = 0.90
	physics.rough = true
	physics_material_override = physics

	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = BODY_RADIUS
	shape.shape = sphere
	shape.name = "Body"
	add_child(shape)

	var visual := MeshInstance3D.new()
	visual.name = "Model"
	visual.mesh = _grenade_mesh()
	visual.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(visual)


func _grenade_mesh() -> Mesh:
	var mesh: Mesh = Meshes.weapon_model(WeaponDefs.GRENADE)
	if mesh != null:
		return mesh
	var body := CylinderMesh.new()
	body.top_radius = 0.045
	body.bottom_radius = 0.045
	body.height = 0.11
	body.radial_segments = 8
	body.rings = 1
	body.material = _metal()
	return body


func _metal() -> Material:
	var mat: Material = MatLib.get_material("gun_metal")
	if mat != null:
		return mat
	var fallback := StandardMaterial3D.new()
	fallback.albedo_color = Palette.METAL
	fallback.metallic = 0.45
	fallback.roughness = 0.55
	return fallback


## The thrower must not be knocked around by his own grenade the instant it
## leaves his hand.
func _add_thrower_exception() -> void:
	var body := _thrower as CollisionObject3D
	if body != null:
		add_collision_exception_with(body)

# --- Contacts --------------------------------------------------------------

func _on_body_entered(_body: Node) -> void:
	if _detonated or _bounce_cooldown > 0.0:
		return
	var speed := linear_velocity.length()
	if speed < BOUNCE_SPEED:
		return
	_bounce_cooldown = BOUNCE_COOLDOWN
	var loudness: float = clampf(-14.0 + speed * 1.2, -14.0, -4.0)
	_play_sound("impact_metal", global_position, loudness, _rng.randf_range(1.15, 1.45))

# --- Audio -----------------------------------------------------------------

## Goes through the autoload by path rather than by name, so this file still
## compiles in a context without autoloads (the headless unit runner) and a
## grenade can be instantiated in a test without a sound bank.
func _play_sound(sample: String, at: Vector3, volume_db: float, pitch: float) -> void:
	var player := get_node_or_null(^"/root/Sfx")
	if player == null or not player.has_method("play_at"):
		return
	player.call("play_at", sample, at, volume_db, pitch)
