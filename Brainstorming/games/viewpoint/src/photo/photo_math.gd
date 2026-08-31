class_name PhotoMath
## Pure geometry of the photo mechanic: the placement frustum used both to
## erase world objects and to size the backdrop, and the pinhole projection
## used to draw thumbnails. Camera space convention: x right, y up, -z forward.

## Square photos, like a polaroid. The fov is vertical (and horizontal, since
## the aspect is 1). Narrower than the player camera on purpose: the photo is
## a window inside the view, not the whole view.
const PHOTO_FOV_DEG := 50.0
const PHOTO_ASPECT := 1.0

## Erase reach of a photo that has no backdrop.
const DEFAULT_ERASE_DEPTH := 12.0


## Half height of the frustum cross-section at the given forward depth.
static func half_extent_at(depth: float, fov_deg: float) -> float:
	return depth * tan(deg_to_rad(fov_deg) * 0.5)


## True when a camera-space point sits inside the photo frustum.
static func point_in_frustum(local: Vector3, fov_deg: float, aspect: float, near: float, far: float) -> bool:
	var depth := -local.z
	if depth < near or depth > far:
		return false
	var half_v := half_extent_at(depth, fov_deg)
	var half_h := half_v * aspect
	return absf(local.x) <= half_h and absf(local.y) <= half_v


## Pinhole projection of a camera-space point onto the photo plane.
## Returns normalized coordinates in [-1, 1] on both axes for points inside
## the frustum, (0, 0) at the photo center, y up.
static func project_point(local: Vector3, fov_deg: float, aspect: float) -> Vector2:
	var depth := maxf(0.01, -local.z)
	var half_v := half_extent_at(depth, fov_deg)
	return Vector2(local.x / (half_v * aspect), local.y / half_v)


## Full size of a quad that exactly fills the frustum at the given depth.
static func backdrop_size(depth: float, fov_deg: float, aspect: float) -> Vector2:
	var h := 2.0 * half_extent_at(depth, fov_deg)
	return Vector2(h * aspect, h)
