class_name PhotoSnaps
extends Node
## Offscreen renderer of the photo pictures. For each photo definition it
## builds the DISPLAY variant of the content in a private world and renders it
## with a square camera whose fov equals the placement frustum: the picture on
## the polaroid is therefore the exact same view the solid content produces
## once placed. That identity is what makes the raised photo (right click)
## blend into the world at the moment of placement.
##
## Falls back gracefully: while a render is pending, or under --headless
## (dummy rasterizer, no pixels), get_texture serves the deterministic drawn
## thumbnail from PhotoDefs instead.

static var instance: PhotoSnaps

var _viewport: SubViewport
var _camera: Camera3D
var _content_root: Node3D
var _cache: Dictionary = {}
var _rendering := false
var _queue: PackedStringArray = PackedStringArray()

const SNAP_SIZE := 512
const BORDER := 24
const BOTTOM := 48


static func get_texture(id: String) -> Texture2D:
	if instance != null and instance._cache.has(id):
		return instance._cache[id]
	return PhotoDefs.thumbnail(id)


static func request(id: String) -> void:
	if instance != null:
		instance._enqueue(id)


func _ready() -> void:
	instance = self
	if DisplayServer.get_name() == "headless":
		return

	_viewport = SubViewport.new()
	_viewport.size = Vector2i(SNAP_SIZE, SNAP_SIZE)
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(_viewport)

	# A private little sky so the picture background matches the game's.
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Palette.color("sky_top")
	sky_mat.sky_horizon_color = Palette.color("sky_horizon")
	sky_mat.ground_bottom_color = Palette.color("sky_horizon").darkened(0.15)
	sky_mat.ground_horizon_color = Palette.color("sky_horizon")
	var sky := Sky.new()
	sky.sky_material = sky_mat
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 0.7
	env.ambient_light_energy = 1.1
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var world_env := WorldEnvironment.new()
	world_env.environment = env
	_viewport.add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-40, 30, 0)
	sun.light_energy = 1.15
	sun.light_color = Color(1, 0.96, 0.88)
	_viewport.add_child(sun)

	_camera = Camera3D.new()
	_camera.fov = PhotoMath.PHOTO_FOV_DEG
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.05
	_viewport.add_child(_camera)

	_content_root = Node3D.new()
	_viewport.add_child(_content_root)

	for id in PhotoDefs.all_ids():
		_enqueue(id)


func _enqueue(id: String) -> void:
	if _viewport == null or _cache.has(id) or _queue.has(id):
		return
	_queue.append(id)
	if not _rendering:
		_drain_queue()


func _drain_queue() -> void:
	_rendering = true
	while not _queue.is_empty():
		var id := _queue[0]
		_queue.remove_at(0)
		await _render_one(id)
	_rendering = false


func _render_one(id: String) -> void:
	var def := PhotoDefs.get_def(id)
	if def.is_empty():
		return
	for child in _content_root.get_children():
		child.free()
	var content := PhotoContent.new()
	content.setup(def, false, true)
	_content_root.add_child(content)

	_viewport.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var img := _viewport.get_texture().get_image()
	if img == null or img.is_empty():
		return
	img.convert(Image.FORMAT_RGBA8)
	_frame_polaroid(img)
	_cache[id] = ImageTexture.create_from_image(img)


## Paints the white polaroid border straight onto the render.
func _frame_polaroid(img: Image) -> void:
	var w := img.get_width()
	var h := img.get_height()
	var frame := Palette.color("frame")
	img.fill_rect(Rect2i(0, 0, w, BORDER), frame)
	img.fill_rect(Rect2i(0, h - BOTTOM, w, BOTTOM), frame)
	img.fill_rect(Rect2i(0, 0, BORDER, h), frame)
	img.fill_rect(Rect2i(w - BORDER, 0, BORDER, h), frame)
