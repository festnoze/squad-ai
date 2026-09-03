class_name Palette
## Named colors of the game. Every material color goes through here so the
## whole look can be retuned in one place, and so tests can assert that photo
## and level definitions only reference colors that exist.

const COLORS := {
	# GROUND LANGUAGE, read at a glance and never explained in words:
	# grey stays, pale goes. A grey slab survives any photo placed over it
	# (the photo is added to it); a pale slab is carved away by the frame,
	# like the lavender walls and crates it belongs to.
	"platform": Color(0.70, 0.71, 0.75),
	"platform_side": Color(0.53, 0.54, 0.59),
	"platform_soft": Color(0.93, 0.92, 0.97),
	"platform_soft_side": Color(0.80, 0.78, 0.88),
	# SEALED MATTER, the same language pushed one step further: this is grey
	# that has gone to steel and lead. A steel cage no photo ever breaks, a
	# leaden battery no film ever prints. Darker than the permanent ground, and
	# with no life of its own (a sealed battery neither bobs nor turns).
	"sealed": Color(0.58, 0.60, 0.66),
	"sealed_dark": Color(0.40, 0.42, 0.48),
	"battery_sealed": Color(0.50, 0.52, 0.57),
	"accent": Color(0.91, 0.45, 0.35),
	"accent_dark": Color(0.72, 0.32, 0.24),
	"teal": Color(0.25, 0.65, 0.63),
	"teal_dark": Color(0.18, 0.50, 0.48),
	"frame": Color(0.98, 0.97, 0.95),
	"photo_back": Color(0.88, 0.86, 0.82),
	"battery": Color(1.0, 0.76, 0.29),
	"battery_tip": Color(0.35, 0.35, 0.38),
	"teleporter": Color(0.36, 0.36, 0.84),
	"teleporter_ring": Color(0.55, 0.78, 1.0),
	"erasable": Color(0.69, 0.62, 0.86),
	"wood": Color(0.62, 0.47, 0.34),
	"wood_dark": Color(0.48, 0.36, 0.26),
	"stone": Color(0.78, 0.77, 0.75),
	"sky_top": Color(0.53, 0.72, 0.87),
	"sky_horizon": Color(0.87, 0.91, 0.93),
	"backdrop_top": Color(0.62, 0.79, 0.90),
	"backdrop_bottom": Color(0.93, 0.90, 0.84),
}


static func has_color(key: String) -> bool:
	return COLORS.has(key)


static func color(key: String) -> Color:
	if not COLORS.has(key):
		push_warning("Palette: unknown color key '%s'" % key)
		return Color.MAGENTA
	return COLORS[key]
