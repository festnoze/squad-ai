extends ViewTest
## The material factory: caching and the ghost variant that carries the
## placement preview.


func suite_name() -> String:
	return "materials"


func test_solid_cache() -> void:
	var a := Materials.solid("platform")
	var b := Materials.solid("platform")
	check(a == b, "meme cle : meme instance")
	var c := Materials.solid("platform", 1.0)
	check(a != c, "variante emissive : instance distincte")
	check(c.emission_enabled, "variante emissive allumee")
	eq(a.albedo_color, Palette.color("platform"), "couleur d'albedo depuis la palette")
	done()


func test_ghost() -> void:
	var g := Materials.ghost("wood")
	check(g == Materials.ghost("wood"), "fantome mis en cache")
	between(g.albedo_color.a, 0.1, 0.9, "fantome semi-transparent")
	eq(g.transparency, BaseMaterial3D.TRANSPARENCY_ALPHA, "transparence alpha activee")
	eq(g.shading_mode, BaseMaterial3D.SHADING_MODE_UNSHADED, "fantome non ombre")
	var solid := Materials.solid("wood")
	near(g.albedo_color.r, solid.albedo_color.r, 0.001, "meme teinte que le solide")
	done()


func test_backdrop() -> void:
	var m := Materials.backdrop("backdrop_top", "backdrop_bottom")
	check(m == Materials.backdrop("backdrop_top", "backdrop_bottom"), "backdrop mis en cache")
	ne(m.albedo_texture, null, "backdrop texture en degrade")
	eq(m.shading_mode, BaseMaterial3D.SHADING_MODE_UNSHADED, "backdrop non ombre")
	var img: Image = m.albedo_texture.get_image()
	var top := img.get_pixel(0, 0)
	var bottom := img.get_pixel(0, img.get_height() - 1)
	check(not top.is_equal_approx(bottom), "le degrade varie du haut vers le bas")
	done()
