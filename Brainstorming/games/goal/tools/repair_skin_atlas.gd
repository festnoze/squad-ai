extends SceneTree
## Repairs the keeper's face atlas in place.
##
##   godot --headless --path . --script res://tools/repair_skin_atlas.gd
##   godot --headless --path . --script res://tools/repair_skin_atlas.gd -- --write
##
## Without --write it only measures and reports, which is the mode to run first.
##
## THE DEFECT. `assets/textures/characters/keeper_skin_albedo.png` was generated
## for this project, and the generator laid its islands - the face, the eyes, the
## chin, the nostrils - on a flat BRICK RUST field that covers most of the sheet.
## Two things follow from that field, and both are visible on a portrait:
##
##  1. Every UV that lands outside an island samples the rust. MakeHuman's head
##     unwraps the whole cranium, not just the face, so the BACK OF THE SKULL and
##     both temples read as a flat rust-mauve mass next to a photographed face.
##  2. The rust also bled INTO the face island while it was composited: streaks
##     of it sit across the brow, the temple and the jaw, where they read as
##     mottled rust blotches on the skin.
##
## One repair answers both, because both are the same pixel: every pixel within
## `TOLERANCE` of the background colour is treated as a HOLE and inpainted.
##
## THE INPAINT is a grassfire from the island edges, and it is deliberately not a
## flat fill. A hole pixel takes the mean of its already-solved neighbours, so a
## streak in the middle of a cheek is repaired with THAT cheek's skin and vanishes
## rather than becoming a patch. Over `FEATHER` rings the fill also ramps towards
## the mean skin tone of the sheet, so by the time the frontier is that far out it
## has already arrived at plain skin and the flood that finishes the job cannot
## show a step.
##
## The frontier is walked as a ring, never as the whole image, so the cost is the
## number of pixels actually repaired near an island and not `FEATHER` full
## passes over four megapixels.
##
## The background colour is MEASURED, not typed in: the modal colour of a 5 bit
## quantisation of the sheet. On an image this empty the mode is the field by a
## wide margin, and the report prints its share so a re-generated atlas that no
## longer has one is obvious rather than silently mangled.

const SOURCE := "assets/textures/characters/keeper_skin_albedo.png"

## How far from the measured background colour a pixel may sit and still count as
## background, as a euclidean distance in unit RGB.
##
## A THRESHOLD ALONE CANNOT DO THIS JOB, and the sweep that proves it is worth
## keeping: from 0.04 to 0.18 the share of the sheet claimed climbs smoothly from
## 86.5 % to 97.2 % and the closest surviving pixel sits exactly ON the threshold
## at every step. There is no gap to cut in, because the generator feathered the
## rust into the islands and because this is a DARK SKINNED face: a shadow under
## the brow is (0.30, 0.20, 0.16), which is 0.065 from the rust. Any threshold
## loose enough to catch the bleed is loose enough to punch holes in the cheeks.
##
## So the threshold is only ever used with a second condition beside it, and the
## field and the bleed are found by two different means.
##
##  - THE FIELD is the flat rust itself, at a TIGHT tolerance. It is uniform, so
##    0.05 already claims all of it. Connectivity from the border is kept as a
##    cheap guard against a rust coloured patch INSIDE a cheek being swept up with
##    it, but it is not what makes the tolerance safe: the tightness is.
##
##    CONNECTIVITY AT THE LOOSE TOLERANCE DOES NOT WORK, and the attempt is worth
##    recording. The generator feathered the rust into the islands, so there is a
##    continuous ramp from the field to the skin; a flood allowed 0.14 walks up
##    that ramp, arrives inside the face, and from there every brow shadow is in
##    range of every other. It ate most of the cheeks and left a lace curtain.
##
##  - THE RIM, the feathered band the tight tolerance leaves behind, is removed by
##    MORPHOLOGY and not by colour: the field is simply DILATED `RIM` pixels into
##    the islands. Those pixels are contaminated by construction, the islands are
##    hundreds of pixels across, and a fixed erosion cannot chase a gradient
##    inwards however dark the skin gets.
##
##  - THE BLEED, the rust streaks sitting inside an island, is found by colour AND
##    by RED BIAS. The face averages (0.300, 0.229, 0.208), which is very nearly
##    neutral, while the rust runs 0.232 redder than it is blue. Asking for most
##    of that bias spares the neutral shadows and still catches the streaks across
##    the brow and the jaw.
const TOLERANCE := 0.05
## Colour tolerance used for the bleed, where the red bias does the real work.
const BLEED_TOLERANCE := 0.14
## Share of the field's own red bias (r - b) a pixel must carry before it counts
## as rust that bled into an island.
const BLEED_RED_SHARE := 0.85
## Pixels of feathered rim eroded off every island edge.
const RIM := 4
## Distance between the field colour and the mean of the content below which the
## sheet is taken to be already repaired and the tool refuses to touch it. See the
## refusal in `_initialize` for why that matters.
const REPAIRED_GAP := 0.05
## Rings of grassfire before the fill has fully become the mean skin tone.
const FEATHER := 28
## Quantisation of the histogram used to find the background, in levels per
## channel.
const BUCKETS := 32


## Live tolerance, TOLERANCE unless --tol=X overrides it. The sweep that picked
## the constant is worth being able to re-run: the honest way to choose it is to
## watch the share of the sheet it claims stop moving.
var _tolerance: float = TOLERANCE


func _initialize() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var write: bool = args.has("--write")
	for arg in args:
		if arg.begins_with("--tol="):
			_tolerance = maxf(arg.substr(6).to_float(), 0.0)
	_say("tolerance      : %.3f" % _tolerance)
	var path: String = ProjectSettings.globalize_path("res://").path_join(SOURCE)
	if not FileAccess.file_exists(path):
		_say("ERREUR: %s est introuvable." % SOURCE)
		quit(1)
		return

	var image: Image = Image.load_from_file(path)
	if image == null:
		_say("ERREUR: %s n'a pas pu etre lu." % SOURCE)
		quit(1)
		return
	image.convert(Image.FORMAT_RGBA8)
	var w: int = image.get_width()
	var h: int = image.get_height()
	_say("atlas %d x %d" % [w, h])

	var background: Color = _modal_colour(image)
	var mask: PackedByteArray = _hole_mask(image, background)
	var holes: int = _count(mask)
	var total: int = w * h
	_say("fond mesure    : (%.3f, %.3f, %.3f)" % [background.r, background.g, background.b])
	_say("pixels de fond : %d / %d (%.1f %%)" % [holes, total, 100.0 * float(holes) / float(total)])
	_say("  dont champ plat (connexite)      : %d" % _field_pixels)
	_say("  dont frange erodee (%d px)        : %d" % [RIM, _rim_pixels])
	_say("  dont bavure dans les ilots       : %d" % _bleed_pixels)

	if holes == 0:
		_say("rien a reparer : cet atlas n'a plus de fond uni.")
		quit(0)
		return
	if holes == total:
		_say("ERREUR: tout l'atlas est classe en fond, la tolerance est trop large.")
		quit(1)
		return

	var skin: Color = _mean_kept(image, mask)
	_say("peau moyenne   : (%.3f, %.3f, %.3f)" % [skin.r, skin.g, skin.b])
	_say("marge la plus faible d'un pixel garde au fond : %.3f" % _closest_kept(image, mask, background))

	# ALREADY REPAIRED? REFUSE. This tool is destructive and in place, and it is
	# NOT idempotent: a second run measures the skin tone it just flooded the sheet
	# with as the new "background", erodes another RIM off every island and
	# diffuses into what is left. Run it three times and the face is gone.
	#
	# The tell is that the field and the content have become the same colour, which
	# is exactly what the repair does and exactly what a generator's rust field is
	# not. Measured, not assumed: 0.088 apart on the atlas as generated, 0.028
	# apart once repaired, and the number is printed either way.
	var settled: float = Vector3(background.r - skin.r, background.g - skin.g,
		background.b - skin.b).length()
	_say("ecart fond / contenu : %.3f (repare en dessous de %.3f)" % [settled, REPAIRED_GAP])
	if settled < REPAIRED_GAP:
		_say("")
		_say("cet atlas est deja repare : son fond EST son teint moyen. Rien a faire.")
		quit(0)
		return

	if not write:
		_say("")
		_say("mesure seule. Relancer avec -- --write pour ecrire la reparation.")
		quit(0)
		return

	var filled: int = _inpaint(image, mask, skin)
	_say("pixels reconstruits par diffusion : %d" % filled)
	_say("pixels restants remplis en peau   : %d" % _flood_rest(image, mask, skin))
	if image.save_png(path) != OK:
		_say("ERREUR: ecriture de %s impossible." % SOURCE)
		quit(1)
		return
	_say("ecrit : %s" % SOURCE)
	quit(0)


# --- measurement --------------------------------------------------------------

## The modal colour of the sheet, on a `BUCKETS` per channel quantisation.
func _modal_colour(image: Image) -> Color:
	var counts: Dictionary = {}
	var best_key: int = -1
	var best_count: int = 0
	for y in image.get_height():
		for x in image.get_width():
			var c: Color = image.get_pixel(x, y)
			var key: int = _bucket(c)
			var n: int = int(counts.get(key, 0)) + 1
			counts[key] = n
			if n > best_count:
				best_count = n
				best_key = key
	# The bucket centre is coarse, so the answer is refined into the true mean of
	# every pixel that fell in it. A background painted with a little noise then
	# comes back as its own average rather than as a lattice point.
	var sum := Vector3.ZERO
	var seen: int = 0
	for y in image.get_height():
		for x in image.get_width():
			var c: Color = image.get_pixel(x, y)
			if _bucket(c) == best_key:
				sum += Vector3(c.r, c.g, c.b)
				seen += 1
	if seen == 0:
		return Color.BLACK
	sum /= float(seen)
	return Color(sum.x, sum.y, sum.z)


func _bucket(c: Color) -> int:
	var r: int = clampi(int(c.r * float(BUCKETS)), 0, BUCKETS - 1)
	var g: int = clampi(int(c.g * float(BUCKETS)), 0, BUCKETS - 1)
	var b: int = clampi(int(c.b * float(BUCKETS)), 0, BUCKETS - 1)
	return (r * BUCKETS + g) * BUCKETS + b


## The field, flooded in from the border, plus the rust that bled into the
## islands. See TOLERANCE for why neither half is a threshold on its own.
func _hole_mask(image: Image, background: Color) -> PackedByteArray:
	var w: int = image.get_width()
	var h: int = image.get_height()
	var mask := PackedByteArray()
	mask.resize(w * h)

	# --- the field, by connectivity ------------------------------------------
	var queue := PackedInt32Array()
	for x in w:
		_seed(image, mask, queue, background, x, 0, w)
		_seed(image, mask, queue, background, x, h - 1, w)
	for y in h:
		_seed(image, mask, queue, background, 0, y, w)
		_seed(image, mask, queue, background, w - 1, y, w)

	var head: int = 0
	while head < queue.size():
		var index: int = queue[head]
		head += 1
		var x: int = index % w
		var y: int = int(index / w)
		for step in _NEIGHBOURS:
			var nx: int = x + step.x
			var ny: int = y + step.y
			if nx < 0 or ny < 0 or nx >= w or ny >= h:
				continue
			if mask[ny * w + nx] == 1:
				continue
			if not _near(image.get_pixel(nx, ny), background):
				continue
			mask[ny * w + nx] = 1
			queue.append(ny * w + nx)
	_field_pixels = queue.size()

	# --- the feathered rim, by erosion ---------------------------------------
	_rim_pixels = 0
	for _ring in RIM:
		var grown := PackedInt32Array()
		for y in h:
			for x in w:
				if mask[y * w + x] == 1:
					continue
				if _touches_field(mask, w, h, x, y):
					grown.append(y * w + x)
		for index in grown:
			mask[index] = 1
		_rim_pixels += grown.size()

	# --- the bleed, by colour and by red bias --------------------------------
	var bias: float = maxf(background.r - background.b, 0.0) * BLEED_RED_SHARE
	_bleed_pixels = 0
	for y in h:
		for x in w:
			if mask[y * w + x] == 1:
				continue
			var c: Color = image.get_pixel(x, y)
			if Vector3(c.r - background.r, c.g - background.g,
					c.b - background.b).length() > BLEED_TOLERANCE:
				continue
			if c.r - c.b < bias:
				continue
			mask[y * w + x] = 1
			_bleed_pixels += 1
	return mask


func _touches_field(mask: PackedByteArray, w: int, h: int, x: int, y: int) -> bool:
	for step in _NEIGHBOURS:
		var nx: int = x + step.x
		var ny: int = y + step.y
		if nx < 0 or ny < 0 or nx >= w or ny >= h:
			continue
		if mask[ny * w + nx] == 1:
			return true
	return false


## Report only: how the three parts of the mask split.
var _field_pixels: int = 0
var _rim_pixels: int = 0
var _bleed_pixels: int = 0


func _seed(image: Image, mask: PackedByteArray, queue: PackedInt32Array,
		background: Color, x: int, y: int, w: int) -> void:
	var index: int = y * w + x
	if mask[index] == 1:
		return
	if not _near(image.get_pixel(x, y), background):
		return
	mask[index] = 1
	queue.append(index)


func _near(c: Color, background: Color) -> bool:
	return Vector3(c.r - background.r, c.g - background.g,
		c.b - background.b).length() <= _tolerance


func _count(mask: PackedByteArray) -> int:
	var n: int = 0
	for v in mask:
		if v == 1:
			n += 1
	return n


## Mean colour of everything the mask KEEPS: the real content of the sheet.
func _mean_kept(image: Image, mask: PackedByteArray) -> Color:
	var w: int = image.get_width()
	var sum := Vector3.ZERO
	var seen: int = 0
	for y in image.get_height():
		for x in w:
			if mask[y * w + x] == 1:
				continue
			var c: Color = image.get_pixel(x, y)
			sum += Vector3(c.r, c.g, c.b)
			seen += 1
	if seen == 0:
		return Color.BLACK
	sum /= float(seen)
	return Color(sum.x, sum.y, sum.z)


## Distance from the background of the KEPT pixel that sits closest to it. This is
## the safety margin of TOLERANCE, and printing it is the only honest way to show
## that the threshold did not eat into the real face.
func _closest_kept(image: Image, mask: PackedByteArray, background: Color) -> float:
	var w: int = image.get_width()
	var best: float = 1.0e9
	for y in image.get_height():
		for x in w:
			if mask[y * w + x] == 1:
				continue
			var c: Color = image.get_pixel(x, y)
			best = minf(best, Vector3(c.r - background.r, c.g - background.g,
				c.b - background.b).length())
	return best


# --- repair -------------------------------------------------------------------

## Grassfire inpaint. Returns the number of pixels it solved.
func _inpaint(image: Image, mask: PackedByteArray, skin: Color) -> int:
	var w: int = image.get_width()
	var h: int = image.get_height()

	# The starting frontier: every hole touching content.
	var frontier := PackedInt32Array()
	for y in h:
		for x in w:
			if mask[y * w + x] == 1 and _touches_kept(mask, w, h, x, y):
				frontier.append(y * w + x)

	var solved: int = 0
	for ring in FEATHER:
		if frontier.is_empty():
			break
		# How far the fill has already travelled towards plain skin. The last ring
		# is pure skin, so the flood that follows joins onto it without a step.
		var towards: float = float(ring + 1) / float(FEATHER)
		var colours: PackedColorArray = PackedColorArray()
		for index in frontier:
			var x: int = index % w
			var y: int = int(index / w)
			colours.append(_neighbour_mean(image, mask, w, h, x, y).lerp(skin, towards))
		for i in frontier.size():
			var index: int = frontier[i]
			image.set_pixel(index % w, int(index / w), colours[i])
		for index in frontier:
			mask[index] = 0
		solved += frontier.size()

		var next := PackedInt32Array()
		var queued: Dictionary = {}
		for index in frontier:
			var x: int = index % w
			var y: int = int(index / w)
			for step in _NEIGHBOURS:
				var nx: int = x + int(step.x)
				var ny: int = y + int(step.y)
				if nx < 0 or ny < 0 or nx >= w or ny >= h:
					continue
				var n_index: int = ny * w + nx
				if mask[n_index] == 1 and not queued.has(n_index):
					queued[n_index] = true
					next.append(n_index)
		frontier = next
	return solved


const _NEIGHBOURS: Array[Vector2i] = [
	Vector2i(-1, -1), Vector2i(0, -1), Vector2i(1, -1),
	Vector2i(-1, 0), Vector2i(1, 0),
	Vector2i(-1, 1), Vector2i(0, 1), Vector2i(1, 1),
]


func _touches_kept(mask: PackedByteArray, w: int, h: int, x: int, y: int) -> bool:
	for step in _NEIGHBOURS:
		var nx: int = x + step.x
		var ny: int = y + step.y
		if nx < 0 or ny < 0 or nx >= w or ny >= h:
			continue
		if mask[ny * w + nx] == 0:
			return true
	return false


func _neighbour_mean(image: Image, mask: PackedByteArray, w: int, h: int, x: int, y: int) -> Color:
	var sum := Vector3.ZERO
	var seen: int = 0
	for step in _NEIGHBOURS:
		var nx: int = x + step.x
		var ny: int = y + step.y
		if nx < 0 or ny < 0 or nx >= w or ny >= h:
			continue
		if mask[ny * w + nx] == 1:
			continue
		var c: Color = image.get_pixel(nx, ny)
		sum += Vector3(c.r, c.g, c.b)
		seen += 1
	if seen == 0:
		return Color.BLACK
	sum /= float(seen)
	return Color(sum.x, sum.y, sum.z)


## Everything the grassfire never reached: the wide empty field far from any
## island. It is plain skin, which is the point - a UV that lands out there now
## reads as a bare patch of the man rather than as a rust stain.
func _flood_rest(image: Image, mask: PackedByteArray, skin: Color) -> int:
	var w: int = image.get_width()
	var n: int = 0
	for y in image.get_height():
		for x in w:
			if mask[y * w + x] == 0:
				continue
			image.set_pixel(x, y, skin)
			mask[y * w + x] = 0
			n += 1
	return n


func _say(text: String) -> void:
	print(text)
