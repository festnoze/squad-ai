class_name PhotoDefs
## Declarative catalog of every photo in the game, plus the computed polaroid
## thumbnails. A photo is pure data: props expressed in camera space (x right,
## y up, -z forward, origin at the player's eye) and an optional backdrop.
##
## The same expansion (expand_prop) feeds both the thumbnail projection and
## the 3D materialization, so what the picture shows is what gets built. Keeping
## defs as plain dictionaries is deliberate: a future in-game camera only has
## to produce the same shape of dictionary (see PRD section 9).
##
## Prop position semantics by kind:
##   box, cylinder : pos is the center of the shape
##   battery       : pos is the base of the battery (it stands on that point)
##   bridge        : pos is the center of the deck
##   stairs        : pos is the front-bottom-center of the flight, which rises
##                   away from the camera (size = width, total rise, total run)
##   arch          : pos is the bottom-center of the portal
##   photo         : pos is the center of a pickable PhotoItem materialized by
##                   the placement (photo-in-photo); "id" names the nested def

const DEFS := {
	"passerelle": {
		"title": "Passerelle",
		"hint": "Une passerelle de bois. Posee droit devant, elle franchit un vide.",
		"props": [
			{"kind": "bridge", "pos": Vector3(0, -1.72, -5.0), "size": Vector3(1.8, 0.24, 8.0), "color": "wood"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
	"pile": {
		"title": "Pile",
		"hint": "Une pile sur son socle. La poser en cree une vraie.",
		"props": [
			{"kind": "box", "pos": Vector3(0, -1.5, -2.4), "size": Vector3(1.1, 0.6, 1.1), "color": "stone"},
			{"kind": "battery", "pos": Vector3(0, -1.2, -2.4), "size": Vector3.ZERO, "color": "battery"},
		],
		"backdrop": {"depth": 8.0, "top": "backdrop_top", "bottom": "backdrop_bottom"},
		"erase_depth": 8.0,
	},
	"escalier": {
		"title": "Escalier",
		"hint": "Une volee de marches. Posee face a un obstacle, elle y grimpe.",
		"props": [
			{"kind": "stairs", "pos": Vector3(0, -1.60, -1.2), "size": Vector3(2.2, 4.6, 7.0), "color": "stone"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
	"porte": {
		"title": "Porte ouverte",
		"hint": "Un mur perce d'une porte. La photo scelle ce qu'elle decoupe.",
		"props": [
			# SEAL WALL: it fills the whole photo frustum cross-section at 6 m
			# (half extent 6 * tan(25) = 2.8), and erase_depth stops just past
			# this plane. Every hole carved in front of it is therefore capped
			# by this wall: no gap to slip through (the "interstice" rule).
			# Opening: 1.6 wide, visible height 2.6 above flat ground (the
			# panels run down to -2.8, sinking into the floor).
			{"kind": "box", "pos": Vector3(-1.8, 0.0, -6.0), "size": Vector3(2.0, 5.6, 0.4), "color": "frame"},
			{"kind": "box", "pos": Vector3(1.8, 0.0, -6.0), "size": Vector3(2.0, 5.6, 0.4), "color": "frame"},
			{"kind": "box", "pos": Vector3(0, 1.89, -6.0), "size": Vector3(1.6, 1.82, 0.4), "color": "frame"},
			# Door casing accents around the opening.
			{"kind": "box", "pos": Vector3(-0.86, -0.32, -5.95), "size": Vector3(0.12, 2.6, 0.5), "color": "accent"},
			{"kind": "box", "pos": Vector3(0.86, -0.32, -5.95), "size": Vector3(0.12, 2.6, 0.5), "color": "accent"},
			{"kind": "box", "pos": Vector3(0, 1.04, -5.95), "size": Vector3(1.84, 0.12, 0.5), "color": "accent"},
			# The leaf, slid open in front of the left panel.
			{"kind": "box", "pos": Vector3(-1.7, -0.32, -5.62), "size": Vector3(1.6, 2.6, 0.08), "color": "wood_dark"},
		],
		"backdrop": {},
		"erase_depth": 6.2,
	},
	"console": {
		"title": "Console",
		"hint": "Une dalle decentree vers le bas. Tournee a 180, elle passe en hauteur.",
		"props": [
			{"kind": "box", "pos": Vector3(0, -0.6, -3.0), "size": Vector3(2.0, 0.3, 2.0), "color": "teal"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
	"corniche": {
		"title": "Corniche",
		"hint": "Une dalle decalee en bas a droite. Tournee a 180 : en haut a gauche.",
		"props": [
			{"kind": "box", "pos": Vector3(1.6, -0.6, -3.2), "size": Vector3(1.8, 0.3, 1.8), "color": "accent"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
	"caisse": {
		"title": "Caisse",
		"hint": "Un cube d'un bon metre. Un appui simple, toujours utile.",
		"props": [
			{"kind": "box", "pos": Vector3(0, -0.97, -2.6), "size": Vector3(1.3, 1.3, 1.3), "color": "wood"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
	"coffret": {
		"title": "Coffret",
		"hint": "Un socle qui porte une autre photo. Poser, puis ramasser ce qui apparait.",
		"props": [
			{"kind": "box", "pos": Vector3(0, -1.35, -2.6), "size": Vector3(1.0, 0.55, 1.0), "color": "stone"},
			{"kind": "photo", "pos": Vector3(0, -0.55, -2.6), "size": Vector3.ZERO, "color": "frame", "id": "pile"},
		],
		"backdrop": {},
		"erase_depth": 12.0,
	},
}

const THUMB_SIZE := 256
## Square picture area inside the polaroid frame, in pixels.
const THUMB_INNER := Rect2i(24, 16, 208, 208)

static var _thumb_cache: Dictionary = {}


static func all_ids() -> PackedStringArray:
	var ids := PackedStringArray()
	for id in DEFS.keys():
		ids.append(id)
	ids.sort()
	return ids


static func get_def(id: String) -> Dictionary:
	return DEFS.get(id, {})


## How many real batteries materialize when this photo is placed.
static func battery_count(id: String) -> int:
	var total := 0
	for prop in get_def(id).get("props", []):
		if prop["kind"] == "battery":
			total += 1
	return total


## Batteries reachable through this photo, following nested photo props
## (photo-in-photo chains). The visited set guards against catalog cycles.
static func battery_count_recursive(id: String, visited: Dictionary = {}) -> int:
	if visited.has(id):
		return 0
	visited[id] = true
	var total := battery_count(id)
	for prop in get_def(id).get("props", []):
		if prop["kind"] == "photo":
			total += battery_count_recursive(prop["id"], visited)
	return total


## Expands one prop into drawable/buildable primitives:
## an array of {kind: "box"|"cylinder"|"battery", center, size, color}.
static func expand_prop(prop: Dictionary) -> Array:
	var pos: Vector3 = prop["pos"]
	var size: Vector3 = prop.get("size", Vector3.ZERO)
	var color: String = prop.get("color", "stone")
	match prop["kind"]:
		"box", "cylinder":
			return [{"kind": prop["kind"], "center": pos, "size": size, "color": color}]
		"battery":
			return [{"kind": "battery", "center": pos + Vector3(0, 0.35, 0), "size": Vector3(0.36, 0.7, 0.36), "color": "battery"}]
		"photo":
			return [{"kind": "photo_item", "center": pos, "size": Vector3(0.72, 0.82, 0.06), "color": "frame", "photo_id": prop["id"]}]
		"bridge":
			var rail_y: float = pos.y + size.y * 0.5 + 0.4
			return [
				{"kind": "box", "center": pos, "size": size, "color": color},
				{"kind": "box", "center": Vector3(pos.x - size.x * 0.5 + 0.05, rail_y, pos.z), "size": Vector3(0.1, 0.8, size.z), "color": "wood_dark"},
				{"kind": "box", "center": Vector3(pos.x + size.x * 0.5 - 0.05, rail_y, pos.z), "size": Vector3(0.1, 0.8, size.z), "color": "wood_dark"},
			]
		"stairs":
			var out: Array = []
			var steps := 8
			var step_h := size.y / steps
			var step_d := size.z / steps
			for i in steps:
				var top := (i + 1) * step_h
				out.append({
					"kind": "box",
					"center": Vector3(pos.x, pos.y + top * 0.5, pos.z - (i + 0.5) * step_d),
					"size": Vector3(size.x, top, step_d),
					"color": color,
				})
			return out
		"arch":
			var col_h := size.y - 0.4
			return [
				{"kind": "box", "center": Vector3(pos.x - size.x * 0.5 + 0.25, pos.y + col_h * 0.5, pos.z), "size": Vector3(0.5, col_h, size.z), "color": color},
				{"kind": "box", "center": Vector3(pos.x + size.x * 0.5 - 0.25, pos.y + col_h * 0.5, pos.z), "size": Vector3(0.5, col_h, size.z), "color": color},
				{"kind": "box", "center": Vector3(pos.x, pos.y + size.y - 0.2, pos.z), "size": Vector3(size.x, 0.4, size.z), "color": color},
			]
	push_warning("PhotoDefs: unknown prop kind '%s'" % str(prop["kind"]))
	return []


static func expand_props(def: Dictionary) -> Array:
	var out: Array = []
	for prop in def.get("props", []):
		out.append_array(expand_prop(prop))
	return out


## Computed polaroid picture of the photo content: pinhole projection of every
## primitive onto the photo plane, painter-sorted back to front.
static func thumbnail(id: String) -> ImageTexture:
	if _thumb_cache.has(id):
		return _thumb_cache[id]
	var def := get_def(id)
	var img := Image.create_empty(THUMB_SIZE, THUMB_SIZE, false, Image.FORMAT_RGBA8)
	img.fill(Palette.color("frame"))

	var backdrop: Dictionary = def.get("backdrop", {})
	var top_c := Palette.color(backdrop.get("top", "sky_top"))
	var bottom_c := Palette.color(backdrop.get("bottom", "sky_horizon"))
	for y in THUMB_INNER.size.y:
		var c := top_c.lerp(bottom_c, float(y) / float(THUMB_INNER.size.y - 1))
		img.fill_rect(Rect2i(THUMB_INNER.position.x, THUMB_INNER.position.y + y, THUMB_INNER.size.x, 1), c)

	var prims := expand_props(def)
	prims.sort_custom(func(a, b): return a["center"].z < b["center"].z)
	for prim in prims:
		_draw_prim(img, prim)

	var tex := ImageTexture.create_from_image(img)
	_thumb_cache[id] = tex
	return tex


static func _draw_prim(img: Image, prim: Dictionary) -> void:
	var center: Vector3 = prim["center"]
	var size: Vector3 = prim["size"]
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for sx in [-0.5, 0.5]:
		for sy in [-0.5, 0.5]:
			for sz in [-0.5, 0.5]:
				var corner := center + Vector3(size.x * sx, size.y * sy, size.z * sz)
				if corner.z > -0.05:
					continue
				var p := PhotoMath.project_point(corner, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT)
				lo = Vector2(minf(lo.x, p.x), minf(lo.y, p.y))
				hi = Vector2(maxf(hi.x, p.x), maxf(hi.y, p.y))
	if lo.x > hi.x:
		return
	var rect := _to_pixels(lo, hi)
	rect = rect.intersection(THUMB_INNER)
	if not rect.has_area():
		return
	var depth := clampf(-center.z / 16.0, 0.0, 0.35)
	var color := Palette.color(prim["color"]).darkened(depth)
	if prim["kind"] == "battery":
		var tip_h := maxi(int(rect.size.y * 0.2), 1)
		img.fill_rect(Rect2i(rect.position.x, rect.position.y, rect.size.x, tip_h), Palette.color("battery_tip"))
		img.fill_rect(Rect2i(rect.position.x, rect.position.y + tip_h, rect.size.x, rect.size.y - tip_h), color)
	elif prim["kind"] == "photo_item":
		# A polaroid inside the picture: white frame around a darker inset.
		img.fill_rect(rect, color)
		var inset := rect.grow(-maxi(rect.size.x / 6, 1))
		if inset.has_area():
			img.fill_rect(inset, Palette.color("photo_back").darkened(depth))
	else:
		img.fill_rect(rect, color)


## Maps normalized photo coordinates ([-1, 1], y up) to a pixel rect inside
## the polaroid picture area.
static func _to_pixels(lo: Vector2, hi: Vector2) -> Rect2i:
	var x0 := THUMB_INNER.position.x + int((lo.x * 0.5 + 0.5) * THUMB_INNER.size.x)
	var x1 := THUMB_INNER.position.x + int((hi.x * 0.5 + 0.5) * THUMB_INNER.size.x)
	var y0 := THUMB_INNER.position.y + int((1.0 - (hi.y * 0.5 + 0.5)) * THUMB_INNER.size.y)
	var y1 := THUMB_INNER.position.y + int((1.0 - (lo.y * 0.5 + 0.5)) * THUMB_INNER.size.y)
	return Rect2i(x0, y0, maxi(x1 - x0, 1), maxi(y1 - y0, 1))
