"""Builds Assets/ThirdParty/Models/Quaternius/quaternius_husky.glb from the staged Quaternius Husky (CC0 1.0).

Changes (geometry, rig, weights and clips untouched):
- materials renamed to the Shiba's names the pipeline reads (Main, Main_Light, Black, Eyes_White, Eyes_Black);
- the mesh and its node renamed "Husky";
- TEXCOORD_0 added: a fixed 5 region box atlas in the bind pose (vertices split where a vertex is shared by faces of
  two regions), so a painted fur texture maps without swimming; layout written to a UV template PNG.
Later versions (see docs/next/progress/DOGBIG.md and DOGFACE.md): v3 a "Jaw" joint, v4 a rounder body and head,
v5 the mouth cut along the lips with a strip that opens on the MOUTH atlas region.
"""
import json, struct, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glbinfo_lib import load, COMP, NUM

SRC = r'C:\Dev\squad-ai\Brainstorming\games\meuble\ThirdParty_staging\poly.pizza\alternates\pets\pet_dog__quaternius_husky__wcWiuEqwzq.glb'
DST = r'C:\Dev\squad-ai\Brainstorming\games\meuble\Assets\ThirdParty\Models\Quaternius\quaternius_husky.glb'
TEMPLATE = r'C:\Dev\squad-ai\Brainstorming\games\meuble\Assets\Art\Characters\dog_fur_uv_template.png'

RENAME = {'Material': 'Main', 'Material.001': 'Main_Light', 'Material.006': 'Black', 'Material.003': 'Eyes_White', 'Material.002': 'Eyes_Black'}

js, binc = load(SRC)
binc = bytearray(binc)


def raw_elements(ai):
    a = js['accessors'][ai]
    bv = js['bufferViews'][a['bufferView']]
    fmt, size = COMP[a['componentType']]
    n = NUM[a['type']]
    esize = size * n
    stride = bv.get('byteStride', esize)
    base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    return [bytes(binc[base + i * stride: base + i * stride + esize]) for i in range(a['count'])], a


def floats(ai):
    els, a = raw_elements(ai)
    fmt, size = COMP[a['componentType']]
    n = NUM[a['type']]
    return [struct.unpack('<' + fmt * n, e) for e in els]


for m in js['materials']:
    m['name'] = RENAME.get(m['name'], m['name'])
for n in js['nodes']:
    if 'mesh' in n:
        n['name'] = 'Husky'
for me in js['meshes']:
    me['name'] = 'Husky'
js['asset']['copyright'] = 'Husky by Quaternius (Animated Animal Pack, poly.pizza/m/wcWiuEqwzq), CC0 1.0. Out of Sight: materials renamed, UV0 atlas added.'

mesh = js['meshes'][0]
# Extents in the model frame: right = x, up = z, forward = -y (mesh space, the node turns -90 deg about X).
allpos = []
for pr in mesh['primitives']:
    allpos += floats(pr['attributes']['POSITION'])
R = max(abs(p[0]) for p in allpos)
U0 = min(p[2] for p in allpos); U1 = max(p[2] for p in allpos)
F0 = min(-p[1] for p in allpos); F1 = max(-p[1] for p in allpos)
K = 0.46 / (F1 - F0)  # UV per mesh unit, the same in every body region
W = 2 * R
print('extents right %.5f up %.5f..%.5f fwd %.5f..%.5f K %.2f' % (R, U0, U1, F0, F1, K))

# Region placement in image space (x right, y down, 0..1): glTF UV (0,0) is the image's top left.
# v2 (black Labrador, 2026-11-21): the body regions at a smaller scale (the fur tiles), and a FACE region holding the
# product owner's front face picture, where every forward facing triangle of the head is projected from the front.
REGIONS = {
    'side': (0.01, 0.01), 'front': (0.01, 0.40), 'back': (0.14, 0.40), 'top': (0.27, 0.40), 'bottom': (0.40, 0.40),
    'face': (0.53, 0.01),
}
FACE_SIZE = 0.46  # the face picture (1024 px) scaled into a FACE_SIZE square of the atlas
# Face alignment (mesh units, measured on the GLB): the eyes (Eyes_White centroids) at x +-0.00216, up 0.02678; the
# nose (the forward-most Black cluster) centred at up 0.0255; the jaw's underside at up 0.0232. On the picture: the eyes
# at x 355 and 685, y 390; the nose centred at y 640; the chin at y 870 (pixels of the 1024 picture).
FACE_SX = 330.0 / (2 * 0.00216)
FACE_CX = 520.0
FACE_V = [(0.0400, 390.0 - (0.0400 - 0.02678) * FACE_SX), (0.02678, 390.0), (0.0255, 640.0), (0.0232, 870.0),
          (0.0000, 870.0 + 0.0232 * FACE_SX)]
# A head triangle: its centroid ahead of the neck and above the jaw line, not facing backwards.
HEAD_FWD = 0.0165
HEAD_UP = 0.0215


def face_py(u):
    for (ua, ya), (ub, yb) in zip(FACE_V, FACE_V[1:]):
        if ub <= u <= ua:
            return ya + (yb - ya) * (ua - u) / (ua - ub)
    return FACE_V[0][1] if u > FACE_V[0][0] else FACE_V[-1][1]


# v3 (product owner, 2026-11-21: "not stretched along the muzzle"): the front projection collapsed the whole muzzle top
# into the few picture rows between the eyes and the nose. Now the height on the picture follows the model's height
# through the features (eyes 390, top of the nose 560, its middle 640, its bottom 700, the chin 870), and on the muzzle
# top (above the nose's top, ahead of the eyes) it slides toward the nose's top (560) with the distance travelled from the
# eyes to the nose tip, so the muzzle top takes the picture's nose bridge at its length. Across, the front projection.
FACE_V = [(0.0400, 390.0 - (0.0400 - 0.02678) * FACE_SX), (0.02678, 390.0), (0.02610, 560.0), (0.02550, 640.0),
          (0.02486, 700.0), (0.02320, 870.0), (0.0000, 870.0 + 0.0232 * FACE_SX)]
EYE_FWD, NOSE_TOP_UP, TIP_FWD = 0.01891, 0.02610, 0.02353


def face_py_mixed(f, u):
    y = face_py(u)
    if u > NOSE_TOP_UP and f > EYE_FWD:
        a = min(max((f - EYE_FWD) / (TIP_FWD - EYE_FWD), 0.0), 1.0)
        y = y + (560.0 - y) * a
    return y

def uv_of(group, p):
    r, u, f = p[0], p[2], -p[1]
    ox, oy = REGIONS[group]
    if group == 'face':
        px = min(max(FACE_CX + r * FACE_SX, 0.0), 1023.0)
        py = min(max(face_py_mixed(f, u), 0.0), 1023.0)
        return (ox + FACE_SIZE * px / 1024.0, oy + FACE_SIZE * py / 1024.0)
    if group == 'side':
        return (ox + (f - F0) * K, oy + (U1 - u) * K)
    if group in ('top', 'bottom'):
        return (ox + (r + R) * K, oy + (F1 - f) * K)
    return (ox + (r + R) * K, oy + (U1 - u) * K)


def group_of(n, centroid):
    r, u, f = n[0], n[2], -n[1]
    length = (r * r + u * u + f * f) ** 0.5 or 1.0
    cu, cf = centroid[2], -centroid[1]
    if cf > HEAD_FWD and cu > HEAD_UP and f / length > -0.3:
        return 'face'
    ar, au, af = abs(r), abs(u), abs(f)
    if ar >= au and ar >= af:
        return 'side'
    if au >= af:
        return 'top' if u > 0 else 'bottom'
    return 'front' if f > 0 else 'back'

# v3 (product owner, 2026-11-21: the bite opens the mouth): the rig has no jaw, so a "Jaw" joint is added under Head, its
# hinge behind the mouth (forward 0.0180, up 0.0243 mesh units, on the middle line), and every lower jaw vertex (head
# region, below the mouth line, ahead of the hinge) is weighted to it alone. InhabitantRig/PetPose open it while biting.
JAW_HINGE = (0.0, -0.0180, 0.0243)  # mesh space (x, y = -forward, z = up)
JAW_MOUTH_UP = 0.0243
JAW_FROM_FWD = 0.0182
# v5 (DOGFACE, 2026-11-22: "the open mouth does not show"): the hinge moves back behind the mouth's corner (a longer
# lower jaw swings a wider gap) and the jaw is cut and weighted on the FINAL shape (step 3b below), not here.
JAW_HINGE = (0.0, -0.0171, 0.0242)
V5_MOUTH = True
_skin = js['skins'][0]
_names = [n.get('name') for n in js['nodes']]
_head_node = _names.index('Head')
_ibm = [list(m) for m in floats(_skin['inverseBindMatrices'])]
_hm = _ibm[_skin['joints'].index(_head_node)]  # column-major 4x4
_hl = [sum(_hm[c * 4 + r] * v for c, v in enumerate(list(JAW_HINGE) + [1.0])) for r in range(3)]
js['nodes'].append({'name': 'Jaw', 'translation': _hl})
JAW_NODE = len(js['nodes']) - 1
js['nodes'][_head_node].setdefault('children', []).append(JAW_NODE)
_jm = list(_hm)
for r in range(3):
    _jm[12 + r] -= _hl[r]
_skin['joints'].append(JAW_NODE)
JAW_SLOT = len(_skin['joints']) - 1
_ibm.append(_jm)
print('jaw joint', JAW_SLOT, 'local translation', [round(v, 6) for v in _hl])


def is_jaw(p):
    if V5_MOUTH:
        return False  # v5: the jaw is weighted on the final shape (step 3b)
    u, f = p[2], -p[1]
    return u < JAW_MOUTH_UP and u > HEAD_UP and f > JAW_FROM_FWD

new_bin = bytearray(binc)


def pad4(b):
    while len(b) % 4:
        b.append(0)


def add_view(data, target):
    pad4(new_bin)
    off = len(new_bin)
    new_bin.extend(data)
    view = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
    if target is not None:
        view['target'] = target
    js['bufferViews'].append(view)
    return len(js['bufferViews']) - 1


def add_accessor(view, ctype, count, typ, normalized=False, mn=None, mx=None):
    a = {'bufferView': view, 'componentType': ctype, 'count': count, 'type': typ}
    if normalized:
        a['normalized'] = True
    if mn is not None:
        a['min'] = mn
        a['max'] = mx
    js['accessors'].append(a)
    return len(js['accessors']) - 1


tris_by_group = {g: [] for g in REGIONS}
jaw_count = [0]
prims = []
areas = []
total_v = 0
for pr in mesh['primitives']:
    assert 'targets' not in pr
    attrs = pr['attributes']
    pos = floats(attrs['POSITION'])
    nor = floats(attrs['NORMAL'])
    idx = [i[0] for i in floats(pr['indices'])]
    raw = {k: raw_elements(v) for k, v in attrs.items()}
    remap = {}
    out_idx = []
    out_raw = {k: [] for k in attrs}
    out_uv = []
    out_pos = []
    for t in range(0, len(idx), 3):
        a, b, c = idx[t], idx[t + 1], idx[t + 2]
        pa, pb, pc = pos[a], pos[b], pos[c]
        e1 = [pb[i] - pa[i] for i in range(3)]
        e2 = [pc[i] - pa[i] for i in range(3)]
        cr = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
        vn = [nor[a][i] + nor[b][i] + nor[c][i] for i in range(3)]
        if sum(cr[i] * vn[i] for i in range(3)) < 0:
            cr = [-x for x in cr]
        if math.sqrt(sum(x * x for x in cr)) < 1e-14:
            cr = vn
        g = group_of(cr, [(pa[i] + pb[i] + pc[i]) / 3.0 for i in range(3)])
        tri_uv = []
        for v in (a, b, c):
            key = (v, g)
            if key not in remap:
                remap[key] = len(out_pos)
                out_pos.append(pos[v])
                out_uv.append(uv_of(g, pos[v]))
                for k in attrs:
                    out_raw[k].append(raw[k][0][v])
                if is_jaw(pos[v]):
                    jt = js['accessors'][attrs['JOINTS_0']]['componentType']
                    out_raw['JOINTS_0'][-1] = struct.pack('<4B' if jt == 5121 else '<4H', JAW_SLOT, 0, 0, 0)
                    wa = js['accessors'][attrs['WEIGHTS_0']]
                    if wa['componentType'] == 5126:
                        out_raw['WEIGHTS_0'][-1] = struct.pack('<4f', 1.0, 0.0, 0.0, 0.0)
                    elif wa['componentType'] == 5121:
                        out_raw['WEIGHTS_0'][-1] = struct.pack('<4B', 255, 0, 0, 0)
                    else:
                        out_raw['WEIGHTS_0'][-1] = struct.pack('<4H', 65535, 0, 0, 0)
                    jaw_count[0] += 1
            out_idx.append(remap[key])
            tri_uv.append(out_uv[remap[key]])
        tris_by_group[g].append(tri_uv)
        areas.append((tri_uv, 0.5 * math.sqrt(sum(x * x for x in cr)), g))
    prims.append({'pr': pr, 'attrs': attrs, 'mat': js['materials'][pr['material']]['name'], 'pos': out_pos, 'uv': out_uv,
                  'raw': out_raw, 'idx': out_idx, 'src_vertices': len(pos)})

# ----- v4 (product owner, 2026-11-21: "a rounder body, a rounder and bigger head, a shorter fuller muzzle") -----
# Done in the bind pose AFTER the UVs (computed on the original shape, so the face picture stays on the same vertices),
# skin weights interpolated, inverse bind matrices untouched:
# 1. the torso, neck and haunches subdivided (red-green: a fully marked triangle into 4, its neighbours into 2 or 3, so
#    no crack), new vertices at edge midpoints with their UV, normal and skin weights merged;
# 2. the head reshaped: the muzzle 40 % shorter ahead of the eyes, the skull and cheeks pulled 45 % toward a sphere;
# 3. a volume keeping (Taubin) smoothing of the body and the head, paws, ears and the eye and nose pieces kept;
# 4. smooth normals over the body (Main and Main_Light welded), so the low poly facets no longer show.
BODY = ('Main', 'Main_Light')
JNAMES = [js['nodes'][n].get('name', '') for n in _skin['joints']]


def pkey(p):
    return (round(p[0], 7), round(p[1], 7), round(p[2], 7))


def model(p):  # (right, up, forward)
    return p[0], p[2], -p[1]


def decode_skin(prim, v):
    attrs = prim['attrs']
    jt = js['accessors'][attrs['JOINTS_0']]['componentType']
    wa = js['accessors'][attrs['WEIGHTS_0']]
    j = struct.unpack('<4B' if jt == 5121 else '<4H', prim['raw']['JOINTS_0'][v])
    if wa['componentType'] == 5126:
        w = struct.unpack('<4f', prim['raw']['WEIGHTS_0'][v])
    elif wa['componentType'] == 5121:
        w = [x / 255.0 for x in struct.unpack('<4B', prim['raw']['WEIGHTS_0'][v])]
    else:
        w = [x / 65535.0 for x in struct.unpack('<4H', prim['raw']['WEIGHTS_0'][v])]
    return list(j), list(w)


def encode_skin(prim, joints, weights):
    attrs = prim['attrs']
    jt = js['accessors'][attrs['JOINTS_0']]['componentType']
    wa = js['accessors'][attrs['WEIGHTS_0']]
    jb = struct.pack('<4B' if jt == 5121 else '<4H', *joints)
    if wa['componentType'] == 5126:
        wb = struct.pack('<4f', *weights)
    elif wa['componentType'] == 5121:
        q = [int(round(x * 255)) for x in weights]
        q[0] += 255 - sum(q)
        wb = struct.pack('<4B', *q)
    else:
        q = [int(round(x * 65535)) for x in weights]
        q[0] += 65535 - sum(q)
        wb = struct.pack('<4H', *q)
    return jb, wb


def dominant(prim, v):
    j, w = decode_skin(prim, v)
    return JNAMES[j[max(range(4), key=lambda i: w[i])]]


def selected(prim, tri):
    if prim['mat'] not in BODY:
        return False
    ps = [model(prim['pos'][v]) for v in tri]
    cu = sum(p[1] for p in ps) / 3.0
    cf = sum(p[2] for p in ps) / 3.0
    if not (SUBDIV_UP < cu and SUBDIV_BACK < cf < SUBDIV_FRONT):
        return False
    return not any(dominant(prim, v).startswith(('Tail', 'Ear')) for v in tri)


SUBDIV_UP, SUBDIV_BACK, SUBDIV_FRONT = 0.0150, -0.0140, 0.0172
marked = set()
nsel = 0
for prim in prims:
    for t in range(0, len(prim['idx']), 3):
        tri = prim['idx'][t:t + 3]
        if selected(prim, tri):
            nsel += 1
            keys = [pkey(prim['pos'][v]) for v in tri]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                marked.add(tuple(sorted((keys[a], keys[b]))))
print('subdivision: %d triangles selected, %d edges marked' % (nsel, len(marked)))

total_tris = 0
for prim in prims:
    pos, uv, raw, idx = prim['pos'], prim['uv'], prim['raw'], prim['idx']
    mids = {}

    def mid(a, b):
        k = (min(a, b), max(a, b))
        if k in mids:
            return mids[k]
        pa, pb = pos[a], pos[b]
        pos.append(tuple((pa[i] + pb[i]) * 0.5 for i in range(3)))
        uv.append(((uv[a][0] + uv[b][0]) * 0.5, (uv[a][1] + uv[b][1]) * 0.5))
        na = struct.unpack('<3f', raw['NORMAL'][a])
        nb = struct.unpack('<3f', raw['NORMAL'][b])
        n = [na[i] + nb[i] for i in range(3)]
        ln = math.sqrt(sum(x * x for x in n)) or 1.0
        raw['NORMAL'].append(struct.pack('<3f', *[x / ln for x in n]))
        raw['POSITION'].append(struct.pack('<3f', *pos[-1]))
        ja, wa_ = decode_skin(prim, a)
        jb_, wb_ = decode_skin(prim, b)
        acc = {}
        for jj, ww in list(zip(ja, wa_)) + list(zip(jb_, wb_)):
            if ww > 0:
                acc[jj] = acc.get(jj, 0.0) + 0.5 * ww
        top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
        s = sum(w for _, w in top) or 1.0
        top += [(0, 0.0)] * (4 - len(top))
        jb2, wb2 = encode_skin(prim, [j for j, _ in top], [w / s for _, w in top])
        raw['JOINTS_0'].append(jb2)
        raw['WEIGHTS_0'].append(wb2)
        for k in raw:
            if k not in ('NORMAL', 'POSITION', 'JOINTS_0', 'WEIGHTS_0'):
                raw[k].append(raw[k][a])
        mids[k] = len(pos) - 1
        return mids[k]

    out = []
    for t in range(0, len(idx), 3):
        tri = idx[t:t + 3]
        keys = [pkey(pos[v]) for v in tri]
        m = [tuple(sorted((keys[i], keys[(i + 1) % 3]))) in marked for i in range(3)]
        n = sum(m)
        if n == 0:
            out += tri
        elif n == 3:
            a, b, c = tri
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            out += [a, ab, ca, ab, b, bc, ca, bc, c, ab, bc, ca]
        elif n == 1:
            i = m.index(True)
            a, b, c = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
            ab = mid(a, b)
            out += [a, ab, c, ab, b, c]
        else:
            i = m.index(False)  # the unmarked edge is tri[i] -> tri[i+1]: rotate so it is c -> a
            c, a, b = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]
            ab, bc = mid(a, b), mid(b, c)
            out += [ab, b, bc, a, ab, bc, a, bc, c]
    prim['idx'] = out
    total_tris += len(out) // 3
print('triangles after subdivision', total_tris)
assert total_tris <= 3000, total_tris
TRI_BUDGET = 3200  # v5: the dog's own budget (Tuning.BudgetPetTriangles), checked after the mouth strips

# 2. The head: shorter muzzle, rounder skull and cheeks (every piece of the head, eyes and nose included).
HEAD_C = (0.0, 0.0262, 0.0180)  # (right, up, forward)
dists = []
for prim in prims:
    for p in prim['pos']:
        r, u, f = model(p)
        if f > 0.0165 and u > 0.0215:
            dists.append(math.dist((r, u, f), HEAD_C))
HEAD_R = sum(dists) / len(dists)


def smooth01(x, a, b):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def reshape(p):
    r, u, f = model(p)
    m = smooth01(f, 0.0140, 0.0170) * smooth01(u, 0.0190, 0.0215)
    if m <= 0.0:
        return p
    f = f - m * max(0.0, f - 0.0185) * 0.40
    d = (r - HEAD_C[0], u - HEAD_C[1], f - HEAD_C[2])
    ln = math.sqrt(sum(x * x for x in d)) or 1.0
    k = 1.0 + m * 0.45 * (HEAD_R / ln - 1.0)
    r, u, f = HEAD_C[0] + d[0] * k, HEAD_C[1] + d[1] * k, HEAD_C[2] + d[2] * k
    return (r, -f, u)


cache = {}
for prim in prims:
    prim['pos'] = [cache.setdefault(pkey(p), reshape(p)) for p in prim['pos']]

# 3. Taubin smoothing over welded positions (a group = every copy of one position, any primitive).
groups = {}
for pi, prim in enumerate(prims):
    for v, p in enumerate(prim['pos']):
        groups.setdefault(pkey(p), []).append((pi, v))
gkeys = list(groups)
gindex = {k: i for i, k in enumerate(gkeys)}
gpos = [list(prims[groups[k][0][0]]['pos'][groups[k][0][1]]) for k in gkeys]
movable = []
for k in gkeys:
    members = groups[k]
    ok = all(prims[pi]['mat'] in BODY for pi, _ in members)
    p = model(prims[members[0][0]]['pos'][members[0][1]])
    ok = ok and p[1] > 0.0060 and not any(dominant(prims[pi], v).startswith('Ear') for pi, v in members)
    movable.append(ok)
nbrs = [set() for _ in gkeys]
for prim in prims:
    idx = prim['idx']
    for t in range(0, len(idx), 3):
        g = [gindex[pkey(prim['pos'][v])] for v in idx[t:t + 3]]
        for a in range(3):
            for b in range(3):
                if a != b:
                    nbrs[g[a]].add(g[b])
for it in range(3):
    for factor in (0.45, -0.47):
        new = [list(p) for p in gpos]
        for gi, p in enumerate(gpos):
            if not movable[gi] or not nbrs[gi]:
                continue
            avg = [sum(gpos[n][i] for n in nbrs[gi]) / len(nbrs[gi]) for i in range(3)]
            new[gi] = [p[i] + factor * (avg[i] - p[i]) for i in range(3)]
        gpos = new
for gi, k in enumerate(gkeys):
    for pi, v in groups[k]:
        prims[pi]['pos'][v] = tuple(gpos[gi])

# ----- 3b. v5 (DOGFACE, 2026-11-22: "the jaw opens in the logs but no open mouth is visible") -----
# On the final shape: every body triangle of the muzzle below the mouth line (MOUTH_LINE, ahead of the mouth's corner) is
# the lower jaw. The jaw is deepened (DEEPEN) and weighted to the Jaw joint (eased in from the corner, so the throat
# stretches instead of folding). The skin is CUT along the mouth line: a vertex on the line gets a second copy for the
# jaw side, and every cut edge gets a strip of two triangles between its upper and its lower copies, zero area when the
# mouth is shut, the mouth's inside when it opens (UVs in the MOUTH atlas region: dark palate at the top, the tongue's
# pink at the bottom, painted by compose_dogfur.py). The corners stay closed (the strip tapers to them).
MOUTH_LINE = [(0.0182, 0.02390), (0.0196, 0.02405), (0.0207, 0.02420), (0.0230, 0.02430)]  # (forward, up)
MOUTH_CORNER_F = 0.0182
JAW_BOTTOM_UP = 0.0212    # below it: throat and neck, never jaw
DEEPEN = 0.45             # the lower jaw's depth below the mouth line, grown by this share
JAW_RAMP = (0.0178, 0.0190)  # jaw weight eased from 0 to 1 over this forward range (lower region and corner vertices)
MOUTH_REGION = (0.60, 0.62, 0.30, 0.14)  # x, y, width, height in the atlas


def mouth_up(f):
    pts = MOUTH_LINE
    if f <= pts[0][0]:
        return pts[0][1]
    for (fa, ua), (fb, ub) in zip(pts, pts[1:]):
        if f <= fb:
            return ua + (ub - ua) * (f - fa) / (fb - fa)
    return pts[-1][1]


def set_jaw(prim, v, w):
    """Blends the Jaw joint in at weight w (the vertex's other influences scaled by 1 - w, top 4 kept)."""
    j, ws = decode_skin(prim, v)
    acc = {}
    for jj, ww in zip(j, ws):
        if ww > 0 and jj != JAW_SLOT:
            acc[jj] = acc.get(jj, 0.0) + ww * (1.0 - w)
    if w > 0:
        acc[JAW_SLOT] = w
    top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
    s = sum(x for _, x in top) or 1.0
    top += [(0, 0.0)] * (4 - len(top))
    prim['raw']['JOINTS_0'][v], prim['raw']['WEIGHTS_0'][v] = encode_skin(prim, [a for a, _ in top], [x / s for _, x in top])


def copy_vertex(prim, v, uv=None):
    prim['pos'].append(prim['pos'][v])
    prim['uv'].append(uv if uv is not None else prim['uv'][v])
    for k in prim['raw']:
        prim['raw'][k].append(prim['raw'][k][v])
    return len(prim['pos']) - 1


if V5_MOUTH:
    tri_list = []  # (pi, t, keys, lower)
    for pi, prim in enumerate(prims):
        idx = prim['idx']
        for t in range(0, len(idx), 3):
            ks = [pkey(prim['pos'][v]) for v in idx[t:t + 3]]
            ps = [model(prim['pos'][v]) for v in idx[t:t + 3]]
            cu = sum(p[1] for p in ps) / 3.0
            cf = sum(p[2] for p in ps) / 3.0
            lower = prim['mat'] in BODY and cf > MOUTH_CORNER_F and JAW_BOTTOM_UP < cu < mouth_up(cf)
            tri_list.append((pi, t, ks, lower, cu, cf))
    edge_tris = {}
    for n, (pi, t, ks, lower, cu, cf) in enumerate(tri_list):
        for a in range(3):
            edge_tris.setdefault(tuple(sorted((ks[a], ks[(a + 1) % 3]))), []).append(n)
    cut, other_boundary = set(), set()
    for e, ns in edge_tris.items():
        lows = [n for n in ns if tri_list[n][3]]
        ups = [n for n in ns if not tri_list[n][3]]
        if not lows or not ups:
            continue
        lo, up = tri_list[lows[0]], tri_list[ups[0]]
        du, df = up[4] - lo[4], up[5] - lo[5]
        if du > 0 and du > 0.7 * abs(df) and prims[up[0]]['mat'] in BODY:
            cut.add(e)
        else:
            other_boundary.add(e)
    vert_cut = {}
    vert_other = set()
    for e in cut:
        for k in e:
            vert_cut[k] = vert_cut.get(k, 0) + 1
    for e in other_boundary:
        vert_other.update(e)
    split = {k for k in vert_cut if k not in vert_other}
    corner = {k for k in vert_cut if k in vert_other} | (vert_other - set(vert_cut))
    lower_keys = set()
    for (pi, t, ks, lower, cu, cf) in tri_list:
        if lower:
            lower_keys.update(ks)
    inner = lower_keys - split - corner
    print('mouth: %d lower triangles, %d cut edges, %d split vertices, %d corner/back vertices, %d jaw vertices' % (
        sum(1 for x in tri_list if x[3]), len(cut), len(split), len(corner), len(inner)))

    # Deepen the lower jaw (inner vertices only: the cut line and the corners stay where they are).
    for prim in prims:
        prim['pos'] = [p if pkey(p) not in inner else
                       (p[0], p[1], mouth_up(-p[1]) - (mouth_up(-p[1]) - p[2]) * (1.0 + DEEPEN * smooth01(-p[1], *JAW_RAMP)))
                       for p in prim['pos']]
    # The cut follows triangle edges (a zigzag): its vertices are slid up or down onto the mouth line (at most SNAP), so
    # the lips meet on a clean curve, level under the nose and falling to the corners.
    SNAP = 0.0004
    for prim in prims:
        prim['pos'] = [p if pkey(p) not in split else
                       (p[0], p[1], p[2] + max(-SNAP, min(SNAP, mouth_up(-p[1]) - p[2])))
                       for p in prim['pos']]

    def ramp(f):
        return smooth01(f, *JAW_RAMP)

    # Inner jaw vertices (full ramp) and the back boundary and corner vertices (half of it): weighted in place, once per
    # vertex (keys from before the deepening).
    weighted = set()
    for (pi, t, ks, lower, cu, cf) in tri_list:
        prim = prims[pi]
        for k, v in zip(ks, prim['idx'][t:t + 3]):
            if (pi, v) in weighted or (k not in inner and k not in corner):
                continue
            weighted.add((pi, v))
            set_jaw(prim, v, ramp(-prim['pos'][v][1]) * (1.0 if k in inner else 0.5))
    # Split vertices: the lower triangles take a jaw copy.
    lower_copy = {}
    for (pi, t, ks, lower, cu, cf) in tri_list:
        if not lower:
            continue
        prim = prims[pi]
        for i in range(3):
            v = prim['idx'][t + i]
            if ks[i] in split:
                if (pi, v) not in lower_copy:
                    c = copy_vertex(prim, v)
                    set_jaw(prim, c, max(ramp(-prim['pos'][v][1]), 0.0))
                    lower_copy[(pi, v)] = c
                prim['idx'][t + i] = lower_copy[(pi, v)]
    # The strips: for each cut edge, in the upper triangle's primitive, with the upper triangle's winding.
    mx0, my0, mw, mh = MOUTH_REGION

    def mouth_s(p):
        r, u, f = model(p)
        return 0.5 + math.atan2(r, max(f - (MOUTH_CORNER_F - 0.0010), 1e-6)) / math.pi

    strip_v = {}
    strips = 0
    mouth_segments = []

    def strip_vertex(pi, key, side, src_v):
        """The strip's copy of a cut position: 'up' (head side) or 'low' (jaw side), the mouth's UV."""
        if (pi, key, side) in strip_v:
            return strip_v[(pi, key, side)]
        prim = prims[pi]
        p = prim['pos'][src_v]
        vv = 0.0 if side == 'up' else 1.0
        c = copy_vertex(prim, src_v, (mx0 + mw * (0.04 + 0.92 * mouth_s(p)), my0 + mh * (0.06 + 0.88 * vv)))
        if key in split:
            set_jaw(prim, c, ramp(-p[1]) if side == 'low' else 0.0)
        strip_v[(pi, key, side)] = c
        return c

    for e in cut:
        ns = edge_tris[e]
        up = next(tri_list[n] for n in ns if not tri_list[n][3])
        pi, t, ks = up[0], up[1], up[2]
        prim = prims[pi]
        tri_v = prim['idx'][t:t + 3]
        ia = next(i for i in range(3) if ks[i] in e and ks[(i + 1) % 3] in e)
        ka, kb = ks[ia], ks[(ia + 1) % 3]
        va, vb = tri_v[ia], tri_v[(ia + 1) % 3]
        if ka not in split and kb not in split:
            continue
        # How much the face projection squeezes this edge (1 = seen from the front): the painted line thins with it, so the
        # sides of the muzzle (front projected, squeezed) do not smear a wide band.
        pa3, pb3 = prim['pos'][va], prim['pos'][vb]
        uv_len = math.dist(prim['uv'][va], prim['uv'][vb])
        squeeze = min(1.0, uv_len / max(math.dist(pa3, pb3) * FACE_SIZE * FACE_SX / 1024.0, 1e-9))
        mouth_segments.append([prim['uv'][va], prim['uv'][vb], squeeze])
        au, bu = strip_vertex(pi, ka, 'up', va), strip_vertex(pi, kb, 'up', vb)
        al = strip_vertex(pi, ka, 'low', va) if ka in split else au
        bl = strip_vertex(pi, kb, 'low', vb) if kb in split else bu
        if ka in split:
            prim['idx'] += [bu, au, al]
            strips += 1
        if kb in split:
            prim['idx'] += [bu, al, bl]
            strips += 1
    print('mouth strip triangles', strips)

# 4. Smooth normals: the body welded over Main and Main_Light, every other piece over itself; area weighted.
acc = {}
for pi, prim in enumerate(prims):
    cls = 'body' if prim['mat'] in BODY else prim['mat']
    idx, pos = prim['idx'], prim['pos']
    for t in range(0, len(idx), 3):
        a, b, c = (pos[v] for v in idx[t:t + 3])
        e1 = [b[i] - a[i] for i in range(3)]
        e2 = [c[i] - a[i] for i in range(3)]
        cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        for v in idx[t:t + 3]:
            key = (cls, pkey(pos[v]))
            s = acc.setdefault(key, [0.0, 0.0, 0.0])
            for i in range(3):
                s[i] += cr[i]
for pi, prim in enumerate(prims):
    cls = 'body' if prim['mat'] in BODY else prim['mat']
    for v, p in enumerate(prim['pos']):
        n = acc.get((cls, pkey(p)))
        if n is None:
            continue
        ln = math.sqrt(sum(x * x for x in n)) or 1.0
        prim['raw']['NORMAL'][v] = struct.pack('<3f', *[x / ln for x in n])
        prim['raw']['POSITION'][v] = struct.pack('<3f', *p)

for prim in prims:
    pr, attrs, out_pos, out_uv, out_raw, out_idx = prim['pr'], prim['attrs'], prim['pos'], prim['uv'], prim['raw'], prim['idx']
    count = len(out_pos)
    total_v += count
    new_attrs = {}
    for k, ai in attrs.items():
        src = js['accessors'][ai]
        view = add_view(b''.join(out_raw[k]), 34962)
        mn = mx = None
        if k == 'POSITION':
            mn = [min(p[i] for p in out_pos) for i in range(3)]
            mx = [max(p[i] for p in out_pos) for i in range(3)]
        new_attrs[k] = add_accessor(view, src['componentType'], count, src['type'], src.get('normalized', False), mn, mx)
    uvdata = b''.join(struct.pack('<ff', u, v) for u, v in out_uv)
    new_attrs['TEXCOORD_0'] = add_accessor(add_view(uvdata, 34962), 5126, count, 'VEC2', False,
                                           [min(u for u, _ in out_uv), min(v for _, v in out_uv)], [max(u for u, _ in out_uv), max(v for _, v in out_uv)])
    if count < 65536:
        idata = struct.pack('<%dH' % len(out_idx), *out_idx)
        ictype = 5123
    else:
        idata = struct.pack('<%dI' % len(out_idx), *out_idx)
        ictype = 5125
    pr['indices'] = add_accessor(add_view(idata, 34963), ictype, len(out_idx), 'SCALAR')
    pr['attributes'] = new_attrs
    print(prim['mat'], 'vertices', prim['src_vertices'], '->', count, 'triangles', len(out_idx) // 3)
_skin['inverseBindMatrices'] = add_accessor(add_view(b''.join(struct.pack('<16f', *m) for m in _ibm), None), 5126, len(_ibm), 'MAT4')
print('jaw vertices', jaw_count[0], 'joints', len(_skin['joints']))
final_tris = sum(len(p['idx']) // 3 for p in prims)
print('final triangles', final_tris, 'of', TRI_BUDGET)
assert final_tris <= TRI_BUDGET, final_tris
pad4(new_bin)
js['buffers'][0]['byteLength'] = len(new_bin)
jb = json.dumps(js, separators=(',', ':')).encode('utf-8')
while len(jb) % 4:
    jb += b' '
total = 12 + 8 + len(jb) + 8 + len(new_bin)
out = struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(jb), 0x4E4F534A) + jb + struct.pack('<II', len(new_bin), 0x004E4942) + bytes(new_bin)
open(DST, 'wb').write(out)
print('wrote', DST, len(out), 'bytes, vertices', total_v)

# The UV template: region frames, labels and every triangle, for whoever paints DogFur.png.
from PIL import Image, ImageDraw
S = 1024
img = Image.new('RGBA', (S, S), (40, 40, 44, 255))
d = ImageDraw.Draw(img)
colours = {'face': (250, 250, 120), 'side': (230, 180, 90), 'top': (120, 200, 230), 'bottom': (200, 130, 220), 'front': (140, 220, 120), 'back': (240, 120, 120)}
labels = {'face': 'FACE (labrador_black_face_front.png, eyes and nose on the model''s)', 'side': 'SIDE (both flanks, mirrored; snout right, back up)', 'top': 'BACK (seen from above, snout up)',
          'bottom': 'BELLY (seen from below, snout up)', 'front': 'FACE / CHEST', 'back': 'RUMP / TAIL END'}
for g, tris in tris_by_group.items():
    for tri in tris:
        pts = [(u * S, v * S) for u, v in tri]
        d.polygon(pts, outline=colours[g])
for g, (ox, oy) in REGIONS.items():
    d.text((ox * S + 4, oy * S + 2), labels[g], fill=(255, 255, 255, 255))
if V5_MOUTH:
    mx0, my0, mw, mh = MOUTH_REGION
    d.rectangle([mx0 * S, my0 * S, (mx0 + mw) * S, (my0 + mh) * S], outline=(240, 110, 140))
    d.text((mx0 * S + 4, my0 * S + 2), 'MOUTH INSIDE (left corner, front, right corner; upper lip top, lower lip bottom)', fill=(255, 255, 255, 255))
    for a, b, _ in mouth_segments:
        d.line([(a[0] * S, a[1] * S), (b[0] * S, b[1] * S)], fill=(240, 110, 140), width=2)
d.text((560, 520), 'Out of Sight dog (Quaternius Husky) UV0 layout', fill=(255, 255, 255, 255))
d.text((560, 536), 'DogFur.png (2048) is composed on this layout by compose_dogfur.py;', fill=(255, 255, 255, 255))
d.text((560, 552), 'see docs/next/progress/DOGBIG.md.', fill=(255, 255, 255, 255))
img.save(TEMPLATE)
json.dump({'triangles': areas, 'regions': REGIONS, 'K': K, 'U0': U0, 'U1': U1, 'F0': F0, 'F1': F1, 'R': R, 'face_size': FACE_SIZE,
           'mouth_line': mouth_segments if V5_MOUTH else [], 'mouth_region': MOUTH_REGION if V5_MOUTH else None}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'husky_uv.json'), 'w'))
print('template', TEMPLATE, {g: len(t) for g, t in tris_by_group.items()})
