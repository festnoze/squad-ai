"""LABRADOR (2026-11-25): stages the final Labrador handoff into the game.

Reads ArtHandoff/LabradorFinal/labrador_profile_rigged.glb (the Quaternius Husky rig, 2,996 triangles, 50 joints, the 24
clips, a "Head/LabradorEyeCenter" eye marker, two materials: "Main" on DogFur and "Tete profil et face" on
LabradorHeadAtlas) and writes:

- Assets/ThirdParty/Models/Quaternius/quaternius_labrador.glb: the same file with its two embedded images dropped (the
  images, textures and samplers arrays, each material's baseColorTexture, and the two image buffer views, the binary
  chunk compacted). Geometry, UVs, skin, nodes, clips and material names are kept byte for byte. glTFast imports an
  embedded image as an uncompressed RGBA32 texture with mips (about 22 MB each at 2048 px) that the catalog's prefab
  would drag into the player; the game shows the same pixels from the two PNGs below, imported compressed.
- Assets/Art/Characters/Resources/LabradorHeadAtlas.png: the head and neck atlas, byte for byte.
- Assets/Art/Characters/Resources/DogFur.png: checked byte for byte against the handoff's (copied when it differs).

Each embedded image is checked equal to its PNG before it is dropped, so nothing of the look is lost.
The old quaternius_husky.glb is left alone: tools/assets/labrador_full.py builds the Labrador from it.
Usage: python tools/assets/dog/stage_labrador.py
"""
import hashlib
import json
import os
import shutil
import struct
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glbinfo_lib import load  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
HANDOFF = os.path.join(ROOT, "ArtHandoff", "LabradorFinal")
SRC = os.path.join(HANDOFF, "labrador_profile_rigged.glb")
DST = os.path.join(ROOT, "Assets", "ThirdParty", "Models", "Quaternius", "quaternius_labrador.glb")
RESOURCES = os.path.join(ROOT, "Assets", "Art", "Characters", "Resources")
# Embedded image name -> the PNG the game ships it as (same name, Resources folder).
IMAGES = {"DogFur": "DogFur.png", "LabradorHeadAtlas": "LabradorHeadAtlas.png"}
EYE_MARKER = "LabradorEyeCenter"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def view_bytes(js: dict[str, Any], binc: bytes, index: int) -> bytes:
    bv = js["bufferViews"][index]
    start = bv.get("byteOffset", 0)
    return binc[start:start + bv["byteLength"]]


def check_handoff(js: dict[str, Any], binc: bytes) -> None:
    """
    The handoff's invariants, against its inventory.json (the art pass may still revise the mesh): the triangles, joints and
    clips it lists, the eye marker under Head, the two materials.
    """
    inventory = json.load(open(os.path.join(HANDOFF, "inventory.json"), encoding="utf-8"))
    mesh = js["meshes"][0]
    triangles = sum(js["accessors"][p["indices"]]["count"] // 3 for p in mesh["primitives"])
    joints = len(js["skins"][0]["joints"])
    clips = [a.get("name") for a in js.get("animations", [])]
    names = [m["name"] for m in js["materials"]]
    head = next(i for i, n in enumerate(js["nodes"]) if n.get("name") == "Head")
    marker = [js["nodes"][c]["name"] for c in js["nodes"][head].get("children", [])]
    print(f"handoff: {triangles} triangles, {joints} joints, {len(clips)} clips, materials {names}, Head children {marker}")
    assert triangles == inventory["triangles"], f"{triangles} triangles, inventory.json lists {inventory['triangles']}"
    assert joints == inventory["joints"], f"{joints} joints, inventory.json lists {inventory['joints']}"
    assert sorted(clips) == sorted(inventory["clips"]), "the clips differ from inventory.json's"
    assert "Idle" in clips and "Walk" in clips, "no Idle or Walk clip"
    assert triangles <= 3000 and joints <= 50, "over the pet budget (Tuning.BudgetInhabitantTriangles, BudgetPetBones)"
    assert names == ["Main", "Tete profil et face"], f"unexpected materials {names}"
    assert inventory.get("eye_marker") == "Head/" + EYE_MARKER and EYE_MARKER in marker, f"no {EYE_MARKER} under Head"


def strip_images(js: dict[str, Any], binc: bytes) -> tuple[dict[str, Any], bytes]:
    """Drops the embedded images and compacts the binary chunk. Returns the new json and binary chunk."""
    dropped: set[int] = set()
    for image in js.get("images", []):
        want = IMAGES.get(image.get("name"))
        assert want is not None, f"unexpected embedded image {image.get('name')}"
        data = view_bytes(js, binc, image["bufferView"])
        png = open(os.path.join(HANDOFF, want), "rb").read()
        assert sha(data) == sha(png), f"embedded {image['name']} differs from {want}"
        dropped.add(image["bufferView"])
        print(f"  embedded {image['name']}: {len(data)} bytes, equal to {want}: dropped")
    for key in ("images", "textures", "samplers"):
        js.pop(key, None)
    for material in js["materials"]:
        pbr = material.get("pbrMetallicRoughness", {})
        pbr.pop("baseColorTexture", None)
    # Nothing else may still point at a dropped view.
    for accessor in js["accessors"]:
        assert accessor.get("bufferView") not in dropped
        assert "sparse" not in accessor, "sparse accessors are not handled"
    remap: dict[int, int] = {}
    views: list[dict[str, Any]] = []
    out = bytearray()
    for index, bv in enumerate(js["bufferViews"]):
        if index in dropped:
            continue
        while len(out) % 4:
            out.append(0)
        data = view_bytes(js, binc, index)
        nbv = dict(bv)
        nbv["byteOffset"] = len(out)
        out.extend(data)
        remap[index] = len(views)
        views.append(nbv)
    while len(out) % 4:
        out.append(0)
    js["bufferViews"] = views
    for accessor in js["accessors"]:
        if "bufferView" in accessor:
            accessor["bufferView"] = remap[accessor["bufferView"]]
    js["buffers"] = [{"byteLength": len(out)}]
    extras = js["asset"].setdefault("extras", {})
    extras["outOfSight"] = ("LABRADOR 2026-11-25: ArtHandoff/LabradorFinal/labrador_profile_rigged.glb with its two embedded "
                            "images dropped (shipped as Assets/Art/Characters/Resources/DogFur.png and LabradorHeadAtlas.png)")
    return js, bytes(out)


def write_glb(path: str, js: dict[str, Any], binc: bytes) -> None:
    text = json.dumps(js, separators=(",", ":")).encode("utf-8")
    while len(text) % 4:
        text += b" "
    total = 12 + 8 + len(text) + 8 + len(binc)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(text), 0x4E4F534A))
        f.write(text)
        f.write(struct.pack("<II", len(binc), 0x004E4942))
        f.write(binc)


def main() -> None:
    js, binc = load(SRC)
    check_handoff(js, binc)
    before = {i: sha(view_bytes(js, binc, a["bufferView"])) for i, a in enumerate(js["accessors"])}
    js, out = strip_images(js, binc)
    write_glb(DST, js, out)
    # Read back: every accessor's bytes unchanged, the invariants intact.
    js2, bin2 = load(DST)
    check_handoff(js2, bin2)
    after = {i: sha(view_bytes(js2, bin2, a["bufferView"])) for i, a in enumerate(js2["accessors"])}
    assert before == after, "an accessor's data changed"
    print(f"wrote {DST}: {os.path.getsize(DST)} bytes (handoff {os.path.getsize(SRC)})")
    for png in IMAGES.values():
        src = os.path.join(HANDOFF, png)
        dst = os.path.join(RESOURCES, png)
        if os.path.exists(dst) and sha(open(dst, "rb").read()) == sha(open(src, "rb").read()):
            print(f"  {dst}: already the handoff's")
        else:
            shutil.copyfile(src, dst)
            print(f"  {dst}: copied")


if __name__ == "__main__":
    main()
