"""Attach the low-poly Labrador head to the animated body from the game."""

import json
import math
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageFilter

from glb_inspect import read_accessor, read_glb
from labrador_head import (SOURCE, PIXEL_METRES, REFERENCE_Y, REFERENCE_Z, HeadProfile,
                           MeshSurface, facial_details, projected_front)
from room_dressing import GLB, Model


ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "ArtHandoff"
OUTPUT = ART / "LabradorFinal"
BODY = ROOT / "Assets/ThirdParty/Models/Quaternius/quaternius_husky.glb"
FUR = ROOT / "Assets/Art/Characters/Resources/DogFur.png"
ATLAS = ROOT / "tools/assets/dog/husky_uv.json"
HEAD_SCALE = .85
BODY_JOIN = -.0032
HEAD_JOIN = .00065
PROFILE_EAR_RIBS = (
    ((676,96), (738,80), (769,103), -.0015),
    ((557,143), (679,121), (758,142), .005),
    ((455,234), (636,200), (749,230), .009),
    ((407,357), (618,310), (749,352), .012),
    ((460,454), (614,409), (758,444), .014),
    ((542,543), (649,511), (766,542), .012),
    ((618,612), (691,590), (760,610), .007),
    ((673,646), (711,650), (748,646), .0012),
)


@dataclass
class Vertex:
    point: np.ndarray
    normal: np.ndarray
    uv: np.ndarray
    color: np.ndarray
    weights: np.ndarray


def normalized(vector):
    return vector / max(1e-10, np.linalg.norm(vector))


def smoothstep(value):
    t = np.clip(value, 0, 1)
    return t*t*(3-2*t)


def refine_profile(points):
    """Refine the fitted silhouette while preserving the body and pose setup."""
    x,y,z = points.T
    nape = smoothstep((y+.0154)/.0021)*smoothstep((z-.0218)/.0024)
    nape *= 1-smoothstep((z-.0257)/.0026)
    nape *= 1-smoothstep((y+.0100)/.0034)
    throat = smoothstep((-y-.0147)/.0021)*(1-smoothstep((-y-.01785)/.00135))
    throat *= smoothstep((z-.0184)/.0031)*(1-smoothstep((z-.0227)/.0020))
    sides = smoothstep((z-.0190)/.0032)*(1-smoothstep((z-.0247)/.0020))
    sides *= smoothstep((-y-.0089)/.0034)*(1-smoothstep((-y-.0159)/.0026))
    crown = .13*np.maximum(0,z-.0271)*smoothstep((-y-.0115)/.0021)
    muzzle = smoothstep((-y-.0182)/.0030)
    chin = smoothstep((-y-.01835)/.00165)*(1-smoothstep((z-.02265)/.00225))
    bridge = muzzle*smoothstep((z-.0244)/.0016)
    return np.column_stack((x*(1+.105*sides),
                            y+.00118*nape-.00057*throat-.00028*muzzle,
                            z-crown+.00067*chin+.00013*bridge))


def reshape_profile(triangles):
    vertices = list({id(v):v for tri in triangles for v in tri}.values())
    points = np.asarray([v.point for v in vertices])
    fitted = refine_profile(points)
    # Transform the normals with the inverse transpose of the deformation.
    offsets = np.eye(3)*.000002
    jacobian = np.stack([(refine_profile(points+offset)-refine_profile(points-offset))
                         / (2*np.linalg.norm(offset)) for offset in offsets],axis=1)
    normals = np.asarray([v.normal for v in vertices])
    normals = np.linalg.solve(jacobian,normals[...,None])[...,0]
    for v,point,normal in zip(vertices,fitted,normals):
        v.point = point
        v.normal = normalized(normal)


def between(a,b,t):
    return Vertex(a.point*(1-t)+b.point*t, normalized(a.normal*(1-t)+b.normal*t),
                  a.uv*(1-t)+b.uv*t, a.color*(1-t)+b.color*t, a.weights*(1-t)+b.weights*t)


def key(vertex):
    return tuple(np.round(vertex.point, 8))


def cut(triangles, field, positive):
    output = []
    edge = {}
    links = set()
    for triangle in triangles:
        values = [field(vertex.point)*(1 if positive else -1) for vertex in triangle]
        polygon = []
        crossings = []
        for i,a in enumerate(triangle):
            j = (i+1)%3
            if values[i] >= 0:
                polygon.append(a)
            if (values[i] >= 0) != (values[j] >= 0):
                v = between(a,triangle[j],values[i]/(values[i]-values[j]))
                edge.setdefault(key(v), v)
                crossings.append(key(v))
                polygon.append(v)
        if len(crossings)==2 and crossings[0]!=crossings[1]:
            links.add(tuple(sorted(crossings)))
        output.extend((polygon[0],polygon[i],polygon[i+1]) for i in range(1,len(polygon)-1))
    return output, edge, links


def collar(point):
    return point[2] - .90*(point[1]+.014) - .024


def lip(point):
    f = -point[1]
    return point[2] - (.02355 + .22*(f-.0185) - 4.0*max(0,.0182-f))


def read_triangles(document, binary, joints, from_head):
    transform = np.array(((.059,0,0),(0,0,-.036),(0,.049,0)))
    translate = np.array((0,-.0162,.0196))
    for part in document["meshes"][0]["primitives"]:
        fields = {name: np.asarray(read_accessor(document,binary,index))
                  for name,index in part["attributes"].items()}
        positions = fields["POSITION"]
        normals = fields["NORMAL"]
        if from_head:
            positions = positions@transform.T + translate
            normals = normals@np.linalg.inv(transform)
        verts = []
        for i,pos in enumerate(positions):
            weight = np.zeros(len(joints))
            if not from_head:
                np.add.at(weight, fields["JOINTS_0"][i], fields["WEIGHTS_0"][i])
            rgba = fields.get("COLOR_0")
            verts.append(Vertex(pos, normalized(normals[i]), fields["TEXCOORD_0"][i],
                                rgba[i] if rgba is not None else np.ones(4),weight))
        indices = np.asarray(read_accessor(document,binary,part["indices"])).reshape(-1,3)
        name = document["materials"][part["material"]]["name"]
        yield name, [tuple(verts[i] for i in tri) for tri in indices]


def assign_head(triangles, joints, jaw=False, palate=False):
    done = set()
    for triangle in triangles:
        for v in triangle:
            if id(v) in done:
                continue
            done.add(id(v))
            x, y, _ = v.point
            f = -y
            head = smoothstep((collar(v.point)-HEAD_JOIN)/.0041)
            jaw_weight = float(np.clip((f-.0180)/.00135,0,1)) if jaw else 0
            v.weights[:] = 0
            v.weights[joints.index("Neck3")] = 1-head
            v.weights[joints.index("Head")] = head*(1-jaw_weight)
            v.weights[joints.index("Jaw")] = head*jaw_weight
            if palate:
                # Keep the lips dark at the rim. The mouth tint stays inward.
                v.uv = np.array((.75 + 32*x, .641))


def loop(vertices, links, axis, center):
    neighbors = {k:[] for k in vertices}
    for a,b in links:
        neighbors[a].append(b)
        neighbors[b].append(a)
    if not all(len(n)==2 for n in neighbors.values()):
        raise ValueError("The mesh cut does not form a closed polygon.")
    def project(k):
        point = vertices[k].point-center
        return point[0],np.dot(point,axis)
    start = min(vertices,key=lambda k:math.atan2(project(k)[1],project(k)[0]))
    sequence = [start]
    while len(sequence)<len(vertices):
        options = [n for n in neighbors[sequence[-1]] if n not in sequence]
        if not options:
            raise ValueError("Multiple contours in the mesh cut.")
        sequence.append(options[0])
    uv = np.array([project(k) for k in sequence])
    next_uv = np.roll(uv,-1,axis=0)
    if np.sum(uv[:,0]*next_uv[:,1]-uv[:,1]*next_uv[:,0])<0:
        sequence = [start]+sequence[:0:-1]
    return [vertices[k] for k in sequence]


def collar_ring(vertices, links, axis):
    points = np.array([v.point for v in vertices.values()])
    projected = points@axis
    center = (projected.min()+projected.max())/2
    ordered = loop(vertices,links,axis,axis*center)
    angles = np.array([math.atan2(np.dot(v.point,axis)-center,v.point[0]) for v in ordered])
    # Keep the cut edges in connectivity order across small angular reversals.
    monotone = np.maximum.accumulate(angles)+1e-7*np.arange(len(angles))
    return list(zip(monotone,ordered))


def at_angle(ring, angle):
    angles = [a for a,_ in ring]
    hi = int(np.searchsorted(angles,angle,side="right"))
    lo = (hi-1)%len(ring)
    a,u = ring[lo]
    b,v = ring[hi%len(ring)]
    if hi == 0:
        a -= math.tau
    if hi == len(ring):
        b += math.tau
    return between(u,v,(angle-a)/(b-a))


def stitch_rings(first, second, reverse):
    i = j = 0
    while i < len(first) or j < len(second):
        an = first[i][0] if i < len(first) else math.inf
        bn = second[j][0] if j < len(second) else math.inf
        u,v = first[(i-1)%len(first)][1],second[(j-1)%len(second)][1]
        if an < bn:
            w = first[i][1]
            i += 1
        else:
            w = second[j][1]
            j += 1
        yield (u,v,w) if reverse else (u,w,v)


def neck_rings(body, head, transverse, direction):
    levels = (1/3, 2/3)
    rings = [[] for _ in levels]
    for angle in np.linspace(-math.pi,math.pi,16,endpoint=False):
        start,end = at_angle(body,angle),at_angle(head,angle)
        radial = np.array((math.cos(angle),0,0))+math.sin(angle)*transverse
        length = np.dot(end.point-start.point,direction)
        slopes = [-np.dot(v.normal,direction)/max(.5,np.dot(v.normal,radial)) for v in (start,end)]
        start_tangent,end_tangent = [length*(direction+np.clip(s,-.85,.85)*radial) for s in slopes]
        for t,ring in zip(levels,rings):
            vertex = between(start,end,t)
            # Cubic Hermite keeps the loft tangent to both trimmed surfaces.
            blend = t*t*(3-2*t)
            vertex.point = (1-blend)*start.point+blend*end.point \
                + t*(1-t)*((1-t)*start_tangent-t*end_tangent)
            tangent = (6*t*(1-t)*(end.point-start.point)
                       +(1-4*t+3*t*t)*start_tangent+(3*t*t-2*t)*end_tangent)
            ring.append((angle,vertex,tangent,radial))
    result = []
    for ring in rings:
        for i,(_,vertex,tangent,radial) in enumerate(ring):
            across = ring[(i+1)%len(ring)][1].point-ring[i-1][1].point
            normal = normalized(np.cross(tangent,across))
            vertex.normal = normal if np.dot(normal,radial)>0 else -normal
        result.append([(angle,vertex) for angle,vertex,_,_ in ring])
    return result


def coat_uv(points, atlas, chart="side"):
    x,y,up = np.asarray(points).T
    ox,oy = atlas["regions"][chart]
    across = -y-atlas["F0"] if chart=="side" else x+atlas["R"]
    down = atlas["F1"]+y if chart=="top" else atlas["U1"]-up
    return np.stack((ox+across*atlas["K"],oy+down*atlas["K"]),axis=-1)


def join_collar(body, body_links, head, head_links, body_faces, atlas):
    axis = normalized(np.array((0,-1,-.9)))
    direction = normalized(np.array((0,-.9,1)))
    a,b = collar_ring(body,body_links,axis),collar_ring(head,head_links,axis)
    directed = {}
    for triangle in body_faces:
        for u,v in zip(triangle,triangle[1:]+triangle[:1]):
            edge = (key(u),key(v))
            if tuple(sorted(edge)) in body_links:
                directed[edge] = (u,v)
    a_keys = [key(v) for _,v in a]
    loop_edges = list(zip(a_keys,a_keys[1:]+a_keys[:1]))
    reverse = sum(edge in directed for edge in loop_edges)>sum(edge[::-1] in directed for edge in loop_edges)
    rings = [a,*neck_rings(a,b,axis,direction),b]
    triangles = []
    for first,second in zip(rings,rings[1:]):
        for triangle in stitch_rings(first,second,reverse):
            border = [key(v) for v in triangle if key(v) in body]
            original = [body[k] for k in border]
            if len(border)==2:
                pair = tuple(border)
                original = directed.get(pair,directed.get(pair[::-1]))
            if original:
                source = {key(v):v.uv for v in original}
                # At the cut, keep both sides of the original UV seams.
                u,v = original[0].uv
                chart = "side" if v < .4 else "front" if u < .14 else "top"
                triangle = tuple(replace(point,uv=source.get(key(point),coat_uv(point.point,atlas,chart)))
                                 for point in triangle)
            triangles.append(triangle)
    return triangles


def mouth_cap(edge, links, upper, joints):
    normal = np.array((0,0,-1 if upper else 1))
    center = np.mean([v.point for v in edge.values()],axis=0)
    ordered = loop(edge,links,np.array((0,1,0)),center)
    vertices = [Vertex(v.point,normal,v.uv.copy(),np.ones(4),v.weights.copy()) for v in ordered]
    middle = Vertex(center,normal,np.zeros(2),np.ones(4),np.zeros(len(joints)))
    triangles = []
    for i,a in enumerate(vertices):
        b = vertices[(i+1)%len(vertices)]
        cross = np.cross(a.point-center,b.point-center)
        triangles.append((middle,a,b) if np.dot(cross,normal)>0 else (middle,b,a))
    assign_head(triangles,joints,jaw=not upper,palate=True)
    middle.uv[1] = .651 if upper else .725
    return triangles


def add_geometry(writer, triangles, material):
    triangles = [tri for tri in triangles if np.linalg.norm(
        np.cross(tri[1].point-tri[0].point,tri[2].point-tri[0].point))>1e-13]
    unique = {}
    for triangle in triangles:
        for v in triangle:
            unique.setdefault(id(v),(len(unique),v))
    verts = [v for _,v in unique.values()]
    skin = np.asarray([v.weights for v in verts])
    joints = np.argsort(-skin,axis=1)[:,:4]
    weights = np.take_along_axis(skin,joints,axis=1)
    weights /= weights.sum(axis=1,keepdims=True)
    jview = writer.view(joints.astype("<u2").tobytes(),34962)
    attrs = {
        "POSITION":writer.accessor([v.point for v in verts],"VEC3",bounds=True),
        "NORMAL":writer.accessor([v.normal for v in verts],"VEC3"),
        "TEXCOORD_0":writer.accessor([v.uv for v in verts],"VEC2"),
        "COLOR_0":writer.accessor([v.color for v in verts],"VEC4"),
        "WEIGHTS_0":writer.accessor(weights,"VEC4"),
        "JOINTS_0":len(writer.data["accessors"]),
    }
    writer.data["accessors"].append({"bufferView":jview,"componentType":5123,"count":len(verts),"type":"VEC4"})
    inds = writer.accessor([unique[id(v)][0] for tri in triangles for v in tri],"SCALAR",indices=True)
    return {"attributes":attrs,"indices":inds,"material":material},len(triangles)


def sample(image, x, y):
    """Bilinear RGBA samples in the source image's pixel coordinates."""
    x = np.clip(x,0,image.shape[1]-1.001)
    y = np.clip(y,0,image.shape[0]-1.001)
    xi, yi = x.astype(int), y.astype(int)
    u,v = (x-xi)[...,None], (y-yi)[...,None]
    return (image[yi,xi]*(1-u)+image[yi,xi+1]*u)*(1-v) + (
        image[yi+1,xi]*(1-u)+image[yi+1,xi+1]*u)*v


def unfit(points):
    """Return the graft's points in the head reference frame, in metres."""
    return np.column_stack((points[:,0]/.059, (points[:,2]-.0196)/.049,
                            (-points[:,1]-.0162)/.036))


def profile_pixels(points):
    source = np.arange(1536,dtype=float)
    forward = (source-REFERENCE_Z)*PIXEL_METRES + .006*np.clip((source-1125)/298,0,1)**1.5
    return np.column_stack((np.interp(points[:,2],forward,source),
                            REFERENCE_Y-points[:,1]/PIXEL_METRES))


def head_atlas(triangles, neck_count, iris, atlas, pivot, destination):
    """Bake both lateral projections and the front reference into UV charts."""
    side = np.asarray(Image.open(SOURCE/"labrador_head_profile.png").convert("RGBA"),dtype=np.float32)
    front = np.asarray(Image.open(SOURCE/"labrador_black_face_front.png").convert("RGBA"),dtype=np.float32)
    coat = Image.open(FUR).convert("RGBA")
    fur = np.asarray(coat,dtype=np.float32)
    soft_fur = np.asarray(coat.filter(ImageFilter.GaussianBlur(2.2)),dtype=np.float32)
    size = 2048
    columns = math.ceil(math.sqrt(len(triangles)))
    cell = size//columns
    pad = 5
    chart = np.array(((pad,pad),(cell-pad-1,pad),(pad,cell-pad-1)))
    y,x = np.indices((cell,cell))
    a = np.maximum(0,(x-pad)/(cell-2*pad-1))
    b = np.maximum(0,(y-pad)/(cell-2*pad-1))
    denom = np.maximum(1,a+b)
    weights = np.stack((1-(a+b)/denom,a/denom,b/denom),axis=-1)
    texture = np.zeros((size,size,3),np.uint8)
    output = []
    eye = profile_pixels(unfit(np.array([v.point for triangle in iris for v in triangle]))).mean(axis=0)
    for index, triangle in enumerate(triangles):
        p = np.array([v.point for v in triangle])
        positions = (weights@p).reshape(-1,3)
        local = unfit(pivot+(positions-pivot)/HEAD_SCALE)
        lateral = profile_pixels(local)
        frontal = projected_front(local)
        # Bring the photographed eye over the mesh's facial landmark.
        offset = lateral-eye
        region = np.exp(-np.sum((offset/np.array((105,66)))**2,axis=1))
        photo_eye = np.array((1018,273))
        lateral += region[:,None]*(photo_eye-eye)
        iris_offset = lateral-photo_eye
        iris_region = np.exp(-np.sum((iris_offset/np.array((65,45)))**2,axis=1))
        lateral -= .15*iris_region[:,None]*iris_offset
        side_rgba = sample(side,*lateral.T)
        front_rgba = sample(front,*frontal.T)
        normals = (weights@np.array([v.normal for v in triangle])).reshape(-1,3)
        yaw = -normals[:,1] - np.abs(normals[:,0])
        ear_x,ear_y = lateral.T
        ear_region = smoothstep((ear_x-350)/150)*(1-smoothstep((ear_x-755)/110))
        ear_region *= smoothstep((ear_y-65)/100)*(1-smoothstep((ear_y-585)/145))
        blend = smoothstep((yaw+.26)/.68)*(1-.9*ear_region)
        side_alpha = np.clip((side_rgba[:,3]-50)/172,0,1)*(1-blend)
        front_alpha = np.clip((front_rgba[:,3]-60)/165,0,1)*blend
        coverage = side_alpha+front_alpha
        photo = (side_rgba[:,:3]*side_alpha[:,None]+front_rgba[:,:3]*front_alpha[:,None])
        distance = positions[:,2]-.90*(positions[:,1]+.014)-.024
        neck = smoothstep((distance-BODY_JOIN)/.0052)[:,None]
        pixels = coat_uv(positions,atlas)*np.array(coat.size)-.5
        sharp = sample(fur,*pixels.T)[:,:3]
        soft = sample(soft_fur,*pixels.T)[:,:3]
        undercoat = (sharp*(1-.70*neck)+soft*.70*neck)*(1-.14*neck)
        if index < neck_count:
            original_uv = (weights@np.array([v.uv for v in triangle])).reshape(-1,2)
            original_coat = sample(fur,*(original_uv*np.array(coat.size)-.5).T)[:,:3]
            source = 1-smoothstep((distance-BODY_JOIN)/.00135)[:,None]
            undercoat = undercoat*(1-source)+original_coat*source
        # Start the portrait in the neck, behind the silhouette of the ear.
        graft = smoothstep((distance+.00135)/.00445)
        rgb = undercoat*(1-(coverage*graft)[:,None])+photo*graft[:,None]
        tile_x, tile_y = (index%columns)*cell, (index//columns)*cell
        texture[tile_y:tile_y+cell,tile_x:tile_x+cell] = np.clip(rgb,0,255).astype(np.uint8).reshape(cell,cell,3)
        uv = (chart+np.array((tile_x,tile_y))+.5)/size
        output.append(tuple(Vertex(v.point,v.normal,z,np.ones(4),v.weights) for v,z in zip(triangle,uv)))
    Image.fromarray(texture).save(destination)
    return output


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    body, body_bin, *_ = read_glb(BODY)
    staging = ROOT / "Build/labrador-full"
    staging.mkdir(parents=True,exist_ok=True)
    alpha = Image.open(SOURCE/"labrador_head_profile.png").getchannel("A")
    profile = HeadProfile(np.asarray(alpha))
    reference = Model("head_for_profile")
    coat = reference.material("Pelage court")
    surface = profile.mesh(reference,coat,True,compact=True,ear_ribs=PROFILE_EAR_RIBS)
    facial_details(reference,MeshSurface(surface,projected_front,2),True,compact=True)
    with TemporaryDirectory(dir=staging) as temp:
        reference.save(Path(temp))
        head, head_bin, *_ = read_glb(Path(temp)/"head_for_profile.glb")
    atlas = json.loads(ATLAS.read_text(encoding="utf-8"))
    names = [body["nodes"][n]["name"] for n in body["skins"][0]["joints"]]
    inverse_binds = read_accessor(body,body_bin,body["skins"][0]["inverseBindMatrices"])
    pivot = np.linalg.inv(np.asarray(inverse_binds[names.index("Jaw")]).reshape(4,4).T)[:3,3]
    body_cut, body_boundary, body_links = [], {}, set()
    for _, triangles in read_triangles(body,body_bin,names,False):
        kept, edge, links = cut(triangles,lambda p:collar(p)-BODY_JOIN,False)
        body_cut.extend(kept)
        body_links.update(links)
        for k,v in edge.items():
            body_boundary.setdefault(k,v)
    all_head = list(read_triangles(head,head_bin,names,True))
    new_skin, head_edge, head_links = cut(all_head[0][1],lambda p:collar(p)-HEAD_JOIN,True)
    upper, lip_edge, lip_links = cut(new_skin,lip,True)
    lower, _, _ = cut(new_skin,lip,False)
    # Both halves receive independent vertices at the closed lip.
    memo = {}
    def copy_vertex(v):
        return memo.setdefault(id(v),Vertex(v.point,v.normal,v.uv.copy(),v.color,v.weights.copy()))
    lower = [tuple(copy_vertex(v) for v in tri) for tri in lower]
    assign_head(upper,names)
    assign_head(lower,names,jaw=True)
    for vertex in head_edge.values():
        vertex.weights[names.index("Neck3")] = 1
    palate = mouth_cap(lip_edge,lip_links,True,names)+mouth_cap(lip_edge,lip_links,False,names)
    fitted = {id(v):v for tri in upper+lower+palate for v in tri}
    fitted.update((id(v),v) for v in head_edge.values())
    for vertex in fitted.values():
        vertex.point = pivot+(vertex.point-pivot)*HEAD_SCALE
    new_keys = {old:key(v) for old,v in head_edge.items()}
    head_edge = {new_keys[old]:v for old,v in head_edge.items()}
    head_links = {tuple(sorted((new_keys[a],new_keys[b]))) for a,b in head_links}
    mantel = join_collar(body_boundary,body_links,head_edge,head_links,body_cut,atlas)
    iris = next(triangles for name,triangles in all_head if name=="Iris brun")
    head_texture = OUTPUT/"LabradorHeadAtlas.png"
    mapped = head_atlas(mantel+upper+lower,len(mantel),iris,atlas,pivot,head_texture)
    print(f"Collar: {len(body_boundary)} / {len(head_edge)} vertices. Closed lip: {len(lip_edge)} vertices.")
    print("Surface triangles:",[len(part) for part in (body_cut,mantel,upper,lower,palate)])

    writer = GLB("Labrador")
    writer.data, writer.bin = body, bytearray(body_bin)
    image = writer.view(FUR.read_bytes())
    body["images"] = [{"bufferView":image,"mimeType":"image/png","name":"DogFur"}]
    body["samplers"] = [{"magFilter":9729,"minFilter":9987,"wrapS":33071,"wrapT":33071}]
    body["textures"] = [{"source":0,"sampler":0}]
    body["materials"] = [{"name":"Main","pbrMetallicRoughness":
                          {"baseColorTexture":{"index":0},"roughnessFactor":.68,"metallicFactor":0}}]
    head_view = writer.view(head_texture.read_bytes())
    body["images"].append({"bufferView":head_view,"mimeType":"image/png","name":"LabradorHeadAtlas"})
    body["textures"].append({"source":1,"sampler":0})
    body["materials"].append({"name":"Tete profil et face","pbrMetallicRoughness":
                              {"baseColorTexture":{"index":1},"roughnessFactor":.68,"metallicFactor":0}})
    portions = [(body_cut+palate,0),(mapped,1)]
    reshape_profile(portions[0][0]+portions[1][0])
    primitives = []
    total = 0
    for triangles, index in portions:
        pr,count = add_geometry(writer,triangles,index)
        primitives.append(pr)
        total += count
    body["meshes"][0]["primitives"] = primitives
    body["meshes"][0]["name"] = "Labrador"
    # The eyes live in the texture. This marker replaces the eye submesh as a
    # source of the visual eye center for Unity's catalog calibration.
    eye_center = np.mean([v.point for triangle in iris for v in triangle],axis=0)
    eye_center = refine_profile((pivot+(eye_center-pivot)*HEAD_SCALE)[None])[0]
    head_joint = names.index("Head")
    head_inverse_bind = np.asarray(inverse_binds[head_joint]).reshape(4,4).T
    eye_local = (head_inverse_bind@np.append(eye_center,1))[:3]
    eye_node = len(body["nodes"])
    body["nodes"].append({"name":"LabradorEyeCenter","translation":eye_local.tolist()})
    parent = body["skins"][0]["joints"][head_joint]
    body["nodes"][parent].setdefault("children",[]).append(eye_node)
    with TemporaryDirectory(dir=staging) as temp:
        exported = Path(temp)/"labrador_profile_rigged.glb"
        writer.save(exported)
        exported.replace(OUTPUT/exported.name)
    shutil.copyfile(FUR,OUTPUT/"DogFur.png")
    stats = {"triangles":total,"joints":len(names),
             "clips":[animation["name"] for animation in body["animations"]],
             "eye_marker":"Head/LabradorEyeCenter",
             "jaw_vertices":len({key(v) for tri in lower for v in tri if v.weights[names.index("Jaw")]>.95})}
    (OUTPUT/"inventory.json").write_text(json.dumps(stats,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(stats))


if __name__=="__main__":
    main()
