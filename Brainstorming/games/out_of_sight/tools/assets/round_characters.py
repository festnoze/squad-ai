"""Make the human GLB variants used by ModelCatalogBuilder, preserving topology and the rig.

Run with Python and NumPy. Coincident positions move together across material and normal seams.
Eye, brow and accessory geometry stays in place. Clothing volume and shoes are refined in bind pose.
"""

import json
from pathlib import Path
import struct

import numpy as np

from glb_inspect import read_accessor, read_glb


ASSETS = Path(__file__).resolve().parents[2] / "Assets"
SOURCE = ASSETS / "ThirdParty/Models/Quaternius"
DESTINATION = ASSETS / "Art/Characters/Models"
FIXED = {"Eyes", "Eyebrows", "Shoes", "Socks", "Black", "Details", "TieTexture"}
TOPS = {"Shirt", "Shirt2", "Jacket", "LightJacket", "Dress"}


def unit(vector):
    return vector / max(np.linalg.norm(vector), 1e-20)


def write_vectors(model, blob, accessor_id, values, bounds=False):
    accessor = model["accessors"][accessor_id]
    view = model["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", 12)
    for index, value in enumerate(values):
        struct.pack_into("<3f", blob, offset + index * stride, *value)
    if bounds:
        accessor["min"] = values.min(axis=0).tolist()
        accessor["max"] = values.max(axis=0).tolist()


def refine_clothes(positions, materials, shoe_neighbours, fixed):
    """Adjust the silhouette without moving skin, garment junctions or sole contacts."""
    torso = np.array([i for i, names in enumerate(materials) if names <= TOPS and i not in fixed])
    if len(torso):
        x, depth, height = positions[torso].T
        chest = np.exp(-((100 * height - 3.37) / 0.47) ** 2 - (100 * x / 0.43) ** 4)
        depth_centre = np.median(depth[np.abs(x) < 0.0043])
        if np.isfinite(depth_centre):
            positions[torso, 1] += 0.075 * chest * (depth - depth_centre)

    pants = np.array([i for i, names in enumerate(materials) if names == {"Pants"} and i not in fixed])
    if len(pants) and np.ptp(positions[pants, 2]) > 0.014:
        for side in (-1, 1):
            leg = pants[side * positions[pants, 0] > 0]
            # Add fabric around the calf in its bind-pose cross-section. The upper leg, knee and
            # hem keep their original cut so the folds can follow the rig and the shoes still fit.
            ankle = positions[leg, 2].min()
            calf = leg[positions[leg, 2] < ankle + 0.010]
            xy = positions[calf, :2]
            centre = 0.5 * (xy.min(axis=0) + xy.max(axis=0))
            height = np.clip((positions[calf, 2] - ankle) / 0.010, 0, 1)
            ease = np.sin(np.pi * height) ** 2
            positions[calf, :2] += 0.17 * ease[:, None] * (xy - centre)

    shoes = [i for i in shoe_neighbours if materials[i] == {"Shoes"}]
    if shoes:
        shape = positions.copy()
        for side in (-1, 1):
            foot = [i for i in shoes if side * shape[i, 0] > 0]
            sole = shape[foot, 2].min()
            for i in foot:
                # Preserve the sole and soften the boxy toe. Small changes around the instep
                # leave the shoe opening and limb proportions close to their source.
                fade = np.clip((shape[i, 2] - sole) / 0.0008, 0, 1)
                delta = shape[sorted(shoe_neighbours[i])].mean(axis=0) - shape[i]
                positions[i] += unit(delta) * min(0.32 * np.linalg.norm(delta), 0.00016) * fade


def rounded(source):
    model, data, *_ = read_glb(source)
    blob = bytearray(data)
    groups = {}
    positions = []
    neighbours = []
    materials = []
    shoe_neighbours = {}
    fixed = set()
    hair = set()
    primitives = []
    for primitive in model["meshes"][0]["primitives"]:
        name = model["materials"][primitive["material"]]["name"]
        attributes = primitive["attributes"]
        original = np.array(read_accessor(model, data, attributes["POSITION"]))
        normals = np.array(read_accessor(model, data, attributes["NORMAL"]))
        triangles = np.array(read_accessor(model, data, primitive["indices"])).reshape(-1, 3)
        welded = []
        for point in original:
            key = tuple(np.rint(point * 1e7).astype(int))
            if key not in groups:
                groups[key] = len(positions)
                positions.append(point)
                neighbours.append(set())
                materials.append(set())
            index = groups[key]
            materials[index].add(name)
            welded.append(index)
        welded = np.array(welded)
        if name.startswith("Hair"):
            hair.update(welded)
        if name in FIXED:
            fixed.update(welded)
        else:
            for a, b, c in welded[triangles]:
                neighbours[a].update((b, c))
                neighbours[b].update((a, c))
                neighbours[c].update((a, b))
        if name == "Shoes":
            for a, b, c in welded[triangles]:
                shoe_neighbours.setdefault(a, set()).update((b, c))
                shoe_neighbours.setdefault(b, set()).update((a, c))
                shoe_neighbours.setdefault(c, set()).update((a, b))
        primitives.append((name, attributes, original, normals, triangles, welded))

    # A positive and negative Laplacian pass soften the silhouette with less shrinkage.
    original_positions = np.array(positions)
    positions = original_positions.copy()
    for factor in (0.52, -0.42, 0.45, -0.34, 0.32, -0.28):
        updated = positions.copy()
        for index, adjacent in enumerate(neighbours):
            if adjacent and index not in fixed:
                updated[index] += factor * (positions[sorted(adjacent)].mean(axis=0) - positions[index])
        positions = updated

    # Hair locks are often separate shells. Limit movement so rounding cannot pull their edges apart.
    for index in hair:
        delta = positions[index] - original_positions[index]
        limit = 0.00016
        if np.linalg.norm(delta) > limit:
            positions[index] = original_positions[index] + unit(delta) * limit

    refine_clothes(positions, materials, shoe_neighbours, fixed)

    # Angle-weighted normals remove planar shading while keeping pronounced creases and material boundaries.
    for name, attributes, original, normals, triangles, welded in primitives:
        if name in FIXED and name != "Shoes":
            continue
        vertices = original + positions[welded] - original_positions[welded]
        incident = {}
        for face in triangles:
            points = vertices[face]
            normal = unit(np.cross(points[1] - points[0], points[2] - points[0]))
            for j, vertex in enumerate(face):
                left = unit(points[(j + 1) % 3] - points[j])
                right = unit(points[(j + 2) % 3] - points[j])
                angle = np.arccos(np.clip(left @ right, -1, 1))
                incident.setdefault(welded[vertex], []).append((normal, angle))
        for index, normal in enumerate(normals):
            adjacent = [n * angle for n, angle in incident.get(welded[index], ()) if n @ normal > 0.25]
            if adjacent and np.linalg.norm(np.sum(adjacent, axis=0)) > 1e-9:
                normals[index] = unit(np.sum(adjacent, axis=0))
        write_vectors(model, blob, attributes["POSITION"], vertices, bounds=True)
        write_vectors(model, blob, attributes["NORMAL"], normals)

    header = json.dumps(model, separators=(",", ":")).encode("utf-8")
    header += b" " * (-len(header) % 4)
    length = 12 + 8 + len(header) + 8 + len(blob)
    return struct.pack("<4sIIII", b"glTF", 2, length, len(header), 0x4E4F534A) + header + struct.pack(
        "<II", len(blob), 0x004E4942
    ) + blob


if __name__ == "__main__":
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for source in sorted(SOURCE.glob("quaternius_*.glb")):
        if source.stem.startswith(("quaternius_man", "quaternius_woman")):
            destination = DESTINATION / source.name
            pending = destination.with_suffix(".glb.tmp")
            pending.write_bytes(rounded(source))
            pending.replace(destination)
            print(destination.relative_to(ASSETS))
