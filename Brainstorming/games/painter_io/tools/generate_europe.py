"""Generate playable European outlines and a triangulated atlas from Natural Earth."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape
from shapely.geometry.polygon import orient
from shapely.ops import transform


NAMES = {
    "AD": "Andorre", "AL": "Albanie", "AT": "Autriche",
    "BA": "Bosnie-Herzégovine", "BE": "Belgique", "BG": "Bulgarie",
    "BY": "Biélorussie", "CH": "Suisse", "CY": "Chypre",
    "CZ": "Tchéquie", "DE": "Allemagne", "DK": "Danemark",
    "EE": "Estonie", "ES": "Espagne", "FI": "Finlande", "FR": "France",
    "GB": "Royaume-Uni", "GR": "Grèce", "HR": "Croatie", "HU": "Hongrie",
    "IE": "Irlande", "IS": "Islande", "IT": "Italie", "LI": "Liechtenstein",
    "LT": "Lituanie", "LU": "Luxembourg", "LV": "Lettonie",
    "MC": "Monaco", "MD": "Moldavie", "ME": "Monténégro",
    "MK": "Macédoine du Nord", "MT": "Malte", "NL": "Pays-Bas",
    "NO": "Norvège", "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie",
    "RS": "Serbie", "SE": "Suède", "SI": "Slovénie", "SK": "Slovaquie",
    "SM": "Saint-Marin", "TR": "Turquie", "UA": "Ukraine",
    "VA": "Vatican", "XK": "Kosovo",
}
SOURCE_VERSION = "v5.1.2"
SOURCES = {
    "ne_10m_admin_0_map_units":
        "57da82be755f4afccd8f3b14251bb2752f5df1395f47d2d86f817470c4a48862",
    "ne_10m_admin_0_countries_ukr":
        "28a1a17d7327cad576083d5122b867843f957468b1bb11168ded23fd5aea342e",
}
ORIGIN = (4321000, 3000000)
MAP_GRID_KM = 0.001
ISLAND_MIN_KM2 = 20
LEVEL_MAX_VERTICES = 128
PROJECT = Path(__file__).resolve().parents[1]
PROJECTION = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def features(dataset, cache_dir):
    cache_path = cache_dir / f"painter-{dataset}_{SOURCE_VERSION}.geojson"
    if not cache_path.exists():
        url = (f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
               f"{SOURCE_VERSION}/geojson/{dataset}.geojson")
        with urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != SOURCES[dataset]:
            raise ValueError(f"Unexpected content from {url}")
        cache_path.write_bytes(data)
    data = cache_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCES[dataset]:
        raise ValueError(f"Unexpected content in {cache_path}")
    return json.loads(data)["features"]


def polygon_parts(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from polygon_parts(part)


def map_polygons(feature, code):
    for polygon in polygon_parts(shape(feature["geometry"])):
        # Natural Earth here groups the Iberian mainland, Balearics and
        # Canaries as Spain. Keep only mainland Spain and the Balearics.
        if code == "ES" and polygon.representative_point().y < 35.9:
            continue
        yield transform(project_xy, polygon)


def project_xy(x, y, z=None):
    east, north = PROJECTION.transform(x, y)
    return (np.asarray(east) - ORIGIN[0]) / 1000, (np.asarray(north) - ORIGIN[1]) / 1000


def load_atlas(cache_dir):
    groups = {code: [] for code in NAMES}
    for feature in features("ne_10m_admin_0_map_units", cache_dir):
        properties = feature["properties"]
        unit = properties["GU_A3"]
        code = properties["ISO_A2_EH"]
        if unit in {"CYP", "CYN", "CNM", "ESB", "WSB"}:
            code = "CY"
        elif unit == "ALD":
            code = "FI"
        if code not in NAMES or code == "UA":
            continue
        if code == "FR" and unit != "FXX":
            continue
        if code == "NO" and unit != "NOW":
            continue
        if code == "PT" and unit != "PRX":
            continue
        if code == "NL" and unit != "NLX":
            continue
        groups[code].extend(map_polygons(feature, code))
    # The map-units layer's default control boundaries assign Crimea to Russia.
    # The publisher's Ukraine variant includes Crimea in Ukraine's perimeter.
    for feature in features("ne_10m_admin_0_countries_ukr", cache_dir):
        if feature["properties"]["ADM0_A3"] == "UKR":
            groups["UA"].extend(map_polygons(feature, "UA"))
    countries = []
    for code, parts in groups.items():
        region = shapely.union_all([shapely.make_valid(part) for part in parts])
        region = shapely.set_precision(region, MAP_GRID_KM)
        by_area = sorted(polygon_parts(region), key=lambda part: -part.area)
        if not by_area:
            raise ValueError(f"No territory for {code}")
        countries.append(shapely.MultiPolygon([
            polygon for index, polygon in enumerate(by_area)
            if index == 0 or polygon.area >= ISLAND_MIN_KM2
        ]))
    return repair_coverage(countries)


def repair_coverage(countries):
    # A precision-grid union nodes common borders. Polygonize once and reassign
    # faces, so even near-identical upstream boundaries use exactly the same edge.
    boundaries = shapely.union_all([country.boundary for country in countries])
    faces = shapely.get_parts(shapely.polygonize(shapely.get_parts(boundaries)))
    tree = shapely.STRtree(countries)
    buckets = [[] for _ in countries]
    for face in faces:
        point = face.representative_point()
        hits = tree.query(point, predicate="within")
        if len(hits):
            if len(hits) > 1 and face.area > 0.05:
                codes = [list(NAMES)[i] for i in hits]
                raise ValueError(f"Unexpected atlas overlap {codes}, {face.area:.4f} km²")
            buckets[min(hits)].append(face)
    coverage = [shapely.union_all(bucket) for bucket in buckets]
    if not shapely.coverage_is_valid(coverage):
        raise ValueError("Country boundaries fail coverage validation")
    # Visvalingam–Whyatt simplifies a shared edge only once.
    simplified = shapely.coverage_simplify(coverage, 1.2)
    if not shapely.coverage_is_valid(simplified):
        raise ValueError("Simplification broke valid atlas topology")
    return simplified


def point(x, y, digits=6):
    return {"x": round(float(x), digits), "y": round(float(y), digits)}


def ring(coords):
    return [point(x, y, 3) for x, y in list(coords)[:-1]]


def mesh(polygon):
    polygon = orient(polygon)
    triangles = shapely.get_parts(shapely.constrained_delaunay_triangles(polygon))
    if not triangles.size or not np.isclose(sum(t.area for t in triangles), polygon.area,
                                             rtol=1e-9, atol=1e-7):
        raise ValueError("Triangulation does not cover the source polygon")
    vertices, indices, lookup = [], [], {}
    for triangle in triangles:
        for x, y in list(orient(triangle).exterior.coords)[:-1]:
            key = (x, y)
            if key not in lookup:
                lookup[key] = len(vertices)
                vertices.append(point(x, y, 3))
            indices.append(lookup[key])
    return {
        "outer": ring(polygon.exterior.coords),
        "holes": [{"points": ring(hole.coords)} for hole in polygon.interiors],
        "vertices": vertices,
        "triangles": indices,
    }


def level_shape(polygon):
    polygon = Polygon(polygon.exterior)
    left, bottom, right, top = polygon.bounds
    cx, cy = (left + right) / 2, (bottom + top) / 2
    scale = 2 / max(right - left, top - bottom)
    normalized = transform(lambda x, y, z=None: ((np.asarray(x) - cx) * scale,
                                                 (np.asarray(y) - cy) * scale), polygon)
    tolerance = 0.002
    level = normalized.simplify(tolerance, preserve_topology=True)
    while len(level.exterior.coords) - 1 > LEVEL_MAX_VERTICES:
        tolerance *= 1.25
        level = normalized.simplify(tolerance, preserve_topology=True)
    level = orient(level)
    center, edge = shapely.maximum_inscribed_circle(level, tolerance=0.001).coords
    if not level.is_valid or not level.contains(Point(center)) or level.area < .1:
        raise ValueError("Invalid level or starting point")
    return ([point(x, y) for x, y in list(level.exterior.coords)[:-1]],
            point(*center), Point(center).distance(Point(edge)))


def export(cache_dir, output):
    atlas = load_atlas(cache_dir)
    countries = []
    for (code, name), geometry in zip(NAMES.items(), atlas, strict=True):
        parts = sorted(polygon_parts(geometry), key=lambda part: -part.area)
        if not parts:
            raise ValueError(f"Lost country {code} during generalization")
        largest = parts[0]
        label = Point(shapely.maximum_inscribed_circle(largest, tolerance=0.05).coords[0])
        level, level_center, level_radius = level_shape(largest)
        countries.append({
            "code": code, "name": name, "parts": [mesh(part) for part in parts],
            "level": level, "levelCenter": level_center,
            "levelRadius": round(level_radius, 6), "label": point(label.x, label.y, 3),
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        '{\n"projection":"EPSG:3035 | km | origin (4321000, 3000000) m",\n'
        '"source":"Natural Earth 1:10m, vector v5.1.2, public domain",\n'
        '"countries":[\n'
        + ",\n".join(json.dumps(country, ensure_ascii=False, separators=(",", ":"))
                      for country in countries)
        + "\n]}\n",
        encoding="utf-8",
    )
    print(f"{len(countries)} pays, {sum(len(country['parts']) for country in countries)} "
          f"polygones cartographiques, {output.stat().st_size:,} octets")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=PROJECT / "Assets/Resources/Europe/countries.json")
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    export(args.cache_dir, args.output)
