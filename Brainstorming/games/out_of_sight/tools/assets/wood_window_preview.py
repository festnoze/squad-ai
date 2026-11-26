"""Build the standalone timber casement window and its transparent glTF material."""

import json
import math
import shutil
import struct

import numpy as np

from living_room_furniture import DESTINATION as FURNITURE, WOOD, wood_box
from room_dressing import Model, OUT, grid_faces, unit


DESTINATION = OUT.parent / "WoodWindow"
GLASS = "Clear glazing"
WIDTH = 1.32
HEIGHT = 1.36


def glazed_leaf(model, wood, seal, glass, x0, x1):
    """In-plane profiles and glass, measured from the bottom of the frame."""
    y0, y1 = .071, HEIGHT - .056
    stile, rail, bar = .039, .041, .032
    depth, front = .065, .039
    center = (x0 + x1) / 2
    inner_left, inner_right = x0 + stile, x1 - stile
    wood_box(model, wood, (x0 + stile/2, (y0+y1)/2, front), (stile, y1-y0, depth),
             shift=.34 + x0, grain_axis=1)
    wood_box(model, wood, (x1 - stile/2, (y0+y1)/2, front), (stile, y1-y0, depth),
             shift=.66 + x0, grain_axis=1)
    glass_bottom = y0 + rail
    pane_height = (y1 - rail - glass_bottom - 2*bar) / 3
    for y, thick, shift in (
        (y0+rail/2, rail, .43), (y1-rail/2, rail, .70),
        (glass_bottom+pane_height+bar/2, bar, .57),
        (glass_bottom+2*pane_height+1.5*bar, bar, .63),
    ):
        wood_box(model, wood, (center, y, front), (inner_right-inner_left, thick, depth),
                 shift=shift+x0)
    for row in range(3):
        low = glass_bottom + row*(pane_height+bar)
        high = low + pane_height
        # A shadowed rebate isolates the transparent pane from the varnished timber.
        gasket, rebate_y, rebate_z = .004, (low+high)/2, .046
        for x in (inner_left+gasket/2, inner_right-gasket/2):
            model.box(seal, (x, rebate_y, rebate_z), (gasket, high-low, .010), "#33352E")
        for y in (low+gasket/2, high-gasket/2):
            model.box(seal, (center, y, rebate_z), (inner_right-inner_left-2*gasket, gasket, .010), "#33352E")
        a, b = inner_left+gasket*.4, inner_right-gasket*.4
        c, d = low+gasket*.4, high-gasket*.4
        model.quad(glass, ((a,c,rebate_z), (b,c,rebate_z), (b,d,rebate_z), (a,d,rebate_z)),
                   uv=((0,1), (1,1), (1,0), (0,0)))


def handle(model, hardware):
    """One curved, tapered lever on a slim backplate near the meeting stile."""
    x, spindle = -.018, .710
    model.bevel_box(hardware, (x, spindle-.014, .077), (.025,.077,.014), "#B9BFC4", .003)
    model.box(hardware, (x, spindle-.044, .084), (.0045,.0018,.002), "#555D65")
    # The first sections clear the backplate before the grip turns downward.
    sections = (
        ((x, .710, .082), .0085, .0085), ((x, .710, .099), .009, .009),
        ((x, .707, .114), .010, .009), ((x, .697, .126), .0105, .0085),
        ((x, .678, .131), .011, .0085), ((x, .610, .131), .0105, .0085),
        ((x, .559, .127), .009, .0075), ((x, .550, .124), .006, .005),
    )
    path = np.array([center for center, _, _ in sections])
    lateral = np.array((1, 0, 0))
    sides = 10
    rings = []
    for i, (center, width, depth) in enumerate(sections):
        tangent = unit(path[min(i+1, len(path)-1)] - path[max(i-1, 0)])
        normal = np.cross(lateral, tangent)
        rings.append([
            center + normal * (depth*math.cos(angle)) + lateral * (width*math.sin(angle))
            for angle in (math.tau*j/sides for j in range(sides))
        ])
    silver = "#D7DCE1"
    vertices = [point for ring in rings for point in ring]
    faces = [face[::-1] for face in grid_faces(len(rings), sides, closed=True)]
    model.add(hardware, vertices, faces, silver)
    for ring in (rings[0][::-1], rings[-1]):
        model.add(hardware, ring, [(0, i, i+1) for i in range(1, sides-1)], silver)


def window():
    model = Model("wood_casement_window")
    wood = model.material("Satin walnut", roughness=.50, texture=WOOD, repeat=True)
    seal = model.material("Glazing gasket", roughness=.82)
    hardware = model.material("Satin metal hardware", roughness=.34, metallic=.54)
    glass = model.material(GLASS, roughness=.11, metallic=0, double_sided=True)
    for side in (-1, 1):
        jamb_x = side * (WIDTH/2-.025)
        wood_box(model, wood, (jamb_x, .69125, -.022), (.050, 1.2375, .162),
                 shift=.18*side, grain_axis=1)
        # Narrow projecting trim gives the frame a readable edge at oblique angles.
        wood_box(model, wood, (jamb_x+side*.008, .699, .064), (.030, 1.258, .022),
                 shift=.18*side, grain_axis=1, shade="#EAE2DA")
    wood_box(model, wood, (0, HEIGHT-.025, -.022), (WIDTH, .050, .162), shift=.60)
    wood_box(model, wood, (0, HEIGHT-.016, .064), (WIDTH, .032, .022), shift=.60, shade="#EAE2DA")
    wood_box(model, wood, (0, .039, -.022), (WIDTH, .067, .162), shift=.81)
    # The interior sill extends just beyond the jambs and the room face of the reveal.
    wood_box(model, wood, (0, .016, .017), (WIDTH+.060, .032, .244), shift=.00)
    wood_box(model, wood, (0, .024, .141), (WIDTH+.056, .011, .014), shift=.00, shade="#EEE4DB")
    for bounds in ((-.606, -.004), (.004, .606)):
        glazed_leaf(model, wood, seal, glass, *bounds)
    # Hinges and the inward-facing lever are deliberately readable in silhouette.
    for x in (-.607, .607):
        for y in (.248, 1.124):
            model.lathe(hardware, ((0,-.028), (.009,-.028), (.009,.028), (0,.028)), 7,
                        "#82674A", center=(x,y,.079))
    handle(model, hardware)
    return model


def add_transparency(path):
    data = path.read_bytes()
    json_size = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20+json_size])
    for material in doc["materials"]:
        if material["name"] == GLASS:
            material["alphaMode"] = "BLEND"
            material["pbrMetallicRoughness"]["baseColorFactor"] = [.90, .95, .96, .035]
            break
    else:
        raise ValueError("Window glass material was not exported.")
    encoded = json.dumps(doc, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary = data[20+json_size:]
    path.write_bytes(struct.pack("<4sIIII", b"glTF", 2, 20+len(encoded)+len(binary), len(encoded), 0x4E4F534A)
                     + encoded + binary)


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FURNITURE / WOOD, DESTINATION / WOOD)
    model = window()
    model.parts[GLASS] = model.parts.pop(GLASS)
    stats = model.save(DESTINATION)
    filename = model.name + ".glb"
    add_transparency(DESTINATION / filename)
    stats["dimensions_m"] = np.round(np.subtract(stats["bounds_max_m"], stats["bounds_min_m"]), 3).tolist()
    inventory = {
        "model": filename, "texture": WOOD, "nominal_opening_m": [WIDTH, HEIGHT],
        "pivot": "Bas central, Y vers le haut, face intérieure +Z dans le GLB.",
        "glazing": "Six carreaux identiques, trois par battant, avec joints et matériau transparent double face.",
        "unity_glazing": {
            "shader_file": "WindowGlass.shader",
            "material_slot": GLASS,
            "description": "Fins reflets blancs dessinés dans les UV de chaque carreau et décalés selon l’angle de vue.",
        },
        "hardware": "Poignée intérieure argentée en métal satiné et quatre charnières. Modèle en position fermée.",
        "stats": stats,
    }
    (DESTINATION / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
