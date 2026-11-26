"""Bake the room dressing handoff GLBs from their models and three supplied PNGs."""

import json
import math
import struct
from pathlib import Path

import numpy as np


OUT = Path(__file__).resolve().parents[2] / "ArtHandoff" / "RoomDressing"
UP = np.array((0.0, 1.0, 0.0))
WHITE = "#FFFFFF"


def linear_color(code):
    channels = [int(code[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels] + [1.0]


def unit(vector):
    return vector / np.linalg.norm(vector)


class Model:
    def __init__(self, name):
        self.name = name
        self.materials = {}
        self.parts = {}

    def material(self, name, roughness=0.85, metallic=0, texture=None, double_sided=False, repeat=False):
        self.materials[name] = (roughness, metallic, texture, double_sided, repeat)
        return name

    def add(self, material, vertices, triangles, color=WHITE, uv=None):
        vertices = np.asarray(vertices, dtype=np.float32)
        triangles = np.asarray(triangles, dtype=np.int32)
        points = vertices[triangles]
        face_normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        if (np.linalg.norm(face_normals, axis=1) < 1e-10).any():
            raise ValueError(f"{self.name}: degenerate triangle in {material}")
        normals = np.zeros_like(vertices)
        for i in range(3):
            np.add.at(normals, triangles[:, i], face_normals)
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-10)
        colors = np.broadcast_to(np.array(linear_color(color), dtype=np.float32), (len(vertices), 4))
        coords = np.asarray(uv, dtype=np.float32) if uv is not None else np.zeros((len(vertices), 2), dtype=np.float32)
        self.parts.setdefault(material, []).append((vertices, normals, coords, colors, triangles))

    def quad(self, material, points, color=WHITE, uv=None):
        self.add(material, points, ((0, 1, 2), (0, 2, 3)), color, uv)

    def box(self, material, center, size, color, yaw=0):
        half = np.asarray(size) / 2
        axes = np.eye(3)
        for axis in range(3):
            u, v = (axis + 1) % 3, (axis + 2) % 3
            for side in (-1, 1):
                points = [
                    side * half[axis] * axes[axis] + a * half[u] * axes[u] + b * half[v] * axes[v]
                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                ]
                points = rotated(points, yaw, center)
                self.quad(material, points if side > 0 else points[::-1], color)

    def bevel_box(self, material, center, size, color, bevel, yaw=0):
        x, y, z = np.asarray(size) / 2
        b = min(bevel, x / 2, y / 2, z / 2)
        outline = ((x-b, -z), (x, -z+b), (x, z-b), (x-b, z), (-x+b, z), (-x, z-b), (-x, -z+b), (-x+b, -z))
        rings = [[(px * scale, height, pz * scale) for px, pz in outline]
                 for height, scale in ((-y, 0.92), (-y+b, 1), (y-b, 1), (y, 0.92))]
        points = rotated([point for ring in rings for point in ring], yaw, center)
        faces = grid_faces(4, 8, closed=True)
        self.add(material, points, faces, color)
        for ring, forward in ((points[:8], True), (points[-8:], False)):
            tris = [(0, i, i+1) if forward else (0, i+1, i) for i in range(1, 7)]
            self.add(material, ring, tris, color)

    def lathe(self, material, profile, segments, color, center=(0, 0, 0), oval=1):
        # A closed profile runs from bottom centre, around the wall, to inside centre.
        vertices = []
        rings = []
        for radius, y in profile:
            rings.append(list(range(len(vertices), len(vertices) + (segments if radius else 1))))
            for i in range(len(rings[-1])):
                angle = 2 * math.pi * i / segments
                vertices.append(np.array((radius * math.cos(angle), y, oval * radius * math.sin(angle))) + center)
        faces = []
        for low, high in zip(rings, rings[1:]):
            for i in range(segments):
                j = (i + 1) % segments
                if len(low) == 1:
                    faces.append((low[0], high[i], high[j]))
                elif len(high) == 1:
                    faces.append((low[i], high[0], low[j]))
                else:
                    faces.extend(((low[i], high[i], high[j]), (low[i], high[j], low[j])))
        self.add(material, vertices, faces, color)

    def tube(self, material, path, sides, radius, color, plane, closed=False):
        path = np.asarray(path, dtype=float)
        vertices = []
        for i, center in enumerate(path):
            previous = path[i - 1] if closed or i > 0 else center
            following = path[(i + 1) % len(path)] if closed or i + 1 < len(path) else center
            tangent = unit(following - previous)
            side_axis = unit(np.cross(plane, tangent))
            for j in range(sides):
                angle = 2 * math.pi * j / sides
                vertices.append(center + radius * (math.cos(angle) * side_axis + math.sin(angle) * plane))
        faces = [face[::-1] for face in grid_faces(len(path), sides, closed=True, loop=closed)]
        self.add(material, vertices, faces, color)

    def save(self, directory):
        writer = GLB(self.name)
        all_positions = []
        for material, pieces in self.parts.items():
            positions, normals, coords, colors, triangles = [], [], [], [], []
            offset = 0
            for p, n, t, c, f in pieces:
                positions.extend(p)
                normals.extend(n)
                coords.extend(t)
                colors.extend(c)
                triangles.extend(f + offset)
                offset += len(p)
            all_positions.extend(positions)
            writer.primitive(self.materials[material], material, positions, normals, coords, colors, triangles, directory)
        writer.save(directory / f"{self.name}.glb")
        bounds = np.asarray(all_positions, dtype=float)
        return {
            "triangles": sum(len(piece[4]) for pieces in self.parts.values() for piece in pieces),
            "material_slots": len(self.parts),
            "bounds_min_m": np.round(bounds.min(axis=0), 4).tolist(),
            "bounds_max_m": np.round(bounds.max(axis=0), 4).tolist(),
        }


def grid_faces(rows, columns, closed=False, loop=False):
    tris = []
    for row in range(rows if loop else rows - 1):
        for col in range(columns if closed else columns - 1):
            next_row, next_col = (row + 1) % rows, (col + 1) % columns
            a, b = row * columns + col, row * columns + next_col
            c, d = next_row * columns + col, next_row * columns + next_col
            tris.extend(((a, c, d), (a, d, b)))
    return tris


def rotated(points, yaw, center):
    angle = math.radians(yaw)
    c, s = math.cos(angle), math.sin(angle)
    return [(x * c + z * s + center[0], y + center[1], z * c - x * s + center[2]) for x, y, z in points]


class GLB:
    def __init__(self, name):
        self.bin = bytearray()
        self.data = {
            "asset": {"version": "2.0", "generator": "Out of Sight room dressing"},
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": []}],
            "buffers": [], "bufferViews": [], "accessors": [], "materials": [],
        }

    def view(self, raw, target=None):
        self.bin.extend(bytes(-len(self.bin) % 4))
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(raw)}
        self.bin.extend(raw)
        if target:
            view["target"] = target
        self.data["bufferViews"].append(view)
        return len(self.data["bufferViews"]) - 1

    def accessor(self, array, kind, indices=False, bounds=False):
        array = np.asarray(array, dtype="<u2" if indices else "<f4")
        accessor = {"bufferView": self.view(array.tobytes(), 34963 if indices else 34962),
                    "componentType": 5123 if indices else 5126, "count": len(array), "type": kind}
        if bounds:
            accessor.update({"min": array.min(axis=0).tolist(), "max": array.max(axis=0).tolist()})
        self.data["accessors"].append(accessor)
        return len(self.data["accessors"]) - 1

    def primitive(self, properties, name, p, n, uv, colors, tri, directory):
        roughness, metallic, texture, double_sided, repeat = properties
        pbr = {"roughnessFactor": roughness, "metallicFactor": metallic}
        material = {"name": name, "pbrMetallicRoughness": pbr, "doubleSided": double_sided}
        attrs = {
            "POSITION": self.accessor(p, "VEC3", bounds=True),
            "NORMAL": self.accessor(n, "VEC3"),
            "TEXCOORD_0": self.accessor(uv, "VEC2"),
            "COLOR_0": self.accessor(colors, "VEC4"),
        }
        if texture:
            image_view = self.view((directory / texture).read_bytes())
            images = self.data.setdefault("images", [])
            samplers = self.data.setdefault("samplers", [])
            textures = self.data.setdefault("textures", [])
            wrap = 10497 if repeat else 33071
            pbr["baseColorTexture"] = {"index": len(textures)}
            textures.append({"source": len(images), "sampler": len(samplers)})
            images.append({"name": Path(texture).stem, "bufferView": image_view, "mimeType": "image/png"})
            samplers.append({"wrapS": wrap, "wrapT": wrap, "magFilter": 9729, "minFilter": 9987})
        self.data["meshes"][0]["primitives"].append({
            "attributes": attrs, "indices": self.accessor(np.ravel(tri), "SCALAR", indices=True),
            "material": len(self.data["materials"]),
        })
        self.data["materials"].append(material)

    def save(self, path):
        self.bin.extend(bytes(-len(self.bin) % 4))
        self.data["buffers"] = [{"byteLength": len(self.bin)}]
        encoded = json.dumps(self.data, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        total = 12 + 8 + len(encoded) + 8 + len(self.bin)
        path.write_bytes(struct.pack("<4sIIII", b"glTF", 2, total, len(encoded), 0x4E4F534A)
                         + encoded + struct.pack("<II", len(self.bin), 0x004E4942) + self.bin)


def open_book():
    model = Model("open_book")
    solid = model.material("Dressing matte")
    print_material = model.material("Travel book spread", texture="book_spread.png")
    model.bevel_box(solid, (0, 0.004, 0), (0.342, 0.008, 0.232), "#394B5A", 0.002)
    xs = (-0.164, -0.114, -0.056, -0.019, 0, 0.019, 0.056, 0.114, 0.164)
    ys = (0.020, 0.022, 0.030, 0.024, 0.015, 0.024, 0.032, 0.026, 0.022)
    zs = (-0.110, 0, 0.110)
    points = [(x, y + 0.002 * (1 - abs(z) / 0.110), z) for z in zs for x, y in zip(xs, ys)]
    uv = [((x - xs[0]) / (xs[-1] - xs[0]), (z + 0.110) / 0.220) for z in zs for x in xs]
    model.add(print_material, points, grid_faces(len(zs), len(xs)), uv=uv)
    last = len(xs) * (len(zs) - 1)
    for i in range(len(xs) - 1):
        for edge, front in ((0, False), (last, True)):
            a, b = points[edge + i], points[edge + i + 1]
            quad = [(a[0], 0.008, a[2]), (b[0], 0.008, b[2]), b, a]
            model.quad(solid, quad if front else quad[::-1], "#D9CAAA")
    for i in range(len(zs) - 1):
        for edge, right in ((0, False), (len(xs) - 1, True)):
            a, b = points[i * len(xs) + edge], points[(i + 1) * len(xs) + edge]
            quad = [(a[0], 0.008, a[2]), a, b, (b[0], 0.008, b[2])]
            model.quad(solid, quad if right else quad[::-1], "#D9CAAA")
    return model


def photo_frame():
    model = Model("photo_frame")
    wood = model.material("Dressing matte")
    picture = model.material("Family photograph", texture="family_photo.png")
    tilt = math.radians(-10)

    def tilt_point(point):
        x, y, z = point
        return (x, y * math.cos(tilt) - z * math.sin(tilt) + 0.002,
                y * math.sin(tilt) + z * math.cos(tilt) + 0.024)

    def rim(x, y0, y1, z):
        return [(x, y0, z), (x, y1, z), (-x, y1, z), (-x, y0, z)]

    rings = [rim(0.078, 0, 0.190, -0.009), rim(0.078, 0, 0.190, 0.008),
             rim(0.075, 0.003, 0.187, 0.014), rim(0.063, 0.016, 0.174, 0.014),
             rim(0.060, 0.020, 0.170, 0.009)]
    for a, b, tint in zip(rings, rings[1:], ("#604535", "#A77951", "#8D6344", "#604535")):
        for i in range(4):
            j = (i + 1) % 4
            model.quad(wood, [tilt_point(p) for p in (a[i], a[j], b[j], b[i])], tint)
    model.quad(wood, [tilt_point(p) for p in rings[0][::-1]], "#564238")
    uv = ((1, 1), (1, 0), (0, 0), (0, 1))
    model.quad(picture, [tilt_point(p) for p in rim(0.061, 0.019, 0.171, 0.008)], uv=uv)
    brace = [(x, y, z) for x, y, z in ((-0.019, 0.093, -0.002), (0.019, 0.093, -0.002),
                                      (0.019, 0, -0.070), (-0.019, 0, -0.070))]
    shelf = [(x, y + 0.001, z - 0.006) for x, y, z in brace]
    model.quad(wood, brace[::-1], "#5D4638")
    model.quad(wood, shelf, "#725949")
    for i in range(4):
        j = (i + 1) % 4
        model.quad(wood, (brace[i], brace[j], shelf[j], shelf[i]), "#5D4638")
    return model


def draped_throw():
    model = Model("sofa_throw")
    fabric = model.material("Woven plaid", roughness=0.96, texture="plaid_weave.png", double_sided=True, repeat=True)
    # The anchor is the crest. Negative Z is the short tail behind the crest, positive Z is the long drop.
    profile = ((-0.133, -0.110), (-0.072, -0.078), (-0.024, -0.046), (0, -0.009), (-0.021, 0.048),
               (-0.085, 0.072), (-0.174, 0.079), (-0.268, 0.090), (-0.365, 0.104), (-0.413, 0.117))
    columns = 9
    points, uv = [], []
    distance = 0
    for row, (height, depth) in enumerate(profile):
        if row:
            distance += math.dist(profile[row - 1], profile[row])
        for col in range(columns):
            t = col / (columns - 1)
            wave = math.sin(2 * math.pi * (2 * t + 0.064 * row))
            hang = max(0, row - 3) / 6
            y = height + wave * (0.004 + 0.007 * hang)
            z = depth + wave * (0.003 + 0.019 * hang)
            points.append(((t - 0.5) * (0.56 - 0.022 * hang), y, z))
            uv.append((t * 2, distance / 0.25))
    faces = grid_faces(len(profile), columns)
    model.add(fabric, points, faces, uv=uv)
    for i in range(11):
        t = (i + 0.5) / 11
        x = (t - 0.5) * 0.538
        cv = t * (columns - 1)
        ix = int(cv)
        a = np.array(points[-columns + ix])
        b = np.array(points[-columns + ix + 1])
        _, y, z = a + (b - a) * (cv - ix)
        length = 0.017 + 0.005 * math.sin(i * 2.1)
        model.quad(fabric, ((x-0.004, y, z), (x+0.004, y, z), (x+0.005, y-length, z+0.004),
                            (x-0.003, y-length, z+0.005)), uv=((0.2, .25), (.22, .25), (.22, .28), (.2, .28)))
    return model


def mug():
    model = Model("ceramic_mug")
    glaze = model.material("Dressing glaze", roughness=0.38)
    model.lathe(glaze, ((0, 0), (0.031, 0), (0.040, 0.008), (0.044, 0.078), (0.043, 0.084),
                      (0.039, 0.084), (0.038, 0.077), (0.034, 0.018), (0, 0.015)), 14, "#B8C9C4")
    path = [(0.040 + 0.030 * math.sin(a), .047 + .026 * math.cos(a), 0) for a in np.linspace(0, math.pi, 9)]
    model.tube(glaze, path, 5, 0.006, "#B8C9C4", np.array((0.0, 0.0, 1.0)))
    return model


def magazines():
    model = Model("magazine_stack")
    matte = model.material("Dressing matte")
    model.box(matte, (0, .001, 0), (.234, .002, .164), "#496068")
    model.box(matte, (0, .007, 0), (.229, .010, .160), "#DFD1B0")
    model.box(matte, (0, .013, 0), (.234, .002, .164), "#637E80")
    model.box(matte, (.008, .015, -.002), (.218, .002, .149), "#A75440", yaw=8)
    model.box(matte, (.008, .021, -.002), (.213, .010, .145), "#E4D4B8", yaw=8)
    model.box(matte, (.008, .027, -.002), (.218, .002, .149), "#B36E4E", yaw=8)
    for x, z, w, l, color in ((-.034, -.041, .105, .012, "#E6D1A5"), (.040, .011, .079, .058, "#789290"),
                               (-.050, .008, .053, .007, "#D9B988"), (-.056, .026, .041, .005, "#865444")):
        center = rotated(((x, .0283, z),), 8, (.008, 0, -.002))[0]
        sheet = ((-w/2, 0, -l/2), (-w/2, 0, l/2), (w/2, 0, l/2), (w/2, 0, -l/2))
        model.quad(matte, rotated(sheet, 8, center), color)
    return model


def tv_remote():
    model = Model("tv_remote")
    matte = model.material("Dressing matte")
    model.bevel_box(matte, (0, .008, 0), (.047, .016, .154), "#293138", .003)
    buttons = [(0.012, -.054, .009, .009, "#A9463A"), (-.011, -.031, .010, .014, "#8E9698"),
               (.011, -.031, .010, .014, "#8E9698"), (0, -.008, .024, .019, "#626B72"),
               (0, -.008, .011, .010, "#A8AEAD")]
    buttons += [(x, z, .009, .007, "#626B72") for x in (-.012, 0, .012) for z in (.019, .034, .049)]
    for i, (x, z, w, l, color) in enumerate(buttons):
        y = .0204 if i == 4 else .0175
        model.box(matte, (x, y, z), (w, .003, l), color)
    return model


def key_dish():
    model = Model("key_dish")
    glaze = model.material("Dressing glaze", roughness=0.38)
    metal = model.material("Brushed key metal", roughness=0.39, metallic=0.7)
    model.lathe(glaze, ((0, 0), (.058, 0), (.070, .010), (.079, .024), (.076, .026),
                      (.071, .022), (.055, .010), (0, .010)), 14, "#33565F", oval=0.77)
    ring = [(0.012 + 0.016 * math.cos(a), .013, -.009 + .016 * math.sin(a))
            for a in np.linspace(0, 2 * math.pi, 10, endpoint=False)]
    model.tube(metal, ring, 4, .0015, "#C2AE78", UP, closed=True)
    for offset, angle, hue in (((.018, .016, .005), -34, "#9C9EA1"), ((-.008, .017, .007), 135, "#B49C65")):
        model.box(metal, offset, (.018, .005, .015), hue, yaw=angle)
        for x, z, w, depth in ((0, .018, .006, .026), (-.004, .018, .005, .005), (-.004, .026, .005, .003)):
            at = rotated(((x, 0, z),), angle, offset)[0]
            model.box(metal, at, (w, .003, depth), hue, yaw=angle)
    return model


ASSETS = [
    (open_book, "Livre ouvert", "Table d’appoint ou bureau. Poser à plat, carnet orienté vers le lecteur.", "Contact inférieur, +Z côté lecteur"),
    (photo_frame, "Cadre photo", "Console, bibliothèque ou table de chevet. Diriger le côté photo vers la pièce.", "Contact inférieur, +Z côté photo"),
    (draped_throw, "Plaid drapé", "Centrer sur le haut du dossier. Ajuster la profondeur à l’épaisseur du dossier.", "Crête du pli, +Z côté du pan long, -Y vers le bas"),
    (mug, "Tasse en céramique", "Table près du livre ou plan de travail, anse dégagée du bord.", "Contact inférieur, anse vers -X après import Unity"),
    (magazines, "Pile de revues", "Table basse ou étagère basse. Les deux revues forment un seul objet.", "Contact inférieur"),
    (tv_remote, "Télécommande", "Table basse ou accoudoir large. Orienter selon le mobilier.", "Contact inférieur"),
    (key_dish, "Vide-poche avec clés", "Console d’entrée ou meuble près d’une porte. Bol et clés forment un seul objet.", "Contact inférieur"),
]


def main():
    props = []
    for make, label, placing, pivot in ASSETS:
        model = make()
        props.append({"id": model.name, "name_fr": label, "file": f"{model.name}.glb",
                      "placement_fr": placing, "pivot_fr": pivot,
                      "textures": [m[2] for m in model.materials.values() if m[2]], **model.save(OUT)})
    manifest = {
        "project": "Out of Sight / games/out_of_sight",
        "format": "GLB 2.0, glTFast, metres, Y up, identity node transforms",
        "integration_fr": [
            "Placer en éléments visuels enfants du mobilier, à échelle 1. Les objets servent à habiller les pièces.",
            "Utiliser des accessoires visuels hors NavMesh et hors couche Occluder pour garder les passages et les abris du niveau.",
            "Garder les matériaux importés. Les couleurs unies sont en COLOR_0 et trois GLB embarquent leur albédo.",
            "Les trois PNG sont fournis séparément pour les retouches artistiques. Le plaid répète son motif dans les UV.",
            "Privilégier les matériaux partagés pour les surfaces unies et quelques accessoires par pièce. Contrôler les budgets de la scène.",
        ],
        "imagegen": {
            "book_spread.png": "Double page à plat d’un carnet de voyage alpin, papier ivoire, carte à gauche et illustration ferroviaire à droite.",
            "family_photo.png": "Portrait vertical d’une famille fictive en bord de mer, cadré à mi-buste et traité comme un tirage photographique.",
            "plaid_weave.png": "Trame de laine répétable à carreaux bleu ardoise et caramel sur fond avoine, albédo sans lumière directionnelle.",
        },
        "props": props,
    }
    (OUT / "inventory.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for prop in props:
        print(f"{prop['file']}: {prop['triangles']} tris, {prop['material_slots']} materials")


if __name__ == "__main__":
    main()
