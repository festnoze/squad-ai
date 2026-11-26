"""KITCHEN (2026-11-24): bake the kitchen handoff pack (ArtHandoff/Kitchen) from procedural models and textures.

Five furniture modules (base cabinet, drawer cabinet, sink unit, range, tall pantry) and five utensils (saucepan, frying
pan, stock pot, kettle, cutting board with knife). Metres, Y up, front +Z, pivot at the bottom centre (contact point).
Three procedural albedos are made here and shared: brushed steel, worktop composite, blond oak.

Run with tools/assets/.venv: python tools/assets/kitchen_handoff.py
"""

import json
import math
import zipfile

import numpy as np
from PIL import Image

from living_room_furniture import rounded_wood_top
from room_dressing import Model, OUT, grid_faces, rotated


DESTINATION = OUT.parent / "Kitchen"
ZIP_PATH = OUT.parents[1] / "Build" / "kitchen" / "Kitchen.zip"

STEEL_PNG = "kitchen_brushed_steel.png"
WORKTOP_PNG = "kitchen_worktop.png"
OAK_PNG = "kitchen_oak.png"

SAGE = "#8FA294"      # painted fronts
FRAME = "#768A7D"     # carcass sides
PLINTH = "#3F4843"
DARK = "#262C2F"
GLASS = "#1D2629"
HOB = "#22282B"


# ----- Procedural textures (tileable, 512 px) -----

def _box_blur_x(a, radius):
    out = np.zeros_like(a)
    for shift in range(-radius, radius + 1):
        out += np.roll(a, shift, axis=1)
    return out / (2 * radius + 1)


def _blur(a, radius):
    out = _box_blur_x(a, radius)
    return _box_blur_x(out.T, radius).T


def _save(rgb, name):
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").save(DESTINATION / name, optimize=True)


def make_textures():
    rng = np.random.default_rng(7)
    size = 512

    # Brushed stainless: long horizontal streaks (blurred along x only), a faint coarse sheen.
    fine = _box_blur_x(rng.normal(0, 1, (size, size)), 40)
    coarse = _blur(rng.normal(0, 1, (size, size)), 24)
    value = 196 + 26 * fine / fine.std() * .35 + 10 * coarse / coarse.std() * .5
    _save(np.stack([value - 2, value + 2, value + 1], -1), STEEL_PNG)

    # Worktop: warm ivory mineral composite with sparse grey and sand speckles.
    base = np.array((228.0, 224, 212))
    cloud = _blur(rng.normal(0, 1, (size, size)), 18)
    img = base + (2 * cloud / cloud.std())[..., None]
    for count, tone, radius in ((1400, (160, 156, 150), 1), (700, (190, 174, 148), 1), (500, (246, 244, 236), 1)):
        mask = np.zeros((size, size))
        mask[rng.integers(0, size, count), rng.integers(0, size, count)] = 1
        mask = np.clip(_blur(mask, radius) * 4, 0, 1)
        img = img * (1 - mask[..., None] * .8) + np.array(tone) * (mask[..., None] * .8)
    _save(img, WORKTOP_PNG)

    # Blond oak: grain along x (u), warped by tileable sinusoids, fine fibres and a few darker latewood lines.
    y, x = np.mgrid[0:size, 0:size] / size
    warp = (.035 * np.sin(2 * math.pi * (2 * x + .3)) + .02 * np.sin(2 * math.pi * (5 * x + 3 * y))
            + .012 * np.sin(2 * math.pi * (9 * x - 2 * y + .7)))
    rings = .5 + .5 * np.sin(2 * math.pi * 14 * (y + warp))
    rings = rings ** 3
    fibres = _box_blur_x(rng.normal(0, 1, (size, size)), 30)
    fibres /= fibres.std()
    light, dark = np.array((214.0, 182, 134)), np.array((176.0, 136, 88))
    t = np.clip(.3 + .3 * rings + .1 * fibres, 0, 1)[..., None]
    _save(light * (1 - t) + dark * t, OAK_PNG)


# ----- Shared materials -----

def matte(model):
    return model.material("Kitchen matte", roughness=.8)


def steel(model):
    return model.material("Kitchen brushed steel", roughness=.34, metallic=.64, texture=STEEL_PNG, repeat=True)


def worktop(model):
    return model.material("Kitchen worktop", roughness=.6, texture=WORKTOP_PNG, repeat=True)


def oak(model):
    return model.material("Kitchen oak", roughness=.62, texture=OAK_PNG, repeat=True)


def enamel(model):
    return model.material("Kitchen enamel and glass", roughness=.35, metallic=.1)


TILES = {"Kitchen brushed steel": .5, "Kitchen worktop": .6, "Kitchen oak": .45}


def project_uvs(model):
    """Box-projected UVs (metres / tile) for every textured material: tops by (x, z), fronts by (x, y), sides by (z, y).
    The steel streaks and the oak grain run along u, so they stay horizontal on every face."""
    for material, tile in TILES.items():
        pieces = model.parts.get(material)
        if not pieces:
            continue
        updated = []
        for v, n, _, c, f in pieces:
            a = np.abs(n)
            top = (a[:, 1] >= a[:, 0]) & (a[:, 1] >= a[:, 2])
            side = ~top & (a[:, 0] > a[:, 2])
            u = np.where(side, v[:, 2], v[:, 0])
            w = np.where(top, v[:, 2], v[:, 1])
            updated.append((v, n, (np.stack([u, w], 1) / tile).astype(np.float32), c, f))
        model.parts[material] = updated


# ----- Geometry helpers -----

def round_rect(hx, hz, radius, y, dz=0):
    points = []
    for x, z, start in ((hx-radius, hz-radius, 0), (radius-hx, hz-radius, 90),
                        (radius-hx, radius-hz, 180), (hx-radius, radius-hz, 270)):
        for angle in (start, start+45, start+90):
            a = math.radians(angle)
            points.append((x+radius*math.cos(a), y, dz+z+radius*math.sin(a)))
    return points


def ring_surface(model, material, rings, color="#FFFFFF"):
    points = [v for ring in rings for v in ring]
    model.add(material, points, grid_faces(len(rings), len(rings[0]), closed=True), color)


def flat_disc(model, material, center, radius, n, color):
    x, y, z = center
    points = [(x+radius*math.cos(a), y, z+radius*math.sin(a)) for a in np.linspace(0, 2*math.pi, n, endpoint=False)]
    model.add(material, points, [(0, i+1, i) for i in range(1, n-1)], color)


def plinth(model, width):
    # Recessed 5 cm from the fronts, 10 cm tall: the toe kick every base module shares.
    model.box(matte(model), (0, .05, -.035), (width-.03, .10, .52), PLINTH)


def carcass(model, width, top, bottom=.10):
    # Sides and back from z -0.30 to 0.25; the fronts stand on 0.25 to 0.27, the handles end at 0.295.
    model.box(matte(model), (0, (bottom+top)/2, -.025), (width-.01, top-bottom, .55), FRAME)


def front(model, width, y0, y1, color=SAGE):
    model.bevel_box(matte(model), (0, (y0+y1)/2, .26), (width, y1-y0, .02), color, .006)


def bar_handle(model, center, length, vertical=False):
    x, y, _ = center
    size = (.012, length, .014) if vertical else (length, .012, .014)
    model.box(steel(model), (x, y, .287), size, "#FFFFFF")


def counter_top(model, width):
    rounded_wood_top(model, worktop(model), width, .60, .86, .04, .012)


# ----- Furniture -----

def base_cabinet():
    model = Model("kitchen_base_cabinet")
    plinth(model, .60)
    carcass(model, .60, .86)
    front(model, .594, .705, .853)
    front(model, .594, .102, .699)
    bar_handle(model, (0, .80, 0), .16)
    bar_handle(model, (0, .645, 0), .16)
    counter_top(model, .60)
    return model


def drawer_cabinet():
    model = Model("kitchen_drawer_cabinet")
    plinth(model, .60)
    carcass(model, .60, .86)
    for y0, y1 in ((.102, .405), (.411, .645), (.651, .853)):
        front(model, .594, y0, y1)
        bar_handle(model, (0, y1-.05, 0), .20)
    counter_top(model, .60)
    return model


def sink_cabinet():
    """An 80 cm module: worktop at 0.90 around a pressed steel bowl with its drain, the tap's top at 1.08 (the game's
    kitchen_sink box: worktop 0.18 m under the box top)."""
    model = Model("kitchen_sink_cabinet")
    m, s, w = matte(model), steel(model), worktop(model)
    plinth(model, .80)
    # The carcass stops under the bowl; side posts, back rail and a false drawer front close the space around it.
    model.box(m, (0, .41, -.025), (.79, .62, .55), FRAME)
    for x in (-.378, .378):
        model.box(m, (x, .79, -.025), (.034, .14, .55), FRAME)
    model.box(m, (0, .79, -.285), (.72, .14, .03), FRAME)
    # Plain fronts here (12 triangles each) keep the bowl and the tap within the 400 triangle budget.
    model.box(m, (0, .779, .26), (.794, .148, .02), SAGE)
    for x in (-.1995, .1995):
        model.box(m, (x, .4005, .26), (.395, .597, .02), SAGE)
        bar_handle(model, (x - math.copysign(.15, x), .60, 0), .12, vertical=True)

    outer_low = round_rect(.396, .296, .012, .862)
    outer_top = round_rect(.400, .300, .016, .900)
    hole = round_rect(.271, .178, .029, .900, .034)
    ring_surface(model, w, (outer_low, outer_top, hole))
    # The bowl: a rim on the worktop, sloping walls, a flat bottom and its drain.
    rim = round_rect(.285, .192, .038, .9015, .034)
    inner = round_rect(.261, .166, .032, .897, .034)
    low = round_rect(.250, .154, .031, .865, .034)
    bottom = round_rect(.213, .119, .027, .734, .041)
    ring_surface(model, s, (rim, inner, low, bottom), "#D9DEDD")
    model.add(s, bottom, [(0, i+1, i) for i in range(1, len(bottom)-1)], "#C4CBCB")
    flat_disc(model, m, (0, .7345, .049), .026, 10, "#4D5859")

    faucet = ((.118, .905, -.225), (.118, 1.000, -.225), (.118, 1.040, -.21), (.118, 1.068, -.177),
              (.118, 1.065, -.140), (.118, 1.040, -.113), (.118, 1.013, -.106))
    model.tube(s, faucet, 5, .012, "#FFFFFF", np.array((1.0, 0, 0)))
    model.lathe(s, ((.024, .900), (.025, .908), (.019, .918)), 8, "#FFFFFF", center=(.118, 0, -.225))
    model.box(m, (.150, .935, -.221), (.046, .012, .013), "#8E9997")
    return model


def burner(model, x, z, r):
    ring = [[(x+radius*math.cos(a), .9, z+radius*math.sin(a))
             for a in np.linspace(0, 2*math.pi, 12, endpoint=False)] for radius in (r, r-.012)]
    ring_surface(model, matte(model), ring, "#6E7676")
    flat_disc(model, matte(model), (x, .9, z), r*.42, 10, "#3A4143")


def kitchen_range():
    """A 60 cm range: black glass hob with four burners, a control band with four knobs, a steel oven door with its
    window and bar handle. Same plinth and depth as the cabinets, so it sits in a run."""
    model = Model("kitchen_range")
    m, s, e = matte(model), steel(model), enamel(model)
    plinth(model, .60)
    model.box(m, (0, .485, -.025), (.59, .77, .55), "#8E9796")
    model.bevel_box(e, (0, .8845, 0), (.60, .03, .60), HOB, .005)
    for x, z, r in ((-.145, .125, .085), (.145, .125, .065), (-.145, -.140, .065), (.145, -.140, .085)):
        burner(model, x, z, r)
    model.box(s, (0, .815, .26), (.594, .09, .02), "#E4E7E6")
    for x in (-.21, -.07, .07, .21):
        model.box(m, (x, .815, .277), (.034, .034, .016), DARK)
    model.bevel_box(s, (0, .435, .26), (.594, .645, .02), "#FFFFFF", .006)
    model.quad(e, ((.215, .24, .2702), (.215, .58, .2702), (-.215, .58, .2702), (-.215, .24, .2702)), GLASS)
    model.box(s, (0, .695, .287), (.46, .016, .014), "#F2F4F3")
    return model


def tall_cabinet():
    """A 60 cm pantry, 2.0 m tall: two doors, vertical bar handles at the opening edge."""
    model = Model("kitchen_tall_cabinet")
    plinth(model, .60)
    carcass(model, .60, 2.0)
    front(model, .594, .102, 1.195)
    front(model, .594, 1.201, 1.995)
    bar_handle(model, (.245, 1.06, 0), .22, vertical=True)
    bar_handle(model, (.245, 1.34, 0), .22, vertical=True)
    return model


# ----- Utensils -----

def saucepan():
    model = Model("saucepan")
    s, m = steel(model), matte(model)
    # The lid covers the bowl: only the outer wall is modelled.
    model.lathe(s, ((0, 0), (.086, 0), (.100, .010), (.104, .110), (0, .110)), 12, "#FFFFFF")
    model.lathe(s, ((0, .108), (.109, .108), (.109, .116), (.086, .128), (0, .135)), 12, "#E9ECEB")
    model.lathe(m, ((.012, .135), (.019, .146), (0, .150)), 8, DARK)
    model.box(s, (.112, .092, 0), (.024, .022, .028), "#FFFFFF")
    model.bevel_box(m, (.185, .098, 0), (.13, .026, .032), DARK, .005)
    return model


def frying_pan():
    model = Model("frying_pan")
    iron = model.material("Kitchen cast iron", roughness=.7, metallic=.3)
    m = matte(model)
    model.lathe(iron, ((0, 0), (.096, 0), (.111, .005), (.133, .030), (.137, .038), (.131, .039),
                       (.125, .031), (.105, .010), (0, .009)), 14, "#596166")
    model.box(iron, (.146, .026, 0), (.03, .018, .03), "#596166")
    # Lighter than real cast iron so the pan still reads on the black hob from the game camera.
    model.bevel_box(m, (.225, .034, 0), (.15, .022, .036), "#9A7650", .006)
    return model


def stock_pot():
    model = Model("stock_pot")
    s, e, m = steel(model), enamel(model), matte(model)
    model.lathe(e, ((0, 0), (.108, 0), (.120, .012), (.120, .205), (0, .205)), 12, "#4F7C82")
    model.lathe(s, ((0, .203), (.125, .203), (.125, .211), (.098, .226), (0, .233)), 12, "#FFFFFF")
    model.lathe(m, ((.014, .233), (.021, .243), (0, .247)), 8, DARK)
    for side in (-1, 1):
        loop = [(side*(.118+.03*math.sin(a)), .17+.022*math.cos(a), 0) for a in np.linspace(0, math.pi, 5)]
        model.tube(s, loop, 4, .006, "#FFFFFF", np.array((0, 0, 1.0)))
    return model


def kettle():
    model = Model("kettle")
    e, m = enamel(model), matte(model)
    cream = "#E5DCC5"
    model.lathe(e, ((0, 0), (.086, 0), (.097, .012), (.100, .058), (.088, .125), (.052, .160), (0, .166)), 12, cream)
    model.lathe(m, ((.012, .164), (.016, .176), (0, .180)), 8, DARK)
    spout = ((.075, .05, 0), (.122, .095, 0), (.148, .135, 0), (.160, .150, 0))
    model.tube(e, spout, 5, .013, cream, np.array((0, 0, 1.0)))
    arch = [(0, .16+.085*math.sin(a), .065*math.cos(a)) for a in np.linspace(0, math.pi, 7)]
    model.tube(m, arch, 4, .008, DARK, np.array((1.0, 0, 0)))
    return model


def cutting_board():
    """An oak board with a chef's knife and a few carrot slices: one object, the knife lying on the front half."""
    model = Model("cutting_board")
    s, m, wood = steel(model), matte(model), oak(model)
    rounded_wood_top(model, wood, .38, .25, 0, .02, .02)
    # The knife, turned 12 degrees, lies on the board top (0.02).
    path = ((-.012, -.11), (.012, -.11), (.012, .07), (.007, .095), (-.001, .118), (-.012, .07))
    yaw, at = 78, (.01, .02, .055)
    low = rotated([(x, .0015, z) for x, z in path], yaw, at)
    high = rotated([(x, .004, z) for x, z in path], yaw, at)
    count = len(path)
    faces = [(count, count+i+1, count+i) for i in range(1, count-1)]
    faces += [(a, c, b) for a, b, c in grid_faces(2, count, closed=True)]
    model.add(s, low + high, faces, "#FFFFFF")
    handle_center = rotated(((0, .007, -.165),), yaw, at)[0]
    model.bevel_box(m, handle_center, (.026, .014, .11), DARK, .003, yaw=yaw)
    for x, z in ((-.07, -.05), (-.035, -.075), (.0, -.045)):
        model.lathe(m, ((0, .02), (.016, .02), (.016, .028), (0, .028)), 7, "#D9822B", center=(x, 0, z))
    return model


# ----- Pack -----

FURNITURE = "meuble"
UTENSIL = "ustensile"

ITEMS = [
    (base_cabinet, "Meuble bas porte et tiroir", FURNITURE,
     "Module de 60 cm sous plan de travail (plan à 0,90 m). Habille un comptoir (counter) en ligne de modules.",
     {"worktop": [0, .90, 0]}, ["counter"]),
    (drawer_cabinet, "Meuble bas à trois tiroirs", FURNITURE,
     "Module de 60 cm, alterne avec le meuble bas porte dans une ligne de comptoir.",
     {"worktop": [0, .90, 0]}, ["counter"]),
    (sink_cabinet, "Meuble évier inox", FURNITURE,
     "Module de 80 cm, cuve inox, bonde et mitigeur. Plan à 0,90 m, haut du robinet à 1,08 m (boîte kitchen_sink).",
     {"worktop": [0, .90, 0], "tap_top": [.118, 1.08, -.17]}, ["kitchen_sink"]),
    (kitchen_range, "Cuisinière four et plaque", FURNITURE,
     "Module de 60 cm : plaque vitrocéramique quatre foyers, bandeau de manettes, porte de four vitrée.",
     {"hob": [0, .90, 0]}, ["stove"]),
    (tall_cabinet, "Colonne de rangement", FURNITURE,
     "Colonne de 60 cm, 2,0 m de haut, deux portes. Bout de ligne ou à côté du réfrigérateur.",
     {}, ["wardrobe", "cabinet"]),
    (saucepan, "Casserole avec couvercle", UTENSIL,
     "Sur un foyer de la plaque ou sur le plan. Manche vers +X (vers -X dans Unity).", {}, ["stove", "counter"]),
    (frying_pan, "Poêle en fonte", UTENSIL,
     "Sur un foyer avant, manche vers le côté. Manche vers +X (vers -X dans Unity).", {}, ["stove", "counter"]),
    (stock_pot, "Faitout émaillé", UTENSIL,
     "Sur un grand foyer arrière ou sur le plan.", {}, ["stove", "counter"]),
    (kettle, "Bouilloire émaillée", UTENSIL,
     "Sur un foyer, ou sur le plan près de l'évier ou de la cuisinière.", {}, ["stove", "counter", "table"]),
    (cutting_board, "Planche à découper et couteau", UTENSIL,
     "Sur le plan de travail ou la table de cuisine. Planche, couteau et rondelles de carotte forment un seul objet.",
     {}, ["counter", "table"]),
]


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    make_textures()
    assets = []
    for make, name, category, placement, anchors, kinds in ITEMS:
        model = make()
        project_uvs(model)
        stats = model.save(DESTINATION)
        lo, hi = np.array(stats["bounds_min_m"]), np.array(stats["bounds_max_m"])
        assets.append({
            "id": model.name, "name_fr": name, "category": category, "file": f"{model.name}.glb",
            "placement_fr": placement, "pivot": "contact inférieur au centre, Y vers le haut, façade +Z",
            "dimensions_m": np.round(hi - lo, 3).tolist(),
            "anchors_local_m": anchors,
            ("dress_kinds" if category == FURNITURE else "host_kinds"): kinds,
            "materials": list(model.parts.keys()),
            "textures": sorted({m[2] for k, m in model.materials.items() if m[2] and k in model.parts}),
            **stats,
        })
    inventory = {
        "project": "Out of Sight / games/out_of_sight",
        "format": "GLB 2.0 autonome, mètres, Y vers le haut, façade +Z, pivot au contact inférieur centré",
        "placement_fr": [
            "Modules bas : plan de travail à 0,90 m, profondeur 0,60 m, socle en retrait de 5 cm. Aligner les modules "
            "côte à côte sur une même ligne ; la cuisinière et l'évier partagent la même profondeur et le même socle.",
            "La façade est en +Z. Si un point de pose attend une façade -Z, tourner de 180° autour de Y.",
            "Les couleurs unies sont en COLOR_0. Trois albédos partagés : inox brossé (évier, four, casseroles, poignées), "
            "composite de plan de travail, chêne blond (planche). Mutualiser un seul matériau par albédo.",
            "Les ustensiles se posent sur le haut d'un hôte (foyer, plan, table) ; leur pivot est leur point de contact.",
        ],
        "textures": {
            STEEL_PNG: "Inox brossé répétable, stries horizontales le long de U (512 px, procédural).",
            WORKTOP_PNG: "Composite minéral ivoire à mouchetures grises et sable, répétable (512 px, procédural).",
            OAK_PNG: "Chêne blond répétable, fil le long de U (512 px, procédural).",
        },
        "props": assets,
    }
    (DESTINATION / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DESTINATION.iterdir()):
            if path.suffix in (".glb", ".png", ".json"):
                archive.write(path, f"Kitchen/{path.name}")
    for item in assets:
        print(f"{item['file']}: {item['triangles']} tris, {item['material_slots']} materials, "
              f"size {item['dimensions_m']}, min {item['bounds_min_m']} max {item['bounds_max_m']}")


if __name__ == "__main__":
    main()
