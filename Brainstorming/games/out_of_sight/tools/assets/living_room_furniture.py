"""Bake the standalone living-room GLBs from procedural meshes and supplied albedos."""

import json
import math

import numpy as np

from room_dressing import Model, OUT, UP, grid_faces


DESTINATION = OUT.parent / "LivingRoomFurniture"
WOOD = "walnut_veneer.png"
LEAF = "pothos_leaf.png"
LINEN = "ivory_linen.png"


def wood_box(model, material, center, size, shift=0, grain_axis=0, shade="#FFFFFF"):
    """Panel-shaped wood with the grain following its long axis."""
    center = np.asarray(center)
    half = np.asarray(size) / 2
    axes = np.eye(3)
    for face in range(3):
        u, v = (face + 1) % 3, (face + 2) % 3
        first, second = (v, u) if v == grain_axis else (u, v)
        for side in (-1, 1):
            points = [center + side * half[face] * axes[face] + a * half[u] * axes[u] + b * half[v] * axes[v]
                      for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            if side < 0:
                points.reverse()
            uv = [(point[first] / .86 + shift, point[second] / .41 + shift * .37) for point in points]
            model.quad(material, points, shade, uv)


def rounded_wood_top(model, walnut, width, depth, y, height, radius):
    x, z = width / 2, depth / 2
    outline = []
    # Three vertices per corner retain a rounded rectangle at the normal orbit distance.
    for u, v, start in ((x-radius, z-radius, 0), (radius-x, z-radius, 90),
                         (radius-x, radius-z, 180), (x-radius, radius-z, 270)):
        for angle in (start, start + 45, start + 90):
            a = math.radians(angle)
            outline.append((u + radius * math.cos(a), v + radius * math.sin(a)))
    edge = min(.007, height * .24)
    levels = ((y, .982), (y+edge, 1), (y+height-edge, 1), (y+height, .982))
    closed = outline + outline[:1]
    lengths = [0]
    for a, b in zip(closed, closed[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    points = [(px * scale, h, pz * scale) for h, scale in levels for px, pz in closed]
    uv = [(distance / .86, (h-y) / .41) for h, _ in levels for distance in lengths]
    model.add(walnut, points, grid_faces(len(levels), len(closed)), "#DCE1DD", uv)
    for h, top in ((y, False), (y+height, True)):
        ring = [(px * .982, h, pz * .982) for px, pz in outline]
        tris = [(0, i+1, i) if top else (0, i, i+1) for i in range(1, len(ring)-1)]
        model.add(walnut, ring, tris, uv=[(px/.86 + .20, pz/.41 + .14) for px, _, pz in ring])


def wooden_leg(model, walnut, x, z, height, splay, shift):
    """A four-sided tapered wooden leg with its foot kicked outward."""
    foot_x = x + math.copysign(splay, x)
    foot_z = z + math.copysign(splay * .67, z)
    bottom = [(foot_x + sx*.018, 0, foot_z + sz*.018) for sx, sz in ((1, -1), (1, 1), (-1, 1), (-1, -1))]
    top = [(x + sx*.028, height, z + sz*.028) for sx, sz in ((1, -1), (1, 1), (-1, 1), (-1, -1))]
    for i in range(4):
        j = (i + 1) % 4
        model.quad(walnut, (bottom[i], top[i], top[j], bottom[j]), "#C3B8AA",
                   ((shift, 0), (shift + height/.86, 0), (shift + height/.86, .14), (shift, .1)))
    model.quad(walnut, bottom, "#A5A199",
               ((.12, .1), (.12, .15), (.18, .15), (.18, .1)))


def coffee_table():
    model = Model("walnut_coffee_table")
    walnut = model.material("Walnut veneer", roughness=.62, texture=WOOD, repeat=True)
    rounded_wood_top(model, walnut, 1.06, .58, .394, .038, .095)
    wood_box(model, walnut, (0, .378, 0), (.88, .034, .45), .26, shade="#B9B2A9")
    wood_box(model, walnut, (0, .145, 0), (.79, .022, .39), .42, shade="#BEC0B9")
    for index, (x, z) in enumerate(((.383, .190), (-.383, .190), (.383, -.190), (-.383, -.190))):
        wooden_leg(model, walnut, x, z, .389, .031, index*.16)
    return model


def media_console():
    model = Model("walnut_media_console")
    walnut = model.material("Walnut veneer", roughness=.62, texture=WOOD, repeat=True)
    matte = model.material("Dressing matte")
    rounded_wood_top(model, walnut, 1.44, .42, .530, .035, .037)
    wood_box(model, walnut, (0,.147,0), (1.40,.033,.39), .1, shade="#BDBAB2")
    for x in (-.684,.684):
        wood_box(model, walnut, (x,.346,0), (.034,.368,.39), .32, 1)
    for x in (-.238,.238):
        wood_box(model, walnut, (x,.346,-.001), (.021,.368,.368), .18, 1, "#AFA99F")
    wood_box(model, walnut, (0,.361,-.017), (.455,.023,.343), .31, shade="#B3B0A7")
    model.box(matte, (0,.346,-.188), (1.35,.368,.018), "#483D33")
    for x, uv_offset in ((-.462,.37),(.462,.58)):
        wood_box(model, walnut, (x,.345,.179), (.416,.344,.025), uv_offset)
    for x in (-.312,.312):
        model.bevel_box(matte, (x,.376,.198), (.059,.012,.016), "#3E4141", .002)
    for index, (x,z) in enumerate(((.49,.145),(-.49,.145),(.49,-.145),(-.49,-.145))):
        wooden_leg(model, walnut, x, z, .144, .046, .16*index)
    return model


def television():
    model = Model("flat_screen_tv")
    matte = model.material("Dressing matte")
    glass = model.material("Screen glass off", roughness=.27, metallic=.18)
    model.bevel_box(matte, (0,.009,0), (.36,.018,.221), "#303336", .005)
    model.box(matte, (0,.051,-.012), (.105,.085,.042), "#343638")
    model.bevel_box(matte, (0,.346,-.012), (1.056,.602,.061), "#24282B", .008)
    model.bevel_box(matte, (0,.336,-.045), (.657,.364,.032), "#303537", .004)
    model.quad(glass, ((.513,.063,.0191),(.513,.631,.0191),(-.513,.631,.0191),(-.513,.063,.0191)), "#17242B")
    model.box(matte, (.446,.051,.0185), (.008,.0025,.0014), "#98ACB5")
    return model


def pothos_blade(model, material, start, yaw, length, width, rise, droop, hue):
    angle = math.radians(yaw)
    outward = np.array((math.cos(angle), 0.0, math.sin(angle)))
    across = np.cross(UP, outward)
    steps = (0,.17,.36,.57,.77,1)
    widths = (0,.90,1,.81,.51,0)
    points, uv = [], []
    for row, (t, w) in enumerate(zip(steps, widths)):
        centre = np.asarray(start) + outward*(length*t) + UP*(rise*t + .025*math.sin(math.pi*t) - droop*t*t)
        if row == 0 or row == len(steps)-1:
            points.append(centre)
            uv.append((.5, 1-t))
            continue
        for col in (-1, 0, 1):
            back_sweep = -.020*abs(col) if row == 1 else 0
            # The two lobes pull toward the stem, while the point sweeps naturally downward.
            p = centre + across*(col*w*width) + outward*back_sweep - UP*(.016*w*abs(col))
            points.append(p)
            uv.append(((col+1)/2, 1-t))
    triangles = [(a+1,b+1,c+1) for a,b,c in grid_faces(len(steps)-2, 3)]
    tip = len(points)-1
    for col in range(2):
        triangles.append((0,1+col,2+col))
        triangles.append((tip-3+col,tip,tip-2+col))
    model.add(material, points, triangles, hue, uv)


def tabletop_pothos():
    model = Model("tabletop_pothos")
    matte = model.material("Dressing matte")
    leaf = model.material("Pothos leaf", roughness=.69, texture=LEAF, double_sided=True)
    model.lathe(matte, ((0,0),(.051,0),(.053,.010),(.065,.093),(.066,.099),(.060,.100),
                       (.056,.087),(0,.087)), 12, "#C6876B")
    soil = [(0,.088,0)] + [(.054*math.cos(a),.088,.054*math.sin(a)) for a in np.linspace(0,2*math.pi,12,endpoint=False)]
    model.add(matte, soil, [(0,(i+1)%12+1,i+1) for i in range(12)], "#44362A")
    layout = (
        (15,.101,.163,.078,.038,.048,.016), (80,.083,.174,.109,.046,.051,.014),
        (147,.067,.196,.073,.037,.036,.024), (220,.071,.197,.097,.043,.040,.018),
        (281,.071,.156,.103,.039,.009,.046), (332,.089,.142,.096,.040,-.007,.046),
        (38,.144,.126,.082,.035,-.018,.045),
    )
    for i, (yaw, reach, y, length, width, rise, droop) in enumerate(layout):
        a = math.radians(yaw)
        fx, fz = math.cos(a), math.sin(a)
        start = (reach*.5*fx,y,reach*.5*fz)
        path = [(fx*.005,.088,fz*.005),(fx*reach*.21,y-.024,fz*reach*.21),start]
        # The cross section vector is horizontal and perpendicular to the plane of this branch.
        model.tube(matte, path, 3, .0026, "#69834C", np.array((-fz,0,fx)))
        pothos_blade(model, leaf, start, yaw, length, width, rise, droop, "#EDF3DF" if i % 2 else "#FFFFFF")
    return model


def fabric_shade(model, linen, base_y, top_y):
    n = 14
    profile = ((.115,base_y),(.114,base_y+.009),(.079,top_y-.006),(.078,top_y))
    vertices, uv = [], []
    for radius, y in profile:
        for i in range(n+1):
            angle = 2*math.pi*i/n
            vertices.append((radius*math.cos(angle),y,radius*math.sin(angle)))
            uv.append((3*i/n,1-(y-base_y)/(top_y-base_y)))
    model.add(linen, vertices, grid_faces(len(profile),n+1), uv=uv)


def table_lamp():
    model = Model("linen_table_lamp")
    glazed = model.material("Dressing glaze", roughness=.47)
    matte = model.material("Dressing matte")
    linen = model.material("Linen shade", roughness=.91, texture=LINEN, repeat=True, double_sided=True)
    model.lathe(glazed, ((0,0),(.051,0),(.060,.012),(.063,.043),(.052,.090),(.032,.128),
                         (.015,.140),(0,.140)), 12, "#69827C")
    model.lathe(matte, ((.008,.135),(.008,.230)), 8, "#655747")
    model.lathe(matte, ((0,.215),(.010,.223),(.018,.245),(.017,.267),(0,.274)), 8, "#E9DBB7")
    fabric_shade(model, linen, .185, .350)
    return model


ASSETS = [
    (coffee_table, "Table basse en noyer", "Devant le canapé. Le plateau accueille le livre, les revues et la télécommande du premier lot.",
     {"top_center": [0,.432,0]}),
    (media_console, "Meuble TV en noyer", "Le long d’un mur, façade vers le salon. Poser le téléviseur au point d’ancrage indiqué.",
     {"tv_seat": [0,.565,0]}),
    (television, "Téléviseur", "Centrer sur le meuble TV. L’écran éteint est orienté vers l’avant, en +Z.",
     {"foot_center": [0,0,0]}),
    (tabletop_pothos, "Petit pothos en pot", "Sur une table basse, un guéridon ou un meuble haut. Orienter les feuilles retombantes vers le côté visible.",
     {"pot_base": [0,0,0]}),
    (table_lamp, "Lampe à poser en lin", "Sur un guéridon, un chevet ou le meuble TV. Le modèle inclut le pied, l’abat-jour et l’ampoule.",
     {"base_center": [0,0,0], "bulb_center": [0,.244,0]}),
]


def main():
    assets = []
    for maker, name, placement, anchors in ASSETS:
        model = maker()
        assets.append({"id": model.name, "name_fr": name, "file": f"{model.name}.glb",
                       "placement_fr": placement, "pivot": "contact inférieur, Y vers le haut",
                       "anchors_local_m": anchors, "textures": [m[2] for m in model.materials.values() if m[2]],
                       **model.save(DESTINATION)})
    inventory = {
        "project": "Out of Sight / games/out_of_sight",
        "format": "GLB 2.0 autonome, mètres, Y vers le haut, façade +Z",
        "integration_fr": [
            "Importer les modèles à l’échelle 1. Pour l’ensemble TV, aligner le pied du téléviseur sur l’ancre tv_seat.",
            "Le noyer est partagé. Utiliser un matériau commun dans Unity si les deux meubles cohabitent.",
            "Les GLB embarquent les albédo et les matériaux PBR. Les PNG séparés servent à les retoucher.",
            "Les matériaux unis utilisent COLOR_0. La lampe est livrée comme objet visuel avec une ancre bulb_center.",
        ],
        "imagegen": {
            WOOD: "Albédo répétable de placage de noyer, grain horizontal et éclairage neutre.",
            LEAF: "Albédo UV d’une feuille de pothos, nervure centrale et marbrures olive, plein cadre.",
            LINEN: "Albédo répétable de lin ivoire, trame fine et teinte uniforme.",
        },
        "props": assets,
    }
    (DESTINATION / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in assets:
        print(f"{item['file']}: {item['triangles']} tris, {item['material_slots']} materials")


if __name__ == "__main__":
    main()
