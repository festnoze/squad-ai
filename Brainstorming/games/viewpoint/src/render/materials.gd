class_name Materials
## Material factory with a cache, so every box of the same color shares one
## StandardMaterial3D. Ghost variants (for the photo placement preview) are
## transparent, unshaded and cast no shadow, so the preview never darkens the
## scene it is supposed to predict.

static var _cache: Dictionary = {}


static func solid(key: String, emissive := 0.0) -> StandardMaterial3D:
	var cache_key := "s:%s:%.2f" % [key, emissive]
	if _cache.has(cache_key):
		return _cache[cache_key]
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Palette.color(key)
	mat.roughness = 0.85
	if emissive > 0.0:
		mat.emission_enabled = true
		mat.emission = Palette.color(key)
		mat.emission_energy_multiplier = emissive
	_cache[cache_key] = mat
	return mat


static func ghost(key: String) -> StandardMaterial3D:
	var cache_key := "g:%s" % key
	if _cache.has(cache_key):
		return _cache[cache_key]
	var mat := StandardMaterial3D.new()
	var c := Palette.color(key)
	mat.albedo_color = Color(c.r, c.g, c.b, 0.45)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.no_depth_test = false
	mat.disable_receive_shadows = true
	_cache[cache_key] = mat
	return mat


static func backdrop(top_key: String, bottom_key: String) -> StandardMaterial3D:
	var cache_key := "b:%s:%s" % [top_key, bottom_key]
	if _cache.has(cache_key):
		return _cache[cache_key]
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = _gradient_texture(Palette.color(top_key), Palette.color(bottom_key))
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_cache[cache_key] = mat
	return mat


static func _gradient_texture(top: Color, bottom: Color) -> ImageTexture:
	var img := Image.create_empty(4, 64, false, Image.FORMAT_RGBA8)
	for y in 64:
		var c := top.lerp(bottom, float(y) / 63.0)
		img.fill_rect(Rect2i(0, y, 4, 1), c)
	return ImageTexture.create_from_image(img)
