"""Build two Labrador head meshes from the side and front references."""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from room_dressing import Model, grid_faces


ART = Path(__file__).resolve().parents[2] / "ArtHandoff"
SOURCE = ART / "LabradorDraft"
OUTPUT = ART / "LabradorHeadV3"
FUR = "labrador_black_fur_albedo.png"
PIXEL_METRES = .00023
REFERENCE_Z = 740
REFERENCE_Y = 1008
ALPHA_THRESHOLD = 205
FRONT_CENTER = 513
FRONT_SCALE = 1.25
FRONT_TOP = 70
PROFILE_TOP = 16

# Section widths before the front silhouette and face landmarks are applied.
WIDTHS = (
    (54, 0), (82, .016), (125, .038), (205, .048), (330, .054),
    (470, .062), (650, .063), (790, .060), (889, .057), (955, .054),
    (1005, .051), (1050, .046), (1100, .040), (1160, .036),
    (1220, .034), (1290, .031), (1342, .026), (1370, .022),
    (1390, .019), (1406, .016), (1418, .010), (1423, 0),
)
FACE_WIDTHS = (
    (70, 0), (82, 76), (110, 168), (130, 219), (157, 260), (200, 289),
    (257, 308), (312, 309), (385, 305), (455, 304), (540, 292),
    (612, 279), (675, 282), (723, 308), (758, 298), (805, 267),
    (860, 225), (900, 189), (931, 145), (956, 92), (970, 70), (1315, 70),
)
EAR_RIBS = (
    ((654, 123), (696, 106), (737, 117), -.001),
    ((546, 182), (651, 161), (745, 173), .005),
    ((475, 248), (619, 235), (740, 250), .009),
    ((438, 337), (600, 316), (746, 331), .011),
    ((458, 425), (610, 399), (756, 419), .011),
    ((516, 498), (637, 468), (759, 499), .009),
    ((592, 568), (665, 537), (744, 565), .005),
    ((664, 603), (694, 600), (723, 602), .0012),
)
EYE = (
    (638, 400), (648, 382), (666, 370), (687, 368),
    (705, 376), (718, 392), (719, 404), (703, 418),
    (683, 424), (661, 419), (649, 412),
)
LIP = (
    (968, 663), (1012, 690), (1064, 699), (1110, 697),
    (1166, 681), (1231, 657), (1286, 630), (1337, 599), (1376, 551),
)


def point(horizontal, vertical, lateral):
    extension = .006 * np.clip((horizontal-1125)/(1423-1125), 0, 1)**1.5
    return (lateral, (REFERENCE_Y - vertical) * PIXEL_METRES,
            (horizontal - REFERENCE_Z) * PIXEL_METRES + extension)


def projected(vertices):
    return np.column_stack((vertices[:, 2] / PIXEL_METRES + REFERENCE_Z,
                            REFERENCE_Y - vertices[:, 1] / PIXEL_METRES))


def front_y(profile_y):
    return FRONT_TOP + (profile_y - PROFILE_TOP)*FRONT_SCALE


def projected_front(vertices):
    return np.column_stack((FRONT_CENTER + vertices[:, 0]*FRONT_SCALE/PIXEL_METRES,
                            front_y(REFERENCE_Y - vertices[:, 1]/PIXEL_METRES)))


def curve_at(x, pairs):
    xs, ys = np.asarray(pairs).T
    return float(np.interp(x, xs, ys))


def ear_relief(horizontal, vertical, ribs):
    """Raise the skull surface under the traced ear, with a gradual rim."""
    bounds = np.asarray([rib[:3] for rib in ribs])
    rows = bounds[:, :, 1].mean(axis=1)
    left,center,right = [np.interp(vertical,rows,column) for column in bounds[:, :, 0].T]
    across = np.clip(min((horizontal-left)/(center-left),(right-horizontal)/(right-center)),0,1)
    height = np.interp(vertical,rows,[max(0,rib[3]) for rib in ribs],left=0,right=0)
    return 1.20*height*across*across*(3-2*across)


class HeadProfile:
    def __init__(self, alpha):
        columns = np.flatnonzero(np.max(alpha, axis=0) >= ALPHA_THRESHOLD)
        limits = [np.flatnonzero(alpha[:, x] >= ALPHA_THRESHOLD) for x in columns]
        self.x = columns
        self.top = [rows[0] for rows in limits]
        self.bottom = [rows[-1] for rows in limits]

    def bounds(self, horizontal):
        return (np.interp(horizontal, self.x, self.top),
                np.interp(horizontal, self.x, self.bottom))

    def lateral(self, horizontal, vertical):
        top, bottom = self.bounds(horizontal)
        height = max(bottom - top, 1)
        t = float(np.clip((vertical - top) / height, 0, 1))
        width = curve_at(horizontal, WIDTHS)
        # The upper skull has flatter sides and the muzzle tapers to the nose.
        exponent = np.interp(horizontal, (54, 420, 965, 1130, 1423),
                             (.53, .36, .46, .40, .55))
        lateral = width * (4 * t * (1 - t)) ** exponent
        facial = min(1, width / .025)
        socket = .0090 * np.exp(-((horizontal-1022)/124)**2 - ((vertical-273)/52)**2)
        brow = .0042 * np.exp(-((horizontal-1001)/106)**2 - ((vertical-215)/43)**2)
        cheek = .0050 * np.exp(-((horizontal-876)/168)**2 - ((vertical-492)/149)**2)
        bridge = .0026 * np.exp(-((horizontal-1190)/142)**2 - ((vertical-414)/76)**2)
        lip_falloff = np.clip((horizontal-941)/37, 0, 1) * np.clip((1404-horizontal)/39, 0, 1)
        lip = .0016 * lip_falloff * np.exp(-((vertical-curve_at(horizontal, LIP))/17)**2)
        lateral += facial * (brow + cheek - socket - bridge - lip) * 4*t*(1-t)
        lateral *= 1 - .055*np.clip((horizontal-1100)/290, 0, 1)
        # Limit the front outline along the cheeks and the jaw. The neck is
        # behind the front portrait and continues below its crop.
        limit = curve_at(front_y(vertical), FACE_WIDTHS)*PIXEL_METRES/FRONT_SCALE
        neck = np.clip((vertical-605)/181, 0, 1)*np.clip((866-horizontal)/165, 0, 1)
        limit = max(limit, .040*neck)
        if lateral > limit*.90 and limit > 0:
            excess = (lateral/limit-.90)*10
            lateral = limit*(.90 + .10*excess/(1+excess))
        return max(0, lateral)

    def mesh(self, model, coat, low_poly, compact=False, ear_ribs=None):
        landmarks = [745, 815, 851, 925, 1008, 1099, 1116, 1130, 1419]
        if compact:
            stations = [75,175,290,410,540,660,790,850,910,990,1058,1107,
                        1132,1195,1285,1362,1400,1418]
            if ear_ribs is not None:
                stations.insert(5, 600)
            angles = np.deg2rad([0,12,26,49,72,98,126,155,180,
                                205,234,262,288,311,334,348])
        elif low_poly:
            stations = [70, 120, 175, 235, 300, 365, 430, 495, 560, 630,
                        700, 760, 809, 840, 865, 910, 967, 1018, 1068, 1107,
                        1125, 1160, 1225, 1292, 1340, 1375, 1404, 1418]
            angles = np.r_[0, 7, 15, 24, np.arange(38,180,14), 180]
            angles = np.deg2rad(np.r_[angles,360-angles[-2:0:-1]])
        else:
            stations = sorted(set(np.r_[np.arange(65, 1310, 19), np.arange(1310, 1423, 6), landmarks]))
            angles = np.arange(56)*(2*np.pi/56)
        sides = len(angles)
        vertices = []
        for horizontal in stations:
            top, bottom = self.bounds(horizontal)
            neck_cut = .085 * np.interp(horizontal, (54, 130, 739, 840), (0, 1, 1, 0))
            for angle in angles:
                fraction = (1 - np.cos(angle)) / 2
                uncut = top + (bottom-top)*fraction
                cut = neck_cut * np.interp(fraction, (.77, .90, 1), (0, 1, 1))
                vertical = min(bottom, uncut + (bottom-top)*cut)
                lateral = self.lateral(horizontal, uncut)
                if ear_ribs is not None:
                    lateral += ear_relief(horizontal,uncut,ear_ribs)
                lateral *= np.sign(np.sin(angle))
                vertices.append(point(horizontal, vertical, lateral))

        faces = grid_faces(len(stations), sides, closed=True)
        for horizontal, front in ((int(self.x[0]), False), (int(self.x[-1]), True)):
            top, bottom = self.bounds(horizontal)
            pole = len(vertices)
            vertices.append(point(horizontal, (top+bottom)/2, 0))
            offset = (len(stations)-1) * sides if front else 0
            for i in range(sides):
                a, b = offset+i, offset+(i+1)%sides
                faces.append((a,pole,b) if front else (pole,a,b))

        vertices = np.asarray(vertices)
        faces = np.asarray(faces)
        locations = projected(vertices)
        coat_uvs = locations / (460, 460)
        model.add(coat, vertices, faces, uv=coat_uvs)
        positions, normals, texture, colors, triangles = model.parts.pop(coat)[0]

        # Blend the nose and lip into the surface instead of assigning whole
        # triangles to an abrupt material edge.
        x, y = locations.T
        nose_start = np.interp(y, (390, 425, 466, 505, 539, 570),
                              (1410, 1370, 1358, 1380, 1405, 1470))
        nose = np.clip((x-nose_start)/36,0,1)*np.clip((565-y)/30,0,1)
        lip = np.exp(-((y-np.interp(x,*np.asarray(LIP).T))/17)**2)
        lip *= np.clip((x-944)/69,0,1)*np.clip((1390-x)/43,0,1)
        colors = colors.copy()
        colors[:, :3] *= (1-.37*nose-.24*lip)[:,None]
        model.parts[coat] = [(positions, normals, texture, colors, triangles)]
        return vertices, faces


def rounded_lid(points):
    """Round the photo landmarks without changing their ordering."""
    points = np.asarray(points, dtype=float)
    return np.stack((.75*points + .25*np.roll(points, -1, axis=0),
                     .25*points + .75*np.roll(points, -1, axis=0)), axis=1).reshape(-1, 2)


class MeshSurface:
    """Orthographic depth queries on the actual triangles of each variant."""

    def __init__(self, mesh, projection, axis):
        vertices, faces = mesh
        patches = projection(vertices)[faces]
        self.minimum = patches.min(axis=1)
        self.maximum = patches.max(axis=1)
        self.origin = patches[:, 0]
        self.u = patches[:, 1] - self.origin
        self.v = patches[:, 2] - self.origin
        self.area = self.u[:, 0]*self.v[:, 1] - self.u[:, 1]*self.v[:, 0]
        self.depth = vertices[faces,axis]

    def at(self, x, y):
        query = np.array((x,y))
        bounds = (self.minimum <= query).all(axis=1) & (self.maximum >= query).all(axis=1)
        selected = np.flatnonzero(bounds & (np.abs(self.area) > 1e-8))
        q = query - self.origin[selected]
        u, v = self.u[selected], self.v[selected]
        a = (q[:, 0]*v[:, 1]-q[:, 1]*v[:, 0])/self.area[selected]
        b = (u[:, 0]*q[:, 1]-u[:, 1]*q[:, 0])/self.area[selected]
        inside = (a>=-1e-7) & (b>=-1e-7) & (a+b<=1+1e-7)
        if not inside.any():
            raise ValueError(f"Reference point outside the model at {x:.1f}, {y:.1f}")
        z = self.depth[selected[inside]]
        return np.max(z[:, 0]+a[inside]*(z[:, 1]-z[:, 0])+b[inside]*(z[:, 2]-z[:, 0]))


def ear_patch(model, coat, surface, side, ridge_scale=1.0):
    vertices = []
    # A ridge and two edges, like a simple folded leaf. Embed the margins
    # into the actual loft so there is no projected gap against the cheek.
    for back, ridge, front, lift in EAR_RIBS:
        for (x,y), height in ((back,-.0013),(ridge,lift*ridge_scale),(front,-.0013)):
            vertices.append(point(x,y,side*(surface.at(x,y)+height)))
    faces = np.asarray(grid_faces(len(EAR_RIBS),3))
    if side > 0:
        faces = faces[:, ::-1]
    vertices = np.asarray(vertices)
    model.add(coat, vertices, faces, "#E3E3E3", projected(vertices)/(460,460))
    return vertices, faces


def detail(model, material, outline, center, surface, axis, sign, color, compact=False):
    outline = np.asarray(outline)
    inner = center + .60*(outline-center)
    locations = np.vstack((outline, center)) if compact else np.vstack((outline, inner, center))
    vertices = []
    for i, (x, y) in enumerate(locations):
        radius = 1 if i<len(outline) else .60 if i!=len(locations)-1 else 0
        vertices.append(surface(x,y,1-.42*radius**2))
    n = len(outline)
    offset = 0 if compact else n
    faces = [] if compact else grid_faces(2,n,closed=True)
    faces += [(offset+i,offset+(i+1)%n,len(locations)-1) for i in range(n)]
    vertices, faces = np.asarray(vertices), np.asarray(faces)
    a, b, c = vertices[faces[0]]
    if np.cross(b-a,c-a)[axis]*sign < 0:
        faces = faces[:, ::-1]
    model.add(material, vertices, faces, color)
    return vertices, faces


def facial_details(model, surface, low_poly, compact=False):
    lid = model.material("Contour des paupières", roughness=.79)
    eye = model.material("Iris brun", roughness=.41)
    pupil = model.material("Pupille", roughness=.33)
    crease = model.material("Lèvres et narines", roughness=.88)
    eye_outline = np.asarray(EYE) if low_poly else rounded_lid(EYE)
    eye_center = np.array((682, 396))
    pupil_center = np.array((681, 392))
    segments = 8 if compact else 10 if low_poly else 20
    angles = np.arange(segments)*2*np.pi/segments
    oval = np.column_stack((np.cos(angles), np.sin(angles)))
    eyes = []

    def front_point(x, y, side, depth):
        lateral = (x-FRONT_CENTER)*PIXEL_METRES/FRONT_SCALE
        vertical = PROFILE_TOP + (y-FRONT_TOP)/FRONT_SCALE
        return side*lateral, (REFERENCE_Y-vertical)*PIXEL_METRES, surface.at(x,y)+depth

    for side in (1, -1):
        for material, outline, center, lift, color in (
            (lid, eye_outline, eye_center, .0013, "#191314"),
            (eye, eye_center+oval*(28,24), eye_center, .0026, "#5A3724"),
            (pupil, pupil_center+oval*(13,14), pupil_center, .0037, "#0D0A0B"),
        ):
            eyes.append(detail(model,material,outline,center,
                               lambda x,y,s: front_point(x,y,side,s*lift),
                               2, 1, color, compact))
        nostril = np.array((566, 648))
        detail(model, crease, nostril+oval*(15,11), nostril,
               lambda x,y,s: front_point(x,y,side,s*.0008), 2, 1, "#0D0B0B",compact)
    return eyes


def draw_overlay(reference, head, ears, output):
    size = reference.size
    head_mask = Image.new("L", size)
    head_lines = Image.new("RGBA", size)
    ear_mask = Image.new("L", size)
    ear_lines = Image.new("RGBA", size)

    def draw_faces(mesh, mask, lines, color):
        vertices, faces = mesh
        coords = projected(vertices)
        triangles = vertices[faces]
        normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        patches = coords[faces[normal[:, 0]>0]]
        mask_draw, line_draw = ImageDraw.Draw(mask), ImageDraw.Draw(lines)
        for patch in patches:
            points = [tuple(row) for row in patch]
            mask_draw.polygon(points, fill=255)
            line_draw.line(points+[points[0]], fill=color, width=1)

    draw_faces(head, head_mask, head_lines, (255,198,86,139))
    draw_faces(ears, ear_mask, ear_lines, (124,225,247,180))
    head_lines.putalpha(ImageChops.subtract(head_lines.getchannel("A"), ear_mask))

    def add_outline(lines, mask, color):
        band = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),
                                   mask.filter(ImageFilter.MinFilter(3)))
        outline = Image.new("RGBA", size, color)
        outline.putalpha(band)
        return Image.alpha_composite(lines, outline)

    canvas = Image.alpha_composite(Image.new("RGBA", size, "#1B1C22"), reference)
    canvas = Image.alpha_composite(canvas, add_outline(head_lines, head_mask, "#FFD298"))
    canvas = Image.alpha_composite(canvas, add_outline(ear_lines, ear_mask, "#84E5FF"))
    canvas.convert("RGB").save(output)
    foreground = np.asarray(reference.getchannel("A")) >= ALPHA_THRESHOLD
    mask = np.asarray(head_mask)>0
    return float((mask & foreground).sum()/(mask | foreground).sum())


def draw_front_overlay(reference, patches, output):
    width, height = reference.size
    depth = np.full((height,width), -np.inf)
    drawable = []
    for (vertices, faces), color in patches:
        uv = projected_front(vertices)
        for face in faces:
            points, z = uv[face], vertices[face,2]
            low = np.maximum(np.floor(points.min(axis=0)).astype(int), 0)
            high = np.minimum(np.ceil(points.max(axis=0)).astype(int)+1, (width,height))
            if np.any(high <= low):
                continue
            a,b,c = points
            ab, ac = b-a, c-a
            area = ab[0]*ac[1]-ab[1]*ac[0]
            if abs(area)<.05:
                continue
            y,x = np.ogrid[low[1]:high[1],low[0]:high[0]]
            s = ((x-a[0])*ac[1]-(y-a[1])*ac[0])/area
            t = (ab[0]*(y-a[1])-ab[1]*(x-a[0]))/area
            tri_depth = z[0] + s*(z[1]-z[0]) + t*(z[2]-z[0])
            region = depth[low[1]:high[1],low[0]:high[0]]
            np.maximum(region, np.where((s>=0)&(t>=0)&(s+t<=1),tri_depth,-np.inf),out=region)
            drawable.append((points,z,color))

    canvas = Image.alpha_composite(Image.new("RGBA",reference.size,"#1B1C22"),reference)
    lines = Image.new("RGBA",reference.size)
    draw = ImageDraw.Draw(lines)
    for points,z,color in drawable:
        for i in range(3):
            j = (i+1)%3
            steps = max(2, int(np.linalg.norm(points[i]-points[j])))
            pixels = np.round(np.linspace(points[i],points[j],steps)).astype(int)
            trace = np.linspace(z[i],z[j],steps)
            for (x,y), sample in zip(pixels,trace):
                if 0 <= x < width and 0 <= y < height and sample >= depth[y,x] - .0014:
                    draw.point((int(x),int(y)),fill=color)
    mask = Image.fromarray(np.isfinite(depth).astype(np.uint8)*255)
    edge = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),mask.filter(ImageFilter.MinFilter(3)))
    contour = Image.new("RGBA",reference.size,"#FFD298")
    contour.putalpha(edge)
    Image.alpha_composite(Image.alpha_composite(canvas,lines),contour).convert("RGB").save(output)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / FUR, OUTPUT / FUR)
    reference = Image.open(SOURCE / "labrador_head_profile.png").convert("RGBA")
    front = Image.open(SOURCE / "labrador_black_face_front.png").convert("RGBA")
    profile = HeadProfile(np.asarray(reference.getchannel("A")))
    inventory = {}
    for low_poly in (False, True):
        model = Model("labrador_head_low_poly" if low_poly else "labrador_head_refined")
        coat = model.material("Pelage court", roughness=.73, texture=FUR, repeat=True)
        head = profile.mesh(model, coat, low_poly)
        side_surface = MeshSurface(head, projected, 0)
        right_ear = ear_patch(model, coat, side_surface, 1)
        left_ear = ear_patch(model, coat, side_surface, -1)
        eyes = facial_details(model, MeshSurface(head, projected_front, 2), low_poly)
        stats = model.save(OUTPUT)
        if low_poly:
            overlap = draw_overlay(reference, head, right_ear, OUTPUT / "low_poly_profile_overlay.png")
            stats["profile_overlap"] = round(overlap,4)
            patches = [(head,(255,198,86,155)),
                       (right_ear,(124,225,247,185)), (left_ear,(124,225,247,185))]
            patches += [(mesh,(250,166,200,210)) for mesh in eyes]
            draw_front_overlay(front, patches, OUTPUT / "low_poly_front_overlay.png")
        stats.update(rigged=False, ear_triangles=2*len(right_ear[1]), dimensions_m=np.round(
            np.subtract(stats["bounds_max_m"],stats["bounds_min_m"]),4).tolist())
        inventory[model.name] = stats
        print(model.name, json.dumps(stats))
    (OUTPUT / "inventory.json").write_text(json.dumps(inventory,indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
