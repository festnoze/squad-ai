class_name LevelDefs
## The fifteen levels, as pure data (PRD section 5, docs/LEVELS_V2.md for 6+).
## Coordinates are world space, platform tops sit at y = 0 unless stated
## otherwise. Every list is consumed by LevelBuilder; the unit suite checks
## the invariants (spawn above ground, enough batteries reachable counting
## photo-in-photo chains, referenced photos exist, cages on platforms).

const LEVELS := [
	{
		"name": "Premiers pas",
		"subtitle": "Prenez la photo, cadrez le vide, posez.",
		"spawn": Vector3(0, 1.2, 5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 2), "size": Vector3(10, 1, 10)},
			{"pos": Vector3(0, -0.5, -12), "size": Vector3(10, 1, 8)},
		],
		"decor": [
			{"pos": Vector3(-3.5, 0.5, 5.5), "size": Vector3(1, 1, 1), "color": "wood"},
			{"pos": Vector3(-3.5, 1.3, 5.2), "size": Vector3(0.6, 0.6, 0.6), "color": "wood_dark"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(1.5, 0.9, 4)},
		],
		"batteries": [Vector3(0, 0, -10.5)],
		"teleporter": {"pos": Vector3(0, 0, -14), "required": 1},
	},
	{
		"name": "Copie conforme",
		"subtitle": "Une photo de pile devient une vraie pile.",
		"spawn": Vector3(0, 1.2, 5.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(14, 1, 14)},
		],
		"decor": [
			{"pos": Vector3(5.5, 0.5, 3), "size": Vector3(1.2, 1, 1.2), "color": "wood"},
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
		"subtitle": "Un escalier pose la ou vous regardez.",
		"spawn": Vector3(0, 1.2, 5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(18, 1, 14)},
			{"pos": Vector3(5, 2.0, -2), "size": Vector3(4, 5, 4)},
		],
		"decor": [
			{"pos": Vector3(-7, 0.5, -5.5), "size": Vector3(1, 1, 1), "color": "wood"},
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
		"subtitle": "Ce qui gene dans le cadre disparait.",
		"spawn": Vector3(0, 1.2, 12),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(10, 1, 28)},
		],
		"decor": [
			{"pos": Vector3(4, 0.5, 10), "size": Vector3(1, 1, 1), "color": "wood"},
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
			{"pos": Vector3(0, -0.5, -14), "size": Vector3(8, 1, 8)},
			{"pos": Vector3(10, 1.5, 0), "size": Vector3(6, 4, 6)},
		],
		"decor": [
			{"pos": Vector3(4.5, 0.5, -4.5), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [
			{"pos": Vector3(-4.5, 0.6, -4.5), "size": Vector3(1.2, 1.2, 1.2)},
		],
		"photos": [
			{"id": "passerelle", "pos": Vector3(3, 0.9, 2)},
			{"id": "escalier", "pos": Vector3(-3, 0.9, 2)},
			{"id": "pile", "pos": Vector3(2, 0.9, -15)},
		],
		"batteries": [Vector3(0, 0, -14), Vector3(10, 3.5, 0)],
		"teleporter": {"pos": Vector3(0, 0, 4), "required": 3},
	},
	{
		"name": "La cage",
		"subtitle": "Les barreaux lavande sont dans le cadre comme le reste.",
		"spawn": Vector3(0, 1.2, 5.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(16, 1, 14)},
		],
		"decor": [
			{"pos": Vector3(-6, 0.5, 2), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(4, 0, -4), "size": Vector3(2.5, 2.5, 2.5), "erasable": true, "roof": true},
		],
		"photos": [
			{"id": "porte", "pos": Vector3(0, 0.9, 4)},
		],
		"batteries": [Vector3(4, 0, -4), Vector3(-5, 0, -5)],
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
			{"pos": Vector3(5.5, 0.6, -4.75), "size": Vector3(3, 3.2, 3.5)},
			{"pos": Vector3(-5.5, 1.0, -4.75), "size": Vector3(3, 4, 3.5)},
		],
		"decor": [
			{"pos": Vector3(-3, 0.75, 1.5), "size": Vector3(1.5, 1.5, 1.5), "color": "stone"},
		],
		"erasables": [],
		"photos": [
			{"id": "corniche", "pos": Vector3(1, 0.9, 5)},
			{"id": "corniche", "pos": Vector3(-1, 0.9, 5)},
		],
		"batteries": [Vector3(5.5, 2.2, -4.75), Vector3(-5.5, 3.0, -4.75)],
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
		"subtitle": "On n'efface pas le sombre. On passe par dessus.",
		"spawn": Vector3(0, 1.2, 6.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(20, 1, 16)},
		],
		"decor": [
			{"pos": Vector3(8, 0.5, 5), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [],
		"cages": [
			{"pos": Vector3(5, 0, -3), "size": Vector3(4, 2.8, 4), "erasable": false, "roof": false},
		],
		"photos": [
			{"id": "escalier", "pos": Vector3(-2, 0.9, 4)},
			{"id": "console", "pos": Vector3(5.8, 0.9, -2.2)},
			{"id": "caisse", "pos": Vector3(4.2, 0.9, -3.8)},
		],
		"batteries": [Vector3(5, 0, -3), Vector3(-7, 0, -6)],
		"teleporter": {"pos": Vector3(-5, 0, 5), "required": 2},
	},
	{
		"name": "Plongeon",
		"subtitle": "Visez vers le bas : la passerelle plonge avec vous.",
		"spawn": Vector3(0, 1.2, 7),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 4), "size": Vector3(10, 1, 8)},
			{"pos": Vector3(0, -5.5, -9), "size": Vector3(7, 1, 7)},
		],
		"decor": [
			{"pos": Vector3(3.5, 0.5, 6.5), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(0, 0.9, 6)},
		],
		"batteries": [Vector3(3, 0, 5), Vector3(2, -5, -9)],
		"teleporter": {"pos": Vector3(0, -5, -11), "required": 2},
	},
	{
		"name": "Sous le pont",
		"subtitle": "Le cadre decoupe aussi les sols. Traversez d'abord, percez ensuite.",
		"spawn": Vector3(0, 1.2, 8.5),
		"spawn_yaw": 0.0,
		"kill_y": -12.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 6), "size": Vector3(10, 1, 8)},
			{"pos": Vector3(0, -0.5, -10), "size": Vector3(12, 1, 8)},
			{"pos": Vector3(4, 0.8, -11), "size": Vector3(3, 2.6, 3)},
			{"pos": Vector3(0, -4.5, -2), "size": Vector3(2, 1, 6)},
		],
		"decor": [
			{"pos": Vector3(-4, 0.5, -8), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [
			{"pos": Vector3(0, -0.15, -2), "size": Vector3(2, 0.3, 8.4)},
		],
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
		"subtitle": "Chaque photo ouvre la voie vers la suivante.",
		"spawn": Vector3(-1, 1.2, 6.5),
		"spawn_yaw": 0.0,
		"kill_y": -10.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 0), "size": Vector3(20, 1, 16)},
			{"pos": Vector3(7, 0.6, 5), "size": Vector3(3, 3.2, 3)},
		],
		"decor": [
			{"pos": Vector3(3.0, 1.0, -6.5), "size": Vector3(0.4, 2, 1.6), "color": "battery_tip"},
			{"pos": Vector3(5.6, 1.0, -6.5), "size": Vector3(0.4, 2, 1.6), "color": "battery_tip"},
			{"pos": Vector3(4.3, 2.1, -6.5), "size": Vector3(3, 0.3, 1.6), "color": "battery_tip"},
			{"pos": Vector3(4.3, 1.0, -7.2), "size": Vector3(3, 2, 0.2), "color": "battery_tip"},
		],
		"erasables": [
			{"pos": Vector3(-6.5, 1.25, 0), "size": Vector3(0.6, 3.5, 16)},
			{"pos": Vector3(4.3, 1.0, -5.9), "size": Vector3(2.4, 1.9, 0.15)},
		],
		"photos": [
			{"id": "corniche", "pos": Vector3(2, 0.9, 6)},
			{"id": "porte", "pos": Vector3(7, 3.1, 5)},
			{"id": "coffret", "pos": Vector3(-8.2, 0.9, -3)},
		],
		"batteries": [Vector3(7, 2.2, 5), Vector3(-8.2, 0, 2), Vector3(4.3, 0, -6.6)],
		"teleporter": {"pos": Vector3(0, 0, -6), "required": 3},
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
		],
		"erasables": [],
		"photos": [
			{"id": "pile", "pos": Vector3(0, 0.9, 5)},
			{"id": "escalier", "pos": Vector3(-3, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(3, 0.9, 4)},
		],
		"batteries": [Vector3(0, 9.1, -12), Vector3(5, 0, 4)],
		"teleporter": {"pos": Vector3(-5, 0, 4), "required": 2},
	},
	{
		"name": "La grande traversee",
		"subtitle": "Pont, plancher, escalier : une seule route au dessus du vide.",
		"spawn": Vector3(0, 1.2, 15),
		"spawn_yaw": 0.0,
		"kill_y": -13.0,
		"platforms": [
			{"pos": Vector3(0, -0.5, 12), "size": Vector3(10, 1, 8)},
			{"pos": Vector3(0, -0.5, -2), "size": Vector3(4, 1, 4)},
			{"pos": Vector3(0, -0.5, -20), "size": Vector3(10, 1, 6)},
		],
		"decor": [
			{"pos": Vector3(-3.5, 0.5, 14.5), "size": Vector3(1, 1, 1), "color": "wood"},
		],
		"erasables": [],
		"photos": [
			{"id": "passerelle", "pos": Vector3(0, 0.9, 13)},
			{"id": "pile", "pos": Vector3(2, 0.9, 14)},
			{"id": "escalier", "pos": Vector3(-2, 0.9, 14)},
			{"id": "caisse", "pos": Vector3(0, 0.9, 15.2)},
		],
		"batteries": [Vector3(3, 0, 10), Vector3(0, 0, -20)],
		"teleporter": {"pos": Vector3(0, 0, -21.5), "required": 2},
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
			{"pos": Vector3(3.8, 1.0, -7), "size": Vector3(0.4, 2, 1.6), "color": "battery_tip"},
			{"pos": Vector3(6.4, 1.0, -7), "size": Vector3(0.4, 2, 1.6), "color": "battery_tip"},
			{"pos": Vector3(5.1, 2.1, -7), "size": Vector3(3, 0.3, 1.6), "color": "battery_tip"},
			{"pos": Vector3(5.1, 1.0, -7.7), "size": Vector3(3, 2, 0.2), "color": "battery_tip"},
		],
		"erasables": [
			{"pos": Vector3(-6.5, 1.25, 0), "size": Vector3(0.6, 3.5, 18)},
			{"pos": Vector3(5.1, 1.0, -6.4), "size": Vector3(2.4, 1.9, 0.15)},
		],
		"photos": [
			{"id": "corniche", "pos": Vector3(2, 0.9, 5)},
			{"id": "porte", "pos": Vector3(-3, 0.9, 4)},
			{"id": "caisse", "pos": Vector3(3, 0.9, -2)},
			{"id": "console", "pos": Vector3(1, 0.9, -2)},
			{"id": "coffret", "pos": Vector3(-8.2, 0.9, -3)},
		],
		"batteries": [Vector3(8, 2.2, 6), Vector3(-8.2, 0, 2), Vector3(5.1, 0, -7.1), Vector3(0, 3.3, -6)],
		"teleporter": {"pos": Vector3(0, 0, 7), "required": 5},
	},
]


static func count() -> int:
	return LEVELS.size()


static func get_def(index: int) -> Dictionary:
	if index < 0 or index >= LEVELS.size():
		return {}
	return LEVELS[index]
