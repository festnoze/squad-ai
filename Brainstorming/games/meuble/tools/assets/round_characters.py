"""Make the human GLB variants used by ModelCatalogBuilder, preserving topology and the rig.

Run with Python and NumPy. Coincident positions move together across material and normal seams.
The eye, brow, shoe and accessory geometry stays in place, including shared boundary vertices.
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


def rounded(source):
    model, data, *_ = read_glb(source)
    blob = bytearray(data)
    groups = {}
    positions = []
    neighbours = []
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
            welded.append(groups[key])
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

    # Angle-weighted normals remove planar shading while keeping pronounced creases and material boundaries.
    for name, attributes, original, normals, triangles, welded in primitives:
        if name in FIXED:
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
        if source.stem != "quaternius_shiba":
            destination = DESTINATION / source.name
            pending = destination.with_suffix(".glb.tmp")
            pending.write_bytes(rounded(source))
            pending.replace(destination)
            print(destination.relative_to(ASSETS))
