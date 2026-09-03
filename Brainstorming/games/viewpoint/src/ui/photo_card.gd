class_name PhotoCard
extends Control
## The small held-photo card of the HUD. A Control can only spin around Z, so
## the X tilt is drawn by hand: the picture is a textured quad rotated in 3D
## and projected through a pinhole, subdivided into a grid so the perspective
## stays correct (a single quad would map the texture affinely and shear it).

var texture: Texture2D:
	set(value):
		texture = value
		queue_redraw()

## Roll around the view axis, degrees. Positive leans the top to the right.
@export var tilt_z := 9.0
## Pitch around the horizontal axis, degrees. Positive pushes the top away.
@export var tilt_x := 26.0
## Side of the drawn picture in pixels, before the tilt shrinks it.
@export var card_size := 62.0
## Pinhole distance in card widths: smaller means a stronger perspective.
@export var view_distance := 2.4

const GRID := 6
const SHADOW_OFFSET := Vector2(3, 4)


func _draw() -> void:
	if texture == null:
		return
	var center := size * 0.5
	var basis := Basis(Vector3(0, 0, 1), deg_to_rad(tilt_z)) * Basis(Vector3(1, 0, 0), deg_to_rad(tilt_x))
	# Focal chosen so an untilted card spans exactly card_size pixels.
	var focal := view_distance * card_size

	# One shadow quad for the whole card, drawn first: per cell it would land on
	# top of the neighbouring cells' picture.
	var shadow := PackedVector2Array()
	for corner: Vector2 in [Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)]:
		shadow.append(_project(corner, basis, center, focal) + SHADOW_OFFSET)
	draw_colored_polygon(shadow, Color(0.05, 0.06, 0.10, 0.35))

	var points := PackedVector2Array()
	points.resize(4)
	var uvs := PackedVector2Array()
	uvs.resize(4)
	for gx in GRID:
		for gy in GRID:
			for corner in 4:
				var uv := Vector2(
					float(gx + (1 if corner in [1, 2] else 0)) / GRID,
					float(gy + (1 if corner >= 2 else 0)) / GRID
				)
				points[corner] = _project(uv, basis, center, focal)
				uvs[corner] = uv
			draw_colored_polygon(points, Color.WHITE, uvs, texture)


## Projects a uv of the card (0,0 top left) to a screen point of this Control.
func _project(uv: Vector2, basis: Basis, center: Vector2, focal: float) -> Vector2:
	var p := basis * Vector3(uv.x - 0.5, 0.5 - uv.y, 0.0) + Vector3(0, 0, -view_distance)
	return center + Vector2(p.x, -p.y) * (focal / -p.z)
