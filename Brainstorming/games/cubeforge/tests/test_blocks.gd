extends TestCase
## Consistency of the block registry and of the face visibility rule the mesher
## depends on.


func suite_name() -> String:
	return "blocks"


func test_table_is_complete() -> void:
	eq(Blocks.TILE_NAMES.size(), Blocks.TILE_COUNT, "TILE_NAMES doit contenir TILE_COUNT entrees")
	for id in Blocks.COUNT:
		ne(Blocks.display_name(id), "", "le bloc %d doit avoir un nom" % id)
		for face in Blocks.FACE_COUNT:
			var layer := Blocks.tile_of(id, face)
			between(float(layer), 0.0, float(Blocks.TILE_COUNT - 1),
				"tuile hors bornes pour le bloc %d face %d" % [id, face])
	done()


func test_palette_only_holds_real_blocks() -> void:
	for id in Blocks.PALETTE:
		between(float(id), 1.0, float(Blocks.COUNT - 1), "la palette contient un id invalide %d" % id)
		ne(Blocks.kind_of(id), Blocks.Kind.EMPTY, "la palette ne doit pas contenir d'air")
	done()


func test_surface_assignment() -> void:
	eq(Blocks.surface_of(Blocks.STONE), Blocks.Surface.OPAQUE, "la pierre est opaque")
	eq(Blocks.surface_of(Blocks.OAK_LEAVES), Blocks.Surface.CUTOUT, "les feuilles sont en decoupe")
	eq(Blocks.surface_of(Blocks.GLASS), Blocks.Surface.CUTOUT, "le verre est en decoupe")
	eq(Blocks.surface_of(Blocks.GRASS_TUFT), Blocks.Surface.CUTOUT, "les plantes sont en decoupe")
	eq(Blocks.surface_of(Blocks.ICE), Blocks.Surface.TRANSLUCENT, "la glace est translucide")
	eq(Blocks.surface_of(Blocks.WATER), Blocks.Surface.WATER, "l'eau a sa propre surface")
	done()


func test_collision_flags() -> void:
	check(Blocks.collides(Blocks.STONE), "la pierre bloque")
	check(Blocks.collides(Blocks.GLASS), "le verre bloque")
	check(Blocks.collides(Blocks.ICE), "la glace bloque")
	check(Blocks.collides(Blocks.OAK_LEAVES), "les feuilles bloquent")
	check(not Blocks.collides(Blocks.AIR), "l'air ne bloque pas")
	check(not Blocks.collides(Blocks.WATER), "l'eau ne bloque pas")
	check(not Blocks.collides(Blocks.GRASS_TUFT), "les plantes ne bloquent pas")
	check(not Blocks.collides(Blocks.TORCH), "la torche ne bloque pas")
	done()


func test_opacity_flags() -> void:
	check(Blocks.is_opaque(Blocks.STONE), "la pierre masque ses voisins")
	check(not Blocks.is_opaque(Blocks.AIR), "l'air ne masque rien")
	check(not Blocks.is_opaque(Blocks.WATER), "l'eau ne masque rien")
	check(not Blocks.is_opaque(Blocks.GLASS), "le verre ne masque rien")
	check(not Blocks.is_opaque(Blocks.OAK_LEAVES), "les feuilles ne masquent rien")
	done()


func test_draws_face_rules() -> void:
	check(Blocks.draws_face(Blocks.STONE, Blocks.AIR), "face visible contre l'air")
	check(not Blocks.draws_face(Blocks.STONE, Blocks.STONE), "pas de face entre deux pierres")
	check(not Blocks.draws_face(Blocks.STONE, Blocks.DIRT), "pas de face entre deux blocs opaques")
	check(Blocks.draws_face(Blocks.STONE, Blocks.WATER), "face visible contre l'eau")
	check(Blocks.draws_face(Blocks.STONE, Blocks.GLASS), "face visible contre le verre")

	# Identical see-through blocks merge, which removes the interior faces of a
	# lake or a leaf cluster. Two different see-through blocks do not.
	check(not Blocks.draws_face(Blocks.WATER, Blocks.WATER), "pas de face entre deux eaux")
	check(not Blocks.draws_face(Blocks.GLASS, Blocks.GLASS), "pas de face entre deux verres")
	check(not Blocks.draws_face(Blocks.OAK_LEAVES, Blocks.OAK_LEAVES), "pas de face entre deux feuillages identiques")
	check(Blocks.draws_face(Blocks.OAK_LEAVES, Blocks.BIRCH_LEAVES), "face visible entre deux feuillages differents")
	check(Blocks.draws_face(Blocks.WATER, Blocks.GLASS), "face visible entre eau et verre")
	check(Blocks.draws_face(Blocks.WATER, Blocks.AIR), "face visible entre eau et air")
	done()


func test_breakability_and_drops() -> void:
	check(not Blocks.is_breakable(Blocks.BEDROCK), "la roche-mere est incassable")
	check(not Blocks.is_breakable(Blocks.WATER), "l'eau est incassable")
	check(not Blocks.is_breakable(Blocks.AIR), "l'air est incassable")
	check(Blocks.is_breakable(Blocks.STONE), "la pierre est cassable")
	eq(Blocks.drop_of(Blocks.STONE), Blocks.COBBLESTONE, "la pierre donne de la pierre taillee")
	eq(Blocks.drop_of(Blocks.DIRT), Blocks.DIRT, "la terre se donne elle-meme")
	for id in Blocks.COUNT:
		between(float(Blocks.drop_of(id)), 0.0, float(Blocks.COUNT - 1),
			"le butin du bloc %d doit etre un id valide" % id)
	done()


func test_replaceable_and_support() -> void:
	check(Blocks.is_replaceable(Blocks.AIR), "on peut construire dans l'air")
	check(Blocks.is_replaceable(Blocks.WATER), "on peut construire dans l'eau")
	check(Blocks.is_replaceable(Blocks.GRASS_TUFT), "on peut construire dans une touffe d'herbe")
	check(not Blocks.is_replaceable(Blocks.STONE), "on ne remplace pas la pierre")
	check(Blocks.needs_support(Blocks.FLOWER_RED), "une fleur a besoin d'un sol")
	check(not Blocks.needs_support(Blocks.STONE), "la pierre n'a pas besoin de sol")
	done()


func test_emission() -> void:
	check(Blocks.is_light_source(Blocks.LAMP), "la lampe eclaire")
	check(Blocks.is_light_source(Blocks.TORCH), "la torche eclaire")
	check(not Blocks.is_light_source(Blocks.STONE), "la pierre n'eclaire pas")
	for id in Blocks.COUNT:
		between(Blocks.emission(id), 0.0, 1.0, "emission hors de 0..1 pour le bloc %d" % id)
	done()


func test_tint_masks() -> void:
	eq(Blocks.tint_mask(Blocks.GRASS), Blocks.BIT_PY, "seul le dessus du bloc d'herbe est teinte")
	eq(Blocks.tint_mask(Blocks.OAK_LEAVES), Blocks.BITS_ALL, "toutes les faces des feuilles sont teintees")
	eq(Blocks.tint_mask(Blocks.STONE), 0, "la pierre n'est pas teintee")
	eq(Blocks.tint_mask(Blocks.DEAD_BUSH), 0, "le buisson mort n'est pas teinte")
	done()
