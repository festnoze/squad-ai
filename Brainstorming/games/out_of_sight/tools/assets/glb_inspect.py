"""Inspect GLB files without a 3D tool (stdlib only).

Reads the JSON chunk and, when present, the BIN chunk of each GLB and prints
facts useful for budget and import checks: triangles, meshes, materials,
textures (with pixel size), vertex colors, skins (bone counts), animations
(names and durations), node root transforms (scale and axis hints), exact
world bounds in meters, and the glTF extensions used.

Downloaded GLBs are untrusted data. Run this script isolated:

    python -I glb_inspect.py file.glb [more.glb ...] [--json out.json]

Nothing is executed from the files; only bounded struct/json parsing is done.
"""

import json
import math
import struct
import sys
from pathlib import Path

MAX_FILE_BYTES = 80 * 1024 * 1024
GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

COMPONENT = {
    5120: ("b", 1),
    5121: ("B", 1),
    5122: ("h", 2),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}
NORMALIZE_DIV = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


class GlbError(Exception):
    pass


def read_glb(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise GlbError("file too large")
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise GlbError("not a GLB (bad magic)")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise GlbError(f"unsupported GLB version {version}")
    json_len, json_type = struct.unpack_from("<II", data, 12)
    if json_type != CHUNK_JSON or 20 + json_len > len(data):
        raise GlbError("first chunk is not a valid JSON chunk")
    gltf = json.loads(data[20:20 + json_len].decode("utf-8"))
    binary = None
    offset = 20 + json_len
    if offset + 8 <= len(data):
        bin_len, bin_type = struct.unpack_from("<II", data, offset)
        if bin_type == CHUNK_BIN and offset + 8 + bin_len <= len(data):
            binary = data[offset + 8: offset + 8 + bin_len]
    return gltf, binary, len(data), json_len


# ---------------------------------------------------------------- matrices

def mat_identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mat_mul(a, b):
    """Column-major 4x4 multiply (glTF convention): returns a * b."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
    return out


def mat_from_trs(t, r, s):
    x, y, z, w = r
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    rot = [
        1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy), 0,
        2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx), 0,
        2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy), 0,
        0, 0, 0, 1,
    ]
    for col in range(3):
        for row in range(3):
            rot[col * 4 + row] *= s[col]
    rot[12], rot[13], rot[14] = t
    return rot


def node_local(node):
    if "matrix" in node:
        return [float(v) for v in node["matrix"]]
    return mat_from_trs(
        node.get("translation", [0.0, 0.0, 0.0]),
        node.get("rotation", [0.0, 0.0, 0.0, 1.0]),
        node.get("scale", [1.0, 1.0, 1.0]),
    )


def transform_point(m, p):
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


# ---------------------------------------------------------------- accessors

def read_accessor(gltf, binary, index):
    acc = gltf["accessors"][index]
    if "bufferView" not in acc or binary is None:
        return None
    view = gltf["bufferViews"][acc["bufferView"]]
    if view.get("buffer", 0) != 0 or "uri" in gltf["buffers"][view.get("buffer", 0)]:
        return None
    fmt, size = COMPONENT[acc["componentType"]]
    ncomp = TYPE_SIZE[acc["type"]]
    count = acc["count"]
    stride = view.get("byteStride") or size * ncomp
    base = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    end = base + stride * (count - 1) + size * ncomp
    if count == 0 or end > len(binary) or count > 5_000_000:
        return None
    unpack = struct.Struct("<" + fmt * ncomp).unpack_from
    div = NORMALIZE_DIV.get(acc["componentType"]) if acc.get("normalized") else None
    out = []
    for i in range(count):
        vals = unpack(binary, base + i * stride)
        if div:
            vals = tuple(max(v / div, -1.0) for v in vals)
        out.append(vals)
    return out


def image_size(blob):
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return struct.unpack(">II", blob[16:24])
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return (w, h)
            seg = struct.unpack(">H", blob[i + 2:i + 4])[0]
            i += 2 + seg
        return None
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        kind = blob[12:16]
        if kind == b"VP8X" and len(blob) >= 30:
            w = 1 + int.from_bytes(blob[24:27], "little")
            h = 1 + int.from_bytes(blob[27:30], "little")
            return (w, h)
        if kind == b"VP8L" and len(blob) >= 25:
            b = blob[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return (w, h)
        if kind == b"VP8 " and len(blob) >= 30:
            w, h = struct.unpack("<HH", blob[26:30])
            return (w & 0x3FFF, h & 0x3FFF)
    return None


# ---------------------------------------------------------------- analysis

def prim_triangles(gltf, prim):
    mode = prim.get("mode", 4)
    if "indices" in prim:
        count = gltf["accessors"][prim["indices"]]["count"]
    else:
        count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(count - 2, 0)
    return 0


def world_matrices(gltf):
    nodes = gltf.get("nodes", [])
    world = {}
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    scenes = gltf.get("scenes", [])
    scene_index = gltf.get("scene", 0)
    roots = scenes[scene_index]["nodes"] if scenes else [i for i in range(len(nodes)) if i not in parent]

    stack = [(r, mat_identity()) for r in roots]
    seen = set()
    while stack:
        idx, pm = stack.pop()
        if idx in seen or idx >= len(nodes):
            continue
        seen.add(idx)
        m = mat_mul(pm, node_local(nodes[idx]))
        world[idx] = m
        for c in nodes[idx].get("children", []):
            stack.append((c, m))
    return world, roots


def scale_of(m):
    return tuple(math.sqrt(m[c * 4] ** 2 + m[c * 4 + 1] ** 2 + m[c * 4 + 2] ** 2) for c in range(3))


def analyse(path):
    gltf, binary, file_size, json_len = read_glb(path)
    nodes = gltf.get("nodes", [])
    meshes = gltf.get("meshes", [])
    accessors = gltf.get("accessors", [])
    world, roots = world_matrices(gltf)

    mesh_tris = []
    vertex_colors = False
    for mesh in meshes:
        t = 0
        for prim in mesh.get("primitives", []):
            t += prim_triangles(gltf, prim)
            if "COLOR_0" in prim.get("attributes", {}):
                vertex_colors = True
        mesh_tris.append(t)

    rendered_tris = 0
    mesh_instances = 0
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    bounds_method = "exact"

    def grow(p):
        for k in range(3):
            lo[k] = min(lo[k], p[k])
            hi[k] = max(hi[k], p[k])

    skins = gltf.get("skins", [])
    joint_mats = {}
    for si, skin in enumerate(skins):
        ibms = read_accessor(gltf, binary, skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
        mats = []
        for ji, j in enumerate(skin["joints"]):
            ibm = list(ibms[ji]) if ibms else mat_identity()
            mats.append(mat_mul(world.get(j, mat_identity()), ibm))
        joint_mats[si] = mats

    for ni, node in enumerate(nodes):
        if "mesh" not in node or ni not in world:
            continue
        mesh_instances += 1
        rendered_tris += mesh_tris[node["mesh"]]
        skin_index = node.get("skin")
        for prim in meshes[node["mesh"]].get("primitives", []):
            pos_index = prim["attributes"]["POSITION"]
            positions = read_accessor(gltf, binary, pos_index)
            if positions is None:
                bounds_method = "accessor-corners"
                acc = accessors[pos_index]
                mn, mx = acc.get("min"), acc.get("max")
                if not mn or not mx:
                    continue
                positions = [(x, y, z) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
                m = world[ni]
                if skin_index is not None and joint_mats.get(skin_index):
                    m = joint_mats[skin_index][0]
                for p in positions:
                    grow(transform_point(m, p))
                continue
            if skin_index is None:
                m = world[ni]
                for p in positions:
                    grow(transform_point(m, p))
                continue
            joints = read_accessor(gltf, binary, prim["attributes"].get("JOINTS_0")) if "JOINTS_0" in prim["attributes"] else None
            weights = read_accessor(gltf, binary, prim["attributes"].get("WEIGHTS_0")) if "WEIGHTS_0" in prim["attributes"] else None
            mats = joint_mats[skin_index]
            if not joints or not weights:
                for p in positions:
                    grow(transform_point(mats[0], p))
                continue
            for p, js, ws in zip(positions, joints, weights):
                acc_p = [0.0, 0.0, 0.0]
                wsum = 0.0
                for j, w in zip(js, ws):
                    if w <= 0 or int(j) >= len(mats):
                        continue
                    q = transform_point(mats[int(j)], p)
                    acc_p[0] += w * q[0]
                    acc_p[1] += w * q[1]
                    acc_p[2] += w * q[2]
                    wsum += w
                if wsum > 0:
                    grow([c / wsum for c in acc_p])

    materials = []
    for mat in gltf.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        materials.append({
            "name": mat.get("name", ""),
            "baseColor": [round(c, 3) for c in pbr.get("baseColorFactor", [1, 1, 1, 1])],
            "baseColorTexture": "baseColorTexture" in pbr,
            "normalTexture": "normalTexture" in mat,
            "metallic": pbr.get("metallicFactor", 1.0),
            "roughness": pbr.get("roughnessFactor", 1.0),
            "alphaMode": mat.get("alphaMode", "OPAQUE"),
            "extensions": sorted(mat.get("extensions", {}).keys()),
        })

    images = []
    for img in gltf.get("images", []):
        info = {"name": img.get("name", ""), "mimeType": img.get("mimeType", ""), "uri": "uri" in img}
        if "bufferView" in img and binary is not None:
            view = gltf["bufferViews"][img["bufferView"]]
            start = view.get("byteOffset", 0)
            blob = binary[start:start + view["byteLength"]]
            info["bytes"] = view["byteLength"]
            size = image_size(blob)
            info["size"] = list(size) if size else None
        images.append(info)

    animations = []
    for anim in gltf.get("animations", []):
        duration = 0.0
        for sampler in anim.get("samplers", []):
            acc = accessors[sampler["input"]]
            if acc.get("max"):
                duration = max(duration, float(acc["max"][0]))
        animations.append({"name": anim.get("name", ""), "duration": round(duration, 3), "channels": len(anim.get("channels", []))})

    root_info = []
    for r in roots:
        n = nodes[r]
        root_info.append({
            "name": n.get("name", ""),
            "rotation": [round(v, 4) for v in n.get("rotation", [0, 0, 0, 1])],
            "scale": [round(v, 4) for v in n.get("scale", [1, 1, 1])],
            "hasMatrix": "matrix" in n,
        })
    max_node_scale = max((max(scale_of(m)) for m in world.values()), default=1.0)

    size = [hi[k] - lo[k] for k in range(3)] if lo[0] != math.inf else None
    return {
        "file": str(path),
        "fileBytes": file_size,
        "generator": gltf.get("asset", {}).get("generator", ""),
        "extensionsUsed": gltf.get("extensionsUsed", []),
        "extensionsRequired": gltf.get("extensionsRequired", []),
        "meshes": len(meshes),
        "meshInstances": mesh_instances,
        "primitives": sum(len(m.get("primitives", [])) for m in meshes),
        "trianglesPerMeshSum": sum(mesh_tris),
        "trianglesRendered": rendered_tris,
        "vertexColors": vertex_colors,
        "materials": materials,
        "textures": len(gltf.get("textures", [])),
        "images": images,
        "skins": [{"name": s.get("name", ""), "joints": len(s["joints"])} for s in skins],
        "bones": max((len(s["joints"]) for s in skins), default=0),
        "animations": animations,
        "nodes": len(nodes),
        "roots": root_info,
        "maxWorldScale": round(max_node_scale, 4),
        "boundsMethod": bounds_method,
        "boundsMin": [round(v, 4) for v in lo] if size else None,
        "boundsMax": [round(v, 4) for v in hi] if size else None,
        "sizeXYZ": [round(v, 4) for v in size] if size else None,
    }


def summary_line(r):
    size = "x".join(f"{v:.2f}" for v in r["sizeXYZ"]) if r["sizeXYZ"] else "?"
    tex = [f"{i.get('size')}" for i in r["images"]]
    anims = ",".join(a["name"] for a in r["animations"])
    return (f"{Path(r['file']).name}: tris={r['trianglesRendered']} meshes={r['meshes']} mats={len(r['materials'])} "
            f"tex={len(r['images'])}{tex if tex else ''} vcol={r['vertexColors']} bones={r['bones']} "
            f"anims={len(r['animations'])} size(m)={size} ext={r['extensionsUsed']} [{anims[:300]}]")


def main(argv):
    out_json = None
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == "--json":
            out_json = argv[i + 1]
            i += 2
            continue
        files.append(argv[i])
        i += 1
    results = []
    for f in files:
        try:
            r = analyse(f)
            results.append(r)
            print(summary_line(r))
        except (GlbError, KeyError, ValueError, IndexError, struct.error) as exc:
            print(f"{Path(f).name}: ERROR {exc!r}")
            results.append({"file": str(f), "error": repr(exc)})
    if out_json:
        Path(out_json).write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
