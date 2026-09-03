class_name LevelDefs
## The twenty levels, as pure data (PRD section 5, docs/LEVELS_V2.md).
## Coordinates are world space, platform tops sit at y = 0 unless stated
## otherwise. Every list is consumed by LevelBuilder; the unit suite checks
## the invariants (spawn above ground, enough batteries reachable counting
## photo-in-photo chains and camera films, referenced photos exist, cages on
## platforms).
##
## v4 (total replacement) design rules baked into this data:
## - Every placement carves ALL boxes (platforms included) and paints a solid
##   backdrop wall at the photo's backdrop depth. Landing platforms on a
##   mandatory placement axis are at least 12 m wide so side corridors of
##   1.5 m or more survive a centered 8.9 m to 11.2 m painted wall.
## - Every cage is breakable by any placement that catches its center: cage
##   puzzles are economy (which photo to spend) or distance puzzles.
## - There is no 3D ghost preview anymore: thin tinted slabs in "decor" mark
##   the intended standing spots for precision placements ("teal" for the
##   standard route, "accent" for the critical shot of the level).
## - Interact range is 1.7 m: showcase niches are at most 1.2 m deep and the
##   battery inside sits within 0.6 m of the opening.

const LEVELS := [
	{
		"name": "Premiers pas",
		"subtitle": "Cadrez le vide et posez : la photo s'ajoute au monde.",
		"spawn": Vector3(0, 1.2, 5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 2), "size": Vector3(10, 1, 10)},
			# Wide landing: the walkway's painted sky wall (8.9 m at 9.5 m)
			# lands here, side corridors remain.
			{"pos": Vector3(0, -0.5, -14.9), "size": Vector3(14, 1, 8)},
		],
		"decor": [
			{"pos": Vector3(-3.5, 0.5, 5.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(-3.5, 1.3, 5.2), "size": Vector3(0.6, 0.6, 0.6), "color": "wood_dark"},
			{"pos": Vector3(0, -0.01, -2.85), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(1.5, 0.9, 4)},
		],
		"batteries": [Vector3(0, 0, -11.5)],
		"teleporter": {"pos": Vector3(0, 0, -16.5), "required": 1},
	},
	{
		"name": "Copie conforme",
		"subtitle": "Une photo de pile devient une vraie pile. Grise : une copie ne se recopie pas.",
		"spawn": Vector3(0, 1.2, 5.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(14, 1, 14)},
		],
		"decor": [
			{"pos": Vector3(5.5, 0.5, 3), "size": Vector3(1.2, 1, 1.2), "color": "wood"},
			{"pos": Vector3(-4, -0.01, -1), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [
			{"pos": Vector3(-5, 0.6, 4), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "pile", "pos": Vector3(-4, 0.9, -3)},
		],
		"batteries": [Vector3(5, 0, -5)],
		"teleporter": {"pos": Vector3(2, 0, 3), "required": 2},
	},
	{
		"name": "Prendre de la hauteur",
		"subtitle": "Un escalier pose la ou vous regardez. Son fond se saute.",
		"spawn": Vector3(0, 1.2, 5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 14)},
			{"pos": Vector3(5, 2.0, -2), "size": Vector3(4, 5, 4)},
		],
		"decor": [
			{"pos": Vector3(-7, 0.5, -5.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(5, -0.01, 6.4), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(-4, 0.6, -5.5), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "escalier", "pos": Vector3(0, 0.9, 3)},
		],
		"batteries": [Vector3(5, 4.5, -2), Vector3(-6, 0, -5)],
		"teleporter": {"pos": Vector3(-6, 0, 4), "required": 2},
	},
	{
		"name": "Effacement",
		"subtitle": "Le lavande cede au cadre. Le sol gris, lui, ne bouge pas.",
		"spawn": Vector3(0, 1.2, 12),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(10, 1, 28)},
		],
		"decor": [
			{"pos": Vector3(4, 0.5, 10), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, 1.0), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(0, 1.75, -4), "size": Vector3(10, 3.5, 0.6)},
			{"pos": Vector3(-3.5, 0.6, 8), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "porte", "pos": Vector3(-3, 0.9, 5)},
		],
		"batteries": [Vector3(3, 0, 6), Vector3(0, 0, -9)],
		"teleporter": {"pos": Vector3(0, 0, -12), "required": 2},
	},
	{
		"name": "Belvedere",
		"subtitle": "Franchir, monter, dupliquer : a vous de composer.",
		"spawn": Vector3(-4, 1.2, 4),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(12, 1, 12)},
			# Widened: the walkway's painted wall lands on this island.
			{"pos": Vector3(0, 0.7, -16.5), "size": Vector3(12, 1, 8)},
			{"pos": Vector3(10, 1.5, 0), "size": Vector3(6, 4, 6)},
		],
		"decor": [
			{"pos": Vector3(4.5, 0.5, -4.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, 0.6, -5.2), "size": Vector3(1.6, 1.2, 1.6), "color": "stone"},
			{"pos": Vector3(0, 1.21, -5.2), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0.5, -0.01, 0), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(-4.5, 0.6, -4.5), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "passerelle", "pos": Vector3(3, 0.9, 2)},
			{"id": "escalier", "pos": Vector3(-3, 0.9, 2)},
			{"id": "pile", "pos": Vector3(2, 2.1, -15)},
		],
		"batteries": [Vector3(0, 1.2, -13.5), Vector3(8.6, 3.5, -2.0)],
		"teleporter": {"pos": Vector3(0, 0, 4), "required": 3},
	},
	{
		"name": "La cage",
		"subtitle": "Toute pose fauche une cage entiere. Meme une porte.",
		"spawn": Vector3(0, 1.2, 5.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(16, 1, 14)},
		],
		"decor": [
			{"pos": Vector3(-6, 0.5, 2), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(1, -0.01, 0.2), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(4, 0, -4), "size": Vector3(2.5, 2.5, 2.5), "erasable": true, "roof": true},
		],
		"photos": [
			{"id": "porte", "pos": Vector3(0, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(-2, 0.9, 4)},
		],
		"batteries": [Vector3(3.7, 0, -4), Vector3(4.6, 0, -3.5)],
		"teleporter": {"pos": Vector3(-5, 0, 2), "required": 2},
	},
	{
		"name": "Pivot",
		"subtitle": "La molette tourne la photo : la dalle change de cote.",
		"spawn": Vector3(0, 1.2, 6),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 3), "size": Vector3(12, 1, 8)},
			{"pos": Vector3(6.5, 0.6, -5.5), "size": Vector3(3, 3.2, 3.5)},
			{"pos": Vector3(-5.5, 1.1, -4.75), "size": Vector3(3, 4.2, 3.5)},
		],
		"decor": [
			{"pos": Vector3(-3, 0.75, 1.5), "size": Vector3(1.5, 1.5, 1.5), "color": "stone"},
			{"pos": Vector3(3.6, -0.01, -0.6), "size": Vector3(1.4, 0.06, 1.4), "color": "teal",
				"photo": "corniche", "aim": Vector3(6.5, 2.0, -5.5), "roll": 0},
			{"pos": Vector3(-3.2, -0.01, -0.6), "size": Vector3(1.4, 0.06, 1.4), "color": "accent",
				"photo": "corniche", "aim": Vector3(-5.5, 2.0, -4.75), "roll": 2},
		],
		"erasables": [],
		"photos": [
			{"id": "corniche", "pos": Vector3(1, 0.9, 5)},
			{"id": "corniche", "pos": Vector3(-1, 0.9, 5)},
		],
		# IN FRONT of the painted wall, not past it. They used to sit beyond
		# the 6 m depth of a corniche, which meant the very placement that gave
		# access to them also sealed them behind a solid wall of sky.
		"batteries": [Vector3(6.4, 2.2, -4.6), Vector3(-6.4, 3.2, -4.6)],
		"teleporter": {"pos": Vector3(3, 0, 5), "required": 2},
	},
	{
		"name": "Le coffret",
		"subtitle": "Certaines photos contiennent d'autres photos.",
		"spawn": Vector3(-3, 1.2, 4.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(14, 1, 12)},
		],
		"decor": [
			{"pos": Vector3(5, 0.5, 3), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(-4, -0.01, -0.5), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [
			{"pos": Vector3(-5.5, 0.6, -3), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "coffret", "pos": Vector3(-4, 0.9, -2)},
		],
		"batteries": [Vector3(5, 0, -4)],
		"teleporter": {"pos": Vector3(0, 0, 4), "required": 2},
	},
	{
		"name": "L'enclos",
		"subtitle": "Trois photos, trois serrures. Une pose peut en ouvrir deux.",
		"spawn": Vector3(0, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(22, 1, 18)},
			{"pos": Vector3(5.8, 1.75, -3.2), "size": Vector3(4, 4.5, 4)},
			{"pos": Vector3(-6, 1.4, -4), "size": Vector3(2.5, 3.8, 2.5)},
		],
		"decor": [
			{"pos": Vector3(8, 0.5, 5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(2, -0.01, 4), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(-6, -0.01, 0.8), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(2, 0, -2), "size": Vector3(3, 2.6, 3), "erasable": false, "roof": true},
		],
		"photos": [
			{"id": "escalier", "pos": Vector3(0, 0.9, 4)},
			{"id": "console", "pos": Vector3(-3, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(-1.5, 0.9, 5)},
		],
		"batteries": [Vector3(2, 0, -2), Vector3(-6, 3.3, -4), Vector3(5.8, 4.0, -3.2)],
		"teleporter": {"pos": Vector3(6, 0, 5), "required": 3},
	},
	{
		"name": "Plongeon",
		"subtitle": "La rive est plus bas. Piquez la passerelle, ou franchissez et laissez-vous tomber.",
		"spawn": Vector3(0, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 4), "size": Vector3(10, 1, 8)},
			# Widened: the pitched painted wall crosses the island.
			{"pos": Vector3(0, -5.5, -12), "size": Vector3(12, 1, 8)},
		],
		"decor": [
			{"pos": Vector3(3.5, 0.5, 6.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, 0.5), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(0, 0.9, 6)},
		],
		"batteries": [Vector3(3, 0, 5), Vector3(-3, -5, -12)],
		"teleporter": {"pos": Vector3(4.5, -5, -14), "required": 2},
	},
	{
		"name": "Sous le pont",
		"subtitle": "Un sol pale se decoupe comme un mur. Traversez d'abord, percez ensuite.",
		"spawn": Vector3(0, 1.2, 8.5),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 6), "size": Vector3(10, 1, 8)},
			{"pos": Vector3(0, -0.5, -10), "size": Vector3(12, 1, 8)},
			{"pos": Vector3(4, 0.8, -11), "size": Vector3(3, 2.6, 3)},
			{"pos": Vector3(0, -4.5, -2), "size": Vector3(2, 1, 6)},
			# PALE ground: the only floor of the game a frame may take away.
			{"pos": Vector3(0, -0.15, -2), "size": Vector3(2, 0.3, 8.4), "soft": true},
		],
		"decor": [
			{"pos": Vector3(-4, 0.5, -8), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, -7), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(0, -4.01, -4.2), "size": Vector3(1.0, 0.06, 1.0), "color": "teal"},
			# The only band of ground from which the console slab lands OUTSIDE
			# the grey block instead of inside it.
			{"pos": Vector3(4, -0.01, -6.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal",
				"photo": "console", "aim": Vector3(4, 1.0, -9.5), "roll": 0},
		],
		"erasables": [],
		"photos": [
			{"id": "console", "pos": Vector3(2, 0.9, 7)},
			{"id": "console", "pos": Vector3(-2, 0.9, 7)},
			{"id": "escalier", "pos": Vector3(0, -3.1, -2)},
		],
		"batteries": [Vector3(4, 2.1, -11), Vector3(0, -4, -3)],
		"teleporter": {"pos": Vector3(-4, 0, -10), "required": 2},
	},
	{
		"name": "La vitrine",
		"subtitle": "Chaque photo ouvre la voie vers la suivante. Toutes comptent.",
		"spawn": Vector3(-1, 1.2, 6.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(20, 1, 16)},
			{"pos": Vector3(7, 0.6, 5), "size": Vector3(3, 3.2, 3)},
		],
		"decor": [
			# Showcase niche, 1.0 m deep (interact range is 1.7 m).
			{"pos": Vector3(3.1, 1.0, -6.35), "size": Vector3(0.4, 2, 1.1), "color": "battery_tip"},
			{"pos": Vector3(5.5, 1.0, -6.35), "size": Vector3(0.4, 2, 1.1), "color": "battery_tip"},
			{"pos": Vector3(4.3, 2.05, -6.35), "size": Vector3(2.8, 0.3, 1.1), "color": "battery_tip"},
			{"pos": Vector3(4.3, 1.0, -6.95), "size": Vector3(2.8, 2, 0.2), "color": "battery_tip"},
			{"pos": Vector3(4.2, -0.01, 1.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(-1.4, -0.01, 2), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(4.3, -0.01, -1.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal",
				"photo": "coffret", "aim": Vector3(4.3, 1.0, -5.8), "roll": 0},
		],
		"erasables": [
			{"pos": Vector3(-6.5, 1.25, 0), "size": Vector3(0.6, 3.5, 16)},
			{"pos": Vector3(4.3, 1.0, -5.85), "size": Vector3(2.4, 1.9, 0.15)},
		],
		"photos": [
			{"id": "corniche", "pos": Vector3(2, 0.9, 6)},
			{"id": "porte", "pos": Vector3(7, 3.1, 5)},
			{"id": "coffret", "pos": Vector3(-8.2, 0.9, -3)},
		],
		"batteries": [Vector3(7, 2.2, 5), Vector3(-8.2, 0, 2), Vector3(4.3, 0, -6.35), Vector3(-8.2, 0, -5)],
		"teleporter": {"pos": Vector3(0, 0, -6), "required": 4},
	},
	{
		"name": "La rampe celeste",
		"subtitle": "Visez le ciel : le fond de la photo devient une rampe.",
		"spawn": Vector3(0, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 2), "size": Vector3(16, 1, 12)},
			{"pos": Vector3(0, 4.3, -12), "size": Vector3(3, 9.6, 3)},
		],
		"decor": [
			{"pos": Vector3(6, 0.5, 0), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, -3.2), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(-2, -0.01, 2.6), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"photos": [
			{"id": "pile", "pos": Vector3(0, 0.9, 5)},
			{"id": "escalier", "pos": Vector3(-3, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(3, 0.9, 4)},
		],
		"batteries": [Vector3(0, 9.1, -12), Vector3(0.9, 9.1, -12)],
		"teleporter": {"pos": Vector3(-5, 0, 4), "required": 2},
	},
	{
		"name": "La grande traversee",
		"subtitle": "Pont, plancher, escalier : une seule route au dessus du vide.",
		"spawn": Vector3(0, 1.2, 12),
		"spawn_yaw": 0.0,
		"kill_y": -13.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 10), "size": Vector3(10, 1, 8)},
			# Wide middle bank: the walkway's painted wall crosses it.
			{"pos": Vector3(0, -0.5, -1), "size": Vector3(12, 1, 6)},
			{"pos": Vector3(0, -0.5, -15), "size": Vector3(12, 1, 6)},
		],
		"decor": [
			{"pos": Vector3(-3.5, 0.5, 13), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, 7), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0, -0.01, -3.4), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(0, 0.9, 11)},
			{"id": "pile", "pos": Vector3(2, 0.9, 12)},
			{"id": "escalier", "pos": Vector3(-2, 0.9, 12)},
			{"id": "caisse", "pos": Vector3(0, 0.9, 13.2)},
		],
		"batteries": [Vector3(3, 0, 10), Vector3(0, 0, -16)],
		"teleporter": {"pos": Vector3(3, 0, -16.5), "required": 3},
	},
	{
		"name": "L'examen",
		"subtitle": "Cinq piles. Tout ce que vous savez, dans l'ordre qu'il faut.",
		"spawn": Vector3(-4, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 18)},
			{"pos": Vector3(8, 0.6, 6), "size": Vector3(2.5, 3.2, 2.5)},
			{"pos": Vector3(0, 1.4, -6), "size": Vector3(2.5, 3.8, 2.5)},
		],
		"decor": [
			# Showcase niche, 1.0 m deep (interact range is 1.7 m).
			{"pos": Vector3(3.9, 1.0, -6.75), "size": Vector3(0.4, 2, 1.1), "color": "battery_tip"},
			{"pos": Vector3(6.3, 1.0, -6.75), "size": Vector3(0.4, 2, 1.1), "color": "battery_tip"},
			{"pos": Vector3(5.1, 2.05, -6.75), "size": Vector3(2.8, 0.3, 1.1), "color": "battery_tip"},
			{"pos": Vector3(5.1, 1.0, -7.35), "size": Vector3(2.8, 2, 0.2), "color": "battery_tip"},
			{"pos": Vector3(5, -0.01, 2.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(-1.5, -0.01, 0), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(0, -0.01, -1.2), "size": Vector3(1.4, 0.06, 1.4), "color": "teal",
				"photo": "console", "aim": Vector3(0, 2.0, -4.5), "roll": 2},
			{"pos": Vector3(5.1, -0.01, -1.6), "size": Vector3(1.4, 0.06, 1.4), "color": "accent",
				"photo": "coffret", "aim": Vector3(5.1, 1.0, -6.0), "roll": 0},
		],
		"erasables": [
			{"pos": Vector3(-6.5, 1.25, 0), "size": Vector3(0.6, 3.5, 18)},
			{"pos": Vector3(5.1, 1.0, -6.25), "size": Vector3(2.4, 1.9, 0.15)},
		],
		"photos": [
			{"id": "corniche", "pos": Vector3(2, 0.9, 5)},
			{"id": "porte", "pos": Vector3(-3, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(3, 0.9, -2)},
			{"id": "console", "pos": Vector3(1, 0.9, -2)},
			{"id": "coffret", "pos": Vector3(-8.2, 0.9, -3)},
			{"id": "caisse", "pos": Vector3(-4, 0.9, 3)},
		],
		"batteries": [Vector3(8, 2.2, 6), Vector3(-8.2, 0, 2), Vector3(5.1, 0, -6.75), Vector3(0, 3.3, -6)],
		"teleporter": {"pos": Vector3(0, 0, 7), "required": 5},
	},
	{
		"name": "Le cliche",
		"subtitle": "Cadrez le ciel : une photo de rien perce tout.",
		"spawn": Vector3(0, 1.2, 4),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 2.5), "size": Vector3(12, 1, 5)},
			{"pos": Vector3(0, -0.5, -6), "size": Vector3(8, 1, 6)},
		],
		"decor": [
			{"pos": Vector3(4.5, 0.5, 3.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, -3.9), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(4, 0.15, 4), "size": Vector3(4, 0.3, 2)},
		],
		"cages": [
			{"pos": Vector3(0, 0, -6.5), "size": Vector3(3, 2.6, 3), "erasable": false, "roof": true},
		],
		"camera": {"pos": Vector3(-2, 0, 3.5), "films": 2},
		"photos": [],
		"batteries": [Vector3(3, 0, 3), Vector3(0.8, 0, -7)],
		"teleporter": {"pos": Vector3(0, 0, -6.5), "required": 2},
	},
	{
		"name": "Copie de travail",
		"subtitle": "Photographier copie. Poser remplace. Ne melangez pas les deux.",
		"spawn": Vector3(0, 1.2, 10),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 8), "size": Vector3(8, 1, 8)},
			{"pos": Vector3(0, -0.5, -4), "size": Vector3(8, 1, 7)},
			{"pos": Vector3(0, 1.5, -10.5), "size": Vector3(8, 1, 5)},
		],
		"decor": [
			{"pos": Vector3(3, 0.5, 9), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(3, -0.01, 7), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0, -0.01, -4.5), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(0, -0.15, 2), "size": Vector3(2, 0.3, 5)},
		],
		"camera": {"pos": Vector3(2, 0, 9), "films": 1},
		"photos": [],
		"batteries": [Vector3(2, 0, -5)],
		"sealed_batteries": [Vector3(0, 2.0, -11)],
		"teleporter": {"pos": Vector3(-2, 2.0, -12), "required": 2},
	},
	{
		"name": "L'echafaudage",
		"subtitle": "Ce qui se pose retombe. Faites-en une marche.",
		"spawn": Vector3(0, 1.2, 6),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 5), "size": Vector3(16, 1, 10)},
			# The pit floor: 2.4 m below the rims. A copied crate plus a jump
			# clears it by half a metre; a bare jump never will.
			{"pos": Vector3(0, -2.9, -4), "size": Vector3(16, 1, 8)},
			{"pos": Vector3(0, -0.5, -11), "size": Vector3(16, 1, 6)},
		],
		"decor": [
			{"pos": Vector3(7, 0.5, 6), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(-3.4, -0.01, 3), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0, -2.41, -4.6), "size": Vector3(1.2, 0.06, 1.2), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(-5, 0.7, 3), "size": Vector3(1.4, 1.4, 1.4)},
			{"pos": Vector3(-6.6, 0.7, 1.8), "size": Vector3(1.4, 1.4, 1.4)},
		],
		"camera": {"pos": Vector3(0, 0, 5), "films": 3},
		"photos": [],
		"batteries": [],
		"sealed_batteries": [Vector3(5, 0, -11), Vector3(3, -2.4, -3)],
		"teleporter": {"pos": Vector3(-5, 0, -11.5), "required": 2},
	},
	{
		"name": "A travers les barreaux",
		"subtitle": "Les barreaux n'arretent pas l'objectif. Le gouffre, si.",
		"spawn": Vector3(0, 1.2, 6),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 2), "size": Vector3(14, 1, 12)},
			# Unreachable tower island: 5 m gap, 3 m higher.
			{"pos": Vector3(0, 1.0, -12), "size": Vector3(6, 4, 6)},
		],
		"decor": [
			{"pos": Vector3(6, 0.5, 6), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(0, -0.01, -3.2), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0, -0.01, 7), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(0, 3.0, -12), "size": Vector3(3, 2.2, 3), "sealed": true, "roof": true},
		],
		"camera": {"pos": Vector3(0, 0, 4), "films": 2},
		"photos": [],
		"batteries": [Vector3(-0.6, 3.0, -11.6), Vector3(0.8, 3.0, -12.3), Vector3(5, 0, 4)],
		"teleporter": {"pos": Vector3(-4, 0, 5), "required": 3},
	},
	{
		"name": "Le studio",
		"subtitle": "Tout l'atelier en un plateau : composez votre plan de tournage.",
		"spawn": Vector3(-4, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 16)},
			{"pos": Vector3(7, 0.6, 5), "size": Vector3(2.5, 3.2, 2.5)},
			{"pos": Vector3(0, -0.5, -13), "size": Vector3(8, 1, 4)},
		],
		"decor": [
			{"pos": Vector3(-4, 0.5, -6), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(-1.6, -0.01, 0), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(4.6, -0.01, 1.6), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(3, -0.01, -1.8), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(0, -0.01, -7), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [
			{"pos": Vector3(-6.5, 1.25, 0), "size": Vector3(0.6, 3.5, 16)},
			{"pos": Vector3(5, 0.9, 2), "size": Vector3(4, 1.8, 1.8)},
		],
		"cages": [
			{"pos": Vector3(3, 0, -5), "size": Vector3(2.6, 2.2, 2.6), "sealed": true, "roof": true},
		],
		"camera": {"pos": Vector3(0, 0, 6), "films": 2},
		"photos": [
			{"id": "porte", "pos": Vector3(-3, 0.9, 4)},
			{"id": "corniche", "pos": Vector3(2, 0.9, 5)},
		],
		"batteries": [Vector3(3, 0, -5), Vector3(0, 0, -13)],
		"sealed_batteries": [Vector3(7, 2.2, 5), Vector3(-8, 0, 0)],
		"teleporter": {"pos": Vector3(2, 0, 7), "required": 3},
	},
	# --- v6, the matter that says no -------------------------------------------
	# Three additions, and all three are refusals rather than new powers:
	#   STEEL   a cage no placement breaks. The lens still reaches through the
	#           bars, so the way out is a copy, never a demolition.
	#   LEAD    a battery no film prints. It is worth as much in a teleporter,
	#           but it can never become two.
	#   WEIGHT  a crate placed upside down is 1 m above the eye instead of 1 m
	#           below it, so it FALLS. Stacking is dropping, not placing.
	# Each gets its own level, then two levels that need them together.
	{
		"name": "Acier",
		"subtitle": "L'acier ne cede a aucune photo. L'objectif, lui, passe entre les barreaux.",
		"spawn": Vector3(0, 1.2, 6),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(16, 1, 18)},
		],
		"decor": [
			{"pos": Vector3(-6, 0.5, 5), "size": Vector3(1, 1, 1), "color": "wood"},
			# Where to stand to frame the caged battery through the bars.
			{"pos": Vector3(0, -0.01, -2.6), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			# Where to put the copy down: open ground, the painted wall of the
			# shot lands past the far edge.
			{"pos": Vector3(-3.5, -0.01, 1.5), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(0, 0, -6), "size": Vector3(3, 2.6, 3), "sealed": true, "roof": true},
		],
		"camera": {"pos": Vector3(2, 0, 5), "films": 2},
		"photos": [],
		# The caged one is out of reach for good: a steel cage never opens. It
		# is a MODEL, not a pickup.
		"batteries": [Vector3(-0.8, 0, -6), Vector3(0.8, 0, -6)],
		"teleporter": {"pos": Vector3(-5, 0, 4), "required": 2},
	},
	{
		"name": "Plomb",
		"subtitle": "La pile de plomb ne s'imprime pas. Il faudra monter la chercher.",
		"spawn": Vector3(0, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(16, 1, 20)},
			# Pillar, 3.8 m: out of jump range, in stair range.
			{"pos": Vector3(0, 1.9, -7), "size": Vector3(2.5, 3.8, 2.5)},
		],
		"decor": [
			{"pos": Vector3(6, 0.5, 6), "size": Vector3(1, 1, 1), "color": "wood"},
			# The stairs need 6 m of run to clear the pillar: this is the spot.
			{"pos": Vector3(0, -0.01, 1.45), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			{"pos": Vector3(-4, -0.01, 3), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"camera": {"pos": Vector3(2, 0, 6), "films": 2},
		"photos": [
			{"id": "escalier", "pos": Vector3(-2, 0.9, 6)},
		],
		"batteries": [Vector3(-5, 0, -4)],
		# Leaden, on the pillar: no film will ever save you the climb.
		"sealed_batteries": [Vector3(0, 3.8, -7)],
		"teleporter": {"pos": Vector3(5, 0, -6), "required": 4},
	},
	{
		"name": "L'aplomb",
		"subtitle": "Une caisse posee a l'endroit tombe a vos pieds. A l'envers, elle tombe sur l'autre.",
		"spawn": Vector3(0, 1.2, 6),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 16)},
			# Tower top at 3.8: two stacked crates (2.6) plus a jump (1.5).
			# One crate alone tops out at 2.8 and misses.
			{"pos": Vector3(0, 1.9, -4), "size": Vector3(2.5, 3.8, 2.5)},
		],
		"decor": [
			{"pos": Vector3(-7.5, 0.5, 4), "size": Vector3(1, 1, 1), "color": "wood"},
			# The model crate, 1.3 m: small enough that its copy is loose.
			{"pos": Vector3(-5, 0.65, 1), "size": Vector3(1.3, 1.3, 1.3), "color": "wood_dark"},
			# Shooting mark: the painted wall of a shot from here lands past the
			# far edge, over the void.
			{"pos": Vector3(-5, -0.01, 4.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			# Where to stand to drop the second crate onto the first.
			{"pos": Vector3(0, -0.01, 1.6), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
		],
		"erasables": [],
		"camera": {"pos": Vector3(2, 0, 5), "films": 3},
		"photos": [],
		"batteries": [],
		"sealed_batteries": [Vector3(0, 3.8, -4), Vector3(7, 0, 5)],
		"teleporter": {"pos": Vector3(-6, 0, 6), "required": 2},
	},
	{
		"name": "La geole",
		"subtitle": "La seule pile copiable est sous acier. La seule pile a portee est en plomb.",
		"spawn": Vector3(-2, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 18)},
			# Ledge top at 2.1: above a jump, under a flight of stairs.
			{"pos": Vector3(5, 0.8, -5), "size": Vector3(5, 2.6, 5)},
		],
		"decor": [
			# Two metres on every side: too big for the film to print it as a
			# step, so it cannot become a free staircase to the ledge.
			{"pos": Vector3(-6, 1, 5), "size": Vector3(2, 2, 2), "color": "wood"},
			# THE shot of the level, in corail: where the flight of stairs goes.
			# Foot at z = 1.4, so 3.9 m of run to the ledge face at z = -2.5,
			# which puts the ramp at 2.58 m, over the 2.10 of the ledge.
			{"pos": Vector3(4, -0.01, 2.6), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			# Where to shoot the caged battery FROM THE GROUND. Standing on the
			# ledge is useless: the battery would sit 27.9 degrees under the eye,
			# outside the 25 degree half frame. From here it is 6.0 m away and
			# 18 degrees up, squarely in the picture.
			{"pos": Vector3(7.5, -0.01, 0.5), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			# Where to drop the copies: facing -z the sky wall lands at z = -10,
			# past the edge of the platform.
			{"pos": Vector3(-4, -0.01, 2), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(5, 2.1, -5), "size": Vector3(3, 2.2, 3), "sealed": true, "roof": true},
		],
		# Two films, and that is the whole balance: two copies fall one short of
		# the three the teleporter wants, so the leaden battery on the ledge is
		# not optional, and the stairs are the only way to it.
		"camera": {"pos": Vector3(0, 0, 6), "films": 2},
		"photos": [
			{"id": "escalier", "pos": Vector3(-3, 0.9, 5)},
		],
		# In the steel cage: the ONLY battery in this level a film can print.
		# It can be shot from the ground, and that is fine: the climb is paid
		# for by the leaden one, not by this.
		"batteries": [Vector3(5, 2.1, -5)],
		# On the ledge, in the open, and worth exactly one. No film will ever
		# save the climb.
		"sealed_batteries": [Vector3(3.4, 2.1, -3.2)],
		"teleporter": {"pos": Vector3(0, 0, 7), "required": 3},
	},
	{
		"name": "Le verdict",
		"subtitle": "Acier, plomb, gravite. Cinq piles, et rien de gratuit.",
		"spawn": Vector3(0, 1.2, 8),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(20, 1, 20)},
			# Mesa top at 3.30. One crate plus a jump reaches 2.81 and misses; two
			# stacked reach 4.11. The flip to 180 degrees is the only way up.
			{"pos": Vector3(6, 1.4, -5), "size": Vector3(5, 3.8, 5)},
			# Pillar top at 2.40. One crate plus a jump reaches 2.81, so 0.41 m of
			# margin; a bare jump reaches 1.51 and never will. The old 2.80 left
			# nine millimetres, which is a coin toss, not a puzzle.
			{"pos": Vector3(-6, 0.95, -5), "size": Vector3(2.2, 2.9, 2.2)},
		],
		"decor": [
			# Two metres a side, out of the spawn's face: too big to be printed as
			# a step, so no film can be spent turning it into a staircase.
			{"pos": Vector3(-4, 1, 7), "size": Vector3(2, 2, 2), "color": "wood"},
			# Crate marks. A catalog crate is born 2.6 m ahead and is 1.3 wide, so
			# its far face lands 3.25 m out: each mark sits 3.5 m from the face it
			# serves, which drops the crate 0.25 m IN FRONT of the obstacle instead
			# of inside it.
			{"pos": Vector3(6, -0.01, 1.0), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			{"pos": Vector3(-6, -0.01, -0.4), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
			# THE shot of the level, in corail: the caged battery from the ground,
			# 6.0 m away and 19 degrees up. Shooting it from the mesa is impossible,
			# it would sit 28 degrees under the eye and out of the 25 degree frame.
			{"pos": Vector3(8.5, -0.01, 0.5), "size": Vector3(1.4, 0.06, 1.4), "color": "accent"},
			# The lavender cage, 5.5 m from here and 5 degrees down: any placement
			# made from this mark opens it and drops the copies in the same gesture.
			{"pos": Vector3(-1, -0.01, -1.5), "size": Vector3(1.4, 0.06, 1.4), "color": "teal"},
		],
		"erasables": [],
		"cages": [
			# Steel, on the mesa: the only battery in the level a film can print.
			{"pos": Vector3(6, 3.3, -5), "size": Vector3(3, 2.2, 3), "sealed": true, "roof": true},
			# Lavender, on the ground, right next to it: the same object, and any
			# placement opens this one. The contrast IS the lesson.
			{"pos": Vector3(-1, 0, -7), "size": Vector3(2.4, 2.2, 2.4), "erasable": true, "roof": true},
		],
		# THE BALANCE OF THE EXAM, and the reason the crates are catalog photos
		# rather than shots: film is fungible. Any budget that lets the player buy
		# crates also lets him buy batteries instead, so as long as crates came out
		# of the camera, every climb had a price in batteries and could be skipped.
		# Crates now come from the four photos, film only ever buys copies:
		#   without climbing : 1 (lavender cage) + 3 copies      = 4, one short
		#   climbing         : + the two leaden ones             = 6, for 5 needed
		"camera": {"pos": Vector3(2, 0, 7), "films": 3},
		"photos": [
			{"id": "caisse", "pos": Vector3(-2, 0.9, 5.0)},
			{"id": "caisse", "pos": Vector3(-0.7, 0.9, 5.6)},
			{"id": "caisse", "pos": Vector3(0.6, 0.9, 5.0)},
			{"id": "caisse", "pos": Vector3(1.9, 0.9, 5.6)},
		],
		"batteries": [Vector3(6, 3.3, -5), Vector3(-1, 0, -7)],
		# The two that make the climbs compulsory: no film prints lead, so height
		# stays height.
		"sealed_batteries": [Vector3(4.0, 3.3, -3.0), Vector3(-6, 2.4, -5)],
		"teleporter": {"pos": Vector3(-7, 0, 7), "required": 5},
	},
]


static func count() -> int:
	return LEVELS.size()


static func get_def(index: int) -> Dictionary:
	if index < 0 or index >= LEVELS.size():
		return {}
	return LEVELS[index]
