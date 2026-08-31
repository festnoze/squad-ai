extends ViewTest
## Pure geometry of the photo frustum and the thumbnail projection.


func suite_name() -> String:
	return "photo_math"


func test_half_extent() -> void:
	near(PhotoMath.half_extent_at(5.0, 50.0), 5.0 * tan(deg_to_rad(25.0)), 0.0001, "demi-hauteur a 5 m")
	near(PhotoMath.half_extent_at(0.0, 50.0), 0.0, 0.0001, "demi-hauteur nulle a l'apex")
	done()


func test_frustum_membership() -> void:
	var fov := 50.0
	check(PhotoMath.point_in_frustum(Vector3(0, 0, -5), fov, 1.0, 0.0, 12.0), "le centre a 5 m est dedans")
	check(not PhotoMath.point_in_frustum(Vector3(0, 0, -13), fov, 1.0, 0.0, 12.0), "au dela du plan lointain, dehors")
	check(not PhotoMath.point_in_frustum(Vector3(0, 0, 3), fov, 1.0, 0.0, 12.0), "derriere la camera, dehors")
	var edge := PhotoMath.half_extent_at(5.0, fov)
	check(PhotoMath.point_in_frustum(Vector3(edge - 0.01, 0, -5), fov, 1.0, 0.0, 12.0), "juste sous le bord lateral, dedans")
	check(not PhotoMath.point_in_frustum(Vector3(edge + 0.01, 0, -5), fov, 1.0, 0.0, 12.0), "juste au dela du bord lateral, dehors")
	check(not PhotoMath.point_in_frustum(Vector3(0, edge + 0.01, -5), fov, 1.0, 0.0, 12.0), "juste au dela du bord haut, dehors")
	check(PhotoMath.point_in_frustum(Vector3(0, -edge + 0.01, -5), fov, 1.0, 0.0, 12.0), "pres du bord bas, dedans")
	done()


func test_frustum_aspect() -> void:
	var fov := 50.0
	var edge := PhotoMath.half_extent_at(5.0, fov)
	check(PhotoMath.point_in_frustum(Vector3(edge * 1.5, 0, -5), fov, 2.0, 0.0, 12.0), "aspect 2 : deux fois plus large")
	check(not PhotoMath.point_in_frustum(Vector3(edge * 1.5, 0, -5), fov, 1.0, 0.0, 12.0), "aspect 1 : le meme point est dehors")
	done()


func test_projection() -> void:
	var fov := 50.0
	var p_center := PhotoMath.project_point(Vector3(0, 0, -5), fov, 1.0)
	near(p_center.x, 0.0, 0.0001, "le centre se projette en x = 0")
	near(p_center.y, 0.0, 0.0001, "le centre se projette en y = 0")
	var edge := PhotoMath.half_extent_at(5.0, fov)
	var p_edge := PhotoMath.project_point(Vector3(edge, 0, -5), fov, 1.0)
	near(p_edge.x, 1.0, 0.001, "le bord droit se projette en x = 1")
	var p_sym := PhotoMath.project_point(Vector3(-edge, edge, -5), fov, 1.0)
	near(p_sym.x, -1.0, 0.001, "symetrie gauche")
	near(p_sym.y, 1.0, 0.001, "le haut se projette en y = 1")
	# The same lateral offset projects smaller when it is further away.
	var near_p := PhotoMath.project_point(Vector3(1, 0, -4), fov, 1.0)
	var far_p := PhotoMath.project_point(Vector3(1, 0, -8), fov, 1.0)
	check(far_p.x < near_p.x, "la perspective retrecit avec la distance")
	done()


func test_backdrop_size() -> void:
	var size := PhotoMath.backdrop_size(8.0, 50.0, 1.0)
	near(size.x, size.y, 0.0001, "backdrop carre en aspect 1")
	near(size.y, 2.0 * 8.0 * tan(deg_to_rad(25.0)), 0.001, "hauteur du backdrop a 8 m")
	var wide := PhotoMath.backdrop_size(8.0, 50.0, 2.0)
	near(wide.x, wide.y * 2.0, 0.001, "aspect 2 : deux fois plus large")
	done()
