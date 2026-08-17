extends TestCase
## Procedural texture atlas: layer layout, tile geometry, tileability, the alpha
## budget, the greyscale of the biome tinted tiles, determinism and the 2D
## previews of the interface.
##
## Not a single check looks at an actual colour. The palette is tuned by hand and
## keeps moving, so every property asserted here is structural: a size, a spread,
## a seam, an alpha count. A repaint of stone therefore never breaks the suite,
## while a tile that goes flat, opaque, non tileable or non deterministic does.

const S := Blocks.TILE_PIXELS

## Tiles the contract requires to carry holes: window centre, foliage, plants and
## the torch silhouette. Every other tile must be opaque on all 1024 pixels.
const TRANSPARENT_TILES: PackedStringArray = [
	"glass",
	"oak_leaves", "birch_leaves", "pine_leaves",
	"grass_tuft", "fern", "dead_bush",
	"flower_red", "flower_yellow", "sapling", "torch",
]

## Side faces painted as a cover layer spilling down over dirt. They repeat
## horizontally, but the top of the tile is grass and the bottom is soil by
## design, so the vertical seam test does not apply to them.
const NO_VERTICAL_WRAP: PackedStringArray = ["grass_side", "snow_side"]

## Minimum luminance range inside one tile. Deliberately low: it only has to
## reject a flat fill, and the flattest tile in the current set (snow) still
## spans 0.15.
const MIN_LUMA_SPREAD := 0.06

## A tile wraps when the difference across the seam stays in the same league as
## the worst difference between two neighbouring lines inside the tile. Comparing
## against the internal worst case rather than against zero is what lets a
## deliberately discontinuous pattern (brick mortar, sandstone bedding planes)
## pass while a noise field that lost its wrap fails: such a seam runs several
## times above the internal scale.
const SEAM_FACTOR := 1.5
const SEAM_FLOOR := 0.01

const AXIS_X := 0
const AXIS_Y := 1


func suite_name() -> String:
	return "atlas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


## Tiles multiplied by the vertex colour, read from the block table rather than
## from a copy of its decisions, so the suite follows Blocks.
func _tinted_tiles() -> PackedStringArray:
	var names := PackedStringArray()
	for id in Blocks.COUNT:
		var mask := Blocks.tint_mask(id)
		if mask == 0:
			continue
		for face in Blocks.FACE_COUNT:
			if (mask & (1 << face)) == 0:
				continue
			var tile: String = Blocks.TILE_NAMES[Blocks.tile_of(id, face)]
			if not names.has(tile):
				names.append(tile)
	return names


func _luminance(c: Color) -> float:
	return 0.299 * c.r + 0.587 * c.g + 0.114 * c.b


## Mean absolute difference over the four channels between two rows or columns.
func _line_diff(img: Image, axis: int, a: int, b: int) -> float:
	var total := 0.0
	for k in S:
		var ca := img.get_pixel(a, k) if axis == AXIS_X else img.get_pixel(k, a)
		var cb := img.get_pixel(b, k) if axis == AXIS_X else img.get_pixel(k, b)
		total += absf(ca.r - cb.r) + absf(ca.g - cb.g) + absf(ca.b - cb.b) + absf(ca.a - cb.a)
	return total / float(S * 4)


## Worst difference between two neighbouring lines, the internal scale of the
## tile along that axis.
func _worst_inner_diff(img: Image, axis: int) -> float:
	var worst := 0.0
	for i in S - 1:
		worst = maxf(worst, _line_diff(img, axis, i, i + 1))
	return worst


func _check_seam(tile_name: String, img: Image, axis: int, label: String) -> void:
	var seam := _line_diff(img, axis, 0, S - 1)
	var inner := _worst_inner_diff(img, axis)
	check(seam <= inner * SEAM_FACTOR + SEAM_FLOOR,
		"la tuile '%s' ne se raccorde pas %s (couture %.4f, ecart interne max %.4f)"
		% [tile_name, label, seam, inner])


# ---------------------------------------------------------------------------
# Layers and geometry
# ---------------------------------------------------------------------------


func test_build_stacks_one_layer_per_tile_name() -> void:
	eq(Blocks.TILE_NAMES.size(), Blocks.TILE_COUNT, "le registre annonce autant de noms que de tuiles")

	var tex := VoxelAtlas.build()
	check(tex != null, "build() renvoie un Texture2DArray")
	eq(tex.get_layers(), Blocks.TILE_COUNT, "un calque par tuile")
	eq(tex.get_width(), S, "largeur d'un calque")
	eq(tex.get_height(), S, "hauteur d'un calque")
	eq(tex.get_format(), Image.FORMAT_RGBA8, "format des calques")

	# The layers themselves cannot be read back from a headless renderer, so the
	# mipmap chain the anisotropic filtering needs is checked on the source
	# image instead: a 32x32 square is mipmap capable and must accept the call.
	var probe := VoxelAtlas.tile_image(Blocks.TILE_NAMES[0])
	eq(probe.generate_mipmaps(), OK, "une tuile accepte la generation de mipmaps")
	check(probe.has_mipmaps(), "la tuile porte alors une chaine de mipmaps")
	done()


func test_every_tile_is_a_square_rgba_image() -> void:
	for tile_name in Blocks.TILE_NAMES:
		var img := VoxelAtlas.tile_image(tile_name)
		check(img != null, "la tuile '%s' doit exister" % tile_name)
		eq(img.get_width(), S, "largeur de la tuile '%s'" % tile_name)
		eq(img.get_height(), S, "hauteur de la tuile '%s'" % tile_name)
		eq(img.get_format(), Image.FORMAT_RGBA8, "format de la tuile '%s'" % tile_name)
	done()


func test_unknown_tile_name_falls_back_to_a_visible_placeholder() -> void:
	# The implementation warns and paints a checkerboard rather than returning
	# null, so a typo in a tile name shows up on screen instead of crashing the
	# mesher. A warning in the log is expected here.
	var img := VoxelAtlas.tile_image("tuile_qui_n_existe_pas")
	check(img != null, "un nom inconnu renvoie tout de meme une image")
	eq(img.get_width(), S, "largeur de la tuile de secours")
	eq(img.get_height(), S, "hauteur de la tuile de secours")
	eq(img.get_format(), Image.FORMAT_RGBA8, "format de la tuile de secours")
	eq(img.detect_alpha(), Image.ALPHA_NONE, "la tuile de secours est opaque")

	# Two distinct colours at least, otherwise the placeholder is invisible.
	var first := img.get_pixel(0, 0)
	var different := false
	for y in S:
		for x in S:
			if img.get_pixel(x, y) != first:
				different = true
				break
		if different:
			break
	check(different, "la tuile de secours doit etre voyante, pas un aplat")
	done()


# ---------------------------------------------------------------------------
# Quality: grain and tileability
# ---------------------------------------------------------------------------


func test_every_tile_carries_grain() -> void:
	for tile_name in Blocks.TILE_NAMES:
		var img := VoxelAtlas.tile_image(tile_name)
		var lo := 2.0
		var hi := -1.0
		for y in S:
			for x in S:
				var c := img.get_pixel(x, y)
				if c.a <= 0.5:
					continue
				var l := _luminance(c)
				lo = minf(lo, l)
				hi = maxf(hi, l)
		check(hi >= 0.0, "la tuile '%s' doit avoir des pixels visibles" % tile_name)
		check(hi - lo >= MIN_LUMA_SPREAD,
			"la tuile '%s' est un aplat uni (amplitude de luminance %.4f)" % [tile_name, hi - lo])
	done()


func test_tiles_wrap_on_both_axes() -> void:
	for tile_name in Blocks.TILE_NAMES:
		var img := VoxelAtlas.tile_image(tile_name)
		_check_seam(tile_name, img, AXIS_X, "horizontalement")
		if NO_VERTICAL_WRAP.has(tile_name):
			continue
		_check_seam(tile_name, img, AXIS_Y, "verticalement")
	done()


# ---------------------------------------------------------------------------
# Alpha budget
# ---------------------------------------------------------------------------


func test_only_the_cutout_tiles_carry_holes() -> void:
	for tile_name in Blocks.TILE_NAMES:
		var img := VoxelAtlas.tile_image(tile_name)
		var clear := 0
		var solid := 0
		for y in S:
			for x in S:
				var a := img.get_pixel(x, y).a
				if a <= 0.01:
					clear += 1
				elif a >= 0.99:
					solid += 1
		if TRANSPARENT_TILES.has(tile_name):
			check(clear > 0, "la tuile '%s' doit percer son alpha" % tile_name)
			check(solid > 0, "la tuile '%s' doit garder de la matiere visible" % tile_name)
		else:
			eq(clear, 0, "la tuile '%s' ne doit avoir aucun pixel transparent" % tile_name)
			eq(img.detect_alpha(), Image.ALPHA_NONE, "la tuile '%s' doit etre opaque" % tile_name)
	done()


func test_glass_keeps_an_opaque_frame_around_an_empty_centre() -> void:
	var img := VoxelAtlas.tile_image("glass")
	near(img.get_pixel(0, 0).a, 1.0, 0.01, "coin du cadre de verre opaque")
	near(img.get_pixel(S - 1, S - 1).a, 1.0, 0.01, "coin oppose du cadre de verre opaque")
	near(img.get_pixel(S / 2, S / 2).a, 0.0, 0.01, "centre du verre totalement transparent")

	# The frame has to run all the way round, otherwise the block loses its
	# outline once the neighbouring faces are culled.
	var border_solid := 0
	for k in S:
		if img.get_pixel(k, 0).a >= 0.99:
			border_solid += 1
		if img.get_pixel(k, S - 1).a >= 0.99:
			border_solid += 1
		if img.get_pixel(0, k).a >= 0.99:
			border_solid += 1
		if img.get_pixel(S - 1, k).a >= 0.99:
			border_solid += 1
	eq(border_solid, S * 4, "le cadre de verre couvre tout le bord de la tuile")
	done()


# ---------------------------------------------------------------------------
# Biome tint
# ---------------------------------------------------------------------------


func test_biome_tinted_tiles_stay_near_neutral_grey() -> void:
	var tinted := _tinted_tiles()
	check(tinted.size() >= 6, "Blocks doit declarer des tuiles teintees (obtenu %d)" % tinted.size())

	for tile_name in tinted:
		var img := VoxelAtlas.tile_image(tile_name)
		var sum_r := 0.0
		var sum_g := 0.0
		var sum_b := 0.0
		var visible := 0
		var worst_channel_gap := 0.0
		var lo := 2.0
		for y in S:
			for x in S:
				var c := img.get_pixel(x, y)
				if c.a <= 0.5:
					continue
				visible += 1
				sum_r += c.r
				sum_g += c.g
				sum_b += c.b
				worst_channel_gap = maxf(worst_channel_gap,
					maxf(c.r, maxf(c.g, c.b)) - minf(c.r, minf(c.g, c.b)))
				lo = minf(lo, _luminance(c))
		check(visible > 0, "la tuile teintee '%s' doit avoir des pixels visibles" % tile_name)
		var inv := 1.0 / float(maxi(visible, 1))
		var avg_r := sum_r * inv
		var avg_g := sum_g * inv
		var avg_b := sum_b * inv
		var spread := maxf(avg_r, maxf(avg_g, avg_b)) - minf(avg_r, minf(avg_g, avg_b))
		# The vertex colour supplies the hue, so the tile itself must be grey.
		check(spread <= 0.02,
			"la tuile teintee '%s' porte une couleur propre (ecart entre canaux %.4f)" % [tile_name, spread])
		check(worst_channel_gap <= 0.05,
			"un pixel de la tuile teintee '%s' n'est pas gris (ecart %.4f)" % [tile_name, worst_channel_gap])
		# Contract window is 0.65 to 1.0, checked with a little slack so a
		# repaint inside the window never trips the suite.
		between(lo, 0.60, 1.0, "luminance minimale de la tuile teintee '%s'" % tile_name)
		between((avg_r + avg_g + avg_b) / 3.0, 0.65, 1.0,
			"luminance moyenne de la tuile teintee '%s'" % tile_name)
	done()


func test_untinted_tiles_carry_their_own_hue() -> void:
	# Counterweight to the greyscale check above: a tile no vertex colour tints
	# must not be painted grey, or it renders colourless in game.
	var tinted := _tinted_tiles()
	for tile_name in ["water", "wool_red", "wool_green"]:
		check(not tinted.has(tile_name), "la tuile '%s' n'est pas teintee par biome" % tile_name)
		var img := VoxelAtlas.tile_image(tile_name)
		var sum_r := 0.0
		var sum_g := 0.0
		var sum_b := 0.0
		for y in S:
			for x in S:
				var c := img.get_pixel(x, y)
				sum_r += c.r
				sum_g += c.g
				sum_b += c.b
		var inv := 1.0 / float(S * S)
		var avg_r := sum_r * inv
		var avg_g := sum_g * inv
		var avg_b := sum_b * inv
		var spread := maxf(avg_r, maxf(avg_g, avg_b)) - minf(avg_r, minf(avg_g, avg_b))
		check(spread >= 0.015,
			"la tuile '%s' doit porter sa couleur definitive (ecart entre canaux %.4f)" % [tile_name, spread])
	done()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


func test_tile_generation_is_deterministic() -> void:
	for tile_name in ["stone", "cobblestone", "oak_leaves", "torch"]:
		var a := VoxelAtlas.tile_image(tile_name)
		var b := VoxelAtlas.tile_image(tile_name)
		eq(b.get_data(), a.get_data(), "deux demandes de la tuile '%s' donnent les memes octets" % tile_name)

	# The caller owns the image it receives: painting on it must not poison the
	# next request, which the particle code of Interaction relies on.
	var mine := VoxelAtlas.tile_image("stone")
	var reference := mine.get_data()
	mine.fill(Color(1.0, 0.0, 1.0, 1.0))
	eq(VoxelAtlas.tile_image("stone").get_data(), reference,
		"modifier l'image recue ne doit pas alterer la tuile suivante")

	# Real regeneration test: a second copy of the script loaded outside the
	# resource cache starts with an empty tile cache, so this genuinely repaints
	# the tile from its seed instead of reading it back.
	var fresh := ResourceLoader.load("res://src/render/atlas.gd", "Script", ResourceLoader.CACHE_MODE_IGNORE) as Script
	check(fresh != null, "le script de l'atlas se recharge hors cache")
	var cold: Variant = fresh.call("tile_image", "cobblestone") if fresh != null else null
	check(cold is Image, "la seconde instance du script repeint la tuile")
	if cold is Image:
		var cold_img: Image = cold
		eq(cold_img.get_data(), VoxelAtlas.tile_image("cobblestone").get_data(),
			"une tuile repeinte a froid est identique octet pour octet")
	done()


# ---------------------------------------------------------------------------
# Interface previews
# ---------------------------------------------------------------------------


func test_block_preview_covers_the_whole_palette() -> void:
	for entry in Blocks.PALETTE:
		var id := int(entry)
		var tex := VoxelAtlas.block_preview(id, 40)
		check(tex != null, "apercu du bloc %d" % id)
		eq(tex.get_width(), 40, "largeur de l'apercu du bloc %s" % Blocks.display_name(id))
		eq(tex.get_height(), 40, "hauteur de l'apercu du bloc %s" % Blocks.display_name(id))
	eq(VoxelAtlas.block_preview(Blocks.GRASS).get_width(), 48, "taille d'apercu par defaut")
	done()


func test_block_preview_uses_the_top_face() -> void:
	# At the native tile size the resize is a no-op, so the preview must be the
	# top face tile byte for byte. Oak logs have a different tile on the side,
	# which is exactly what makes them a usable witness here.
	var preview := VoxelAtlas.block_preview(Blocks.OAK_LOG, S)
	var image := preview.get_image()
	check(image != null, "l'apercu expose son image")
	eq(image.get_width(), S, "largeur de l'apercu natif")
	eq(image.get_data(), VoxelAtlas.tile_image("oak_log_top").get_data(),
		"l'apercu d'un cube vient de sa face de dessus")
	ne(image.get_data(), VoxelAtlas.tile_image("oak_log_side").get_data(),
		"l'apercu d'un cube ne vient pas de sa face laterale")

	# Cross blocks have a single tile, taken from a side face.
	var flower := VoxelAtlas.block_preview(Blocks.FLOWER_RED, S).get_image()
	eq(flower.get_data(), VoxelAtlas.tile_image("flower_red").get_data(),
		"l'apercu d'une plante vient de sa tuile unique")
	done()


func test_block_preview_handles_air_and_invalid_ids() -> void:
	var air := VoxelAtlas.block_preview(Blocks.AIR, 16)
	check(air != null, "l'air renvoie tout de meme une texture")
	eq(air.get_width(), 16, "largeur de l'apercu de l'air")
	eq(air.get_height(), 16, "hauteur de l'apercu de l'air")
	var air_img := air.get_image()
	check(air_img != null, "l'apercu de l'air expose son image")
	eq(air_img.detect_alpha() != Image.ALPHA_NONE, true, "l'apercu de l'air est transparent")

	for bad_id in [-1, Blocks.COUNT, 250]:
		var tex := VoxelAtlas.block_preview(bad_id, 20)
		check(tex != null, "un id invalide (%d) ne casse pas l'apercu" % bad_id)
		eq(tex.get_width(), 20, "largeur de l'apercu d'un id invalide (%d)" % bad_id)
		eq(tex.get_height(), 20, "hauteur de l'apercu d'un id invalide (%d)" % bad_id)

	# A degenerate request must still produce a usable square texture.
	var tiny := VoxelAtlas.block_preview(Blocks.STONE, 1)
	eq(tiny.get_width(), tiny.get_height(), "un apercu minuscule reste carre")
	check(tiny.get_width() >= 1, "un apercu minuscule garde une taille utilisable")
	done()
