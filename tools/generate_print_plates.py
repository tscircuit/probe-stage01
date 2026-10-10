#!/usr/bin/env python3
"""Create vendor-neutral, printable-only Core 3MF plates from frozen STL exports.

Usage: python generate_print_plates.py --repo /path/to/probe-stage01 --output ./print-plates
Requires numpy and scipy. Meshes retain all original triangles; only rigid motions
and exact coordinate deduplication are applied. Hardware is never included.
Defaults to v2, v3 and v4; explicitly selecting v1 writes its unsupported-source
diagnostic without creating a 3MF, because the frozen frame STL is non-manifold.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from scipy.spatial import ConvexHull

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
PRINTABLES = ["frame_front_clamp", "rear_clamp", "front_axle_bridge", "sector_crank",
              "motor_pinion", "connecting_rod", "probe_carriage"]
MARGIN = 5.0
GAP = 5.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_stl(path):
    raw = Path(path).read_bytes()
    count = struct.unpack_from("<I", raw, 80)[0]
    if len(raw) != 84 + count * 50:
        raise ValueError(f"Not an exact binary STL: {path}")
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    return np.frombuffer(raw, dtype=dtype, count=count, offset=84)["vertices"].astype(np.float64)


def rotation(axis, degrees):
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


def initial_orientation(version, name):
    # Frozen v2 faces lie in YZ rather than XY. The other releases lie in XY.
    # Positive axial faces down give the broad, flat contact faces of the rods,
    # pinions/carriages. Frame and gear retain their integral bosses and braces.
    if name == "rear_clamp":
        return rotation("x", 90), "flat clamp end face; original -Y faces bed"
    if name == "front_axle_bridge":
        return (rotation("y", -90), "flat bridge face; original -X faces bed") if version == "v2" else (np.eye(3), "flat bridge face; original -Z faces bed")
    if name == "probe_carriage":
        return (rotation("y", 90), "broad carriage end face; original +X faces bed") if version == "v2" else (rotation("x", 180), "broad carriage end face; original +Z faces bed")
    return (rotation("y", 90), "drive plane horizontal; original +X faces bed") if version == "v2" else (rotation("x", 180), "drive plane horizontal; original +Z faces bed")


def area_normals(triangles):
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return np.linalg.norm(cross, axis=1) / 2


def volume(triangles):
    # Subtracting one point keeps translations from degrading the accumulation.
    p = triangles - triangles[0, 0]
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6)


def convex_hull(points):
    points = np.unique(points, axis=0)
    return points[ConvexHull(points).vertices]


def sat_clear(a, b, gap=GAP):
    """Conservative separation: disjoint convex hulls with >=gap along a unit axis.

    Every projected triangle is contained in its convex hull. A separating axis
    with this distance therefore proves all XY mesh projections are at least
    gap apart; it also proves no solid intersections at any Z.
    """
    for polygon in (a, b):
        edges = np.roll(polygon, -1, axis=0) - polygon
        axes = np.column_stack((-edges[:, 1], edges[:, 0]))
        axes /= np.linalg.norm(axes, axis=1)[:, None]
        pa, pb = a @ axes.T, b @ axes.T
        separated = np.maximum(pb.min(0) - pa.max(0), pa.min(0) - pb.max(0))
        if float(separated.max()) >= gap - 1e-8:
            return True
    return False


def separation_bound(a, b):
    best = -float("inf")
    for polygon in (a, b):
        edges = np.roll(polygon, -1, axis=0) - polygon
        axes = np.column_stack((-edges[:, 1], edges[:, 0]))
        axes /= np.linalg.norm(axes, axis=1)[:, None]
        pa, pb = a @ axes.T, b @ axes.T
        best = max(best, float(np.maximum(pb.min(0) - pa.max(0), pa.min(0) - pb.max(0)).max()))
    return best


def place_parts(parts, bed):
    # Place the largest frame first, then large flat pieces. A coarse 2 mm search
    # and convex-hull separation can use free corners while keeping 5 mm clearance.
    order = sorted(parts, key=lambda p: float(np.prod(np.ptp(p["base"][:, :, :2].reshape(-1, 2), axis=0))), reverse=True)
    placed = []
    for part in order:
        options = []
        for angle in (0, 90, 180, 270):
            rz = rotation("z", angle)
            tri = part["base"] @ rz.T
            minimum = tri.reshape(-1, 3).min(0)
            tri -= minimum
            hull = convex_hull(tri[:, :, :2].reshape(-1, 2))
            ext = np.ptp(tri.reshape(-1, 3), axis=0)
            if ext[0] + 2 * MARGIN > bed or ext[1] + 2 * MARGIN > bed:
                continue
            max_x = bed - MARGIN - ext[0]
            max_y = bed - MARGIN - ext[1]
            positions = [(float(x), float(y)) for y in np.arange(MARGIN, max_y + 1e-7, 2.0) for x in np.arange(MARGIN, max_x + 1e-7, 2.0)]
            # Choose compact lower-left placement first. Since pieces can use the
            # corners outside prior hulls, bounding boxes may legitimately overlap.
            positions.sort(key=lambda xy: (max(xy[0] + ext[0], xy[1] + ext[1]), xy[0] + xy[1], xy[1], xy[0]))
            for x, y in positions:
                shifted = hull + [x, y]
                if all(sat_clear(shifted, other["hull"]) for other in placed):
                    options.append((max(x + ext[0], y + ext[1]), x + y, angle, x, y, tri, shifted, rz, minimum))
                    break
        if not options:
            return None
        options.sort(key=lambda row: row[:5])
        _, _, angle, x, y, tri, hull, rz, minimum = options[0]
        R = rz @ part["rotation"]
        # base coordinates already include the source rotation, without translation.
        translation = np.array([x, y, 0.0]) - minimum
        transformed = tri + [x, y, 0.0]
        placed.append({**part, "triangles": transformed, "hull": hull, "plate_rotation": R,
                       "plate_translation": translation, "in_plane_rotation_deg": angle})
    return placed


def index_mesh(triangles):
    # Deduplication changes the storage representation only, preserving every
    # source facet in original order and all source Float32 coordinates exactly.
    vertices, inverse = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
    return vertices, inverse.reshape(-1, 3)


def topology(vertices, triangles):
    edges = Counter()
    incidence = defaultdict(list)
    for i, face in enumerate(triangles):
        for a, b in zip(face, np.roll(face, -1)):
            edges[(int(a), int(b))] += 1
            incidence[tuple(sorted((int(a), int(b))))].append(i)
    closed = all(len(faces) == 2 for faces in incidence.values())
    oriented = all(edges[(a, b)] == edges[(b, a)] == 1 for a, b in incidence)
    adjacency = [[] for _ in triangles]
    for faces in incidence.values():
        if len(faces) == 2:
            adjacency[faces[0]].append(faces[1]); adjacency[faces[1]].append(faces[0])
    seen = set()
    components = 0
    for start in range(len(triangles)):
        if start in seen:
            continue
        components += 1
        todo = [start]; seen.add(start)
        while todo:
            for nxt in adjacency[todo.pop()]:
                if nxt not in seen:
                    seen.add(nxt); todo.append(nxt)
    return {"closed_two_manifold_edges": closed, "consistent_outward_winding": oriented,
            "connected_components": components, "vertex_count": len(vertices), "edge_count": len(incidence)}


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_3mf(path, version, source_sha, placed):
    ET.register_namespace("", CORE)
    model = ET.Element(f"{{{CORE}}}model", {"unit": "millimeter", "{http://www.w3.org/XML/1998/namespace}lang": "en-US"})
    for name, value in (("Title", f"Probe stage {version} printable build plate"),
                        ("Description", f"Frozen {version} build123d source SHA256: {source_sha}. Seven fabricated polymer parts only. No bolts, nuts, bearings, motor, probe, reference geometry, or hardware spacers. Supports and printer settings must be selected in your slicer."),
                        ("Application", "build123d probe-stage01 printable-only Core 3MF exporter"),
                        ("Designer", "tscircuit/probe-stage01")):
        ET.SubElement(model, f"{{{CORE}}}metadata", {"name": name}).text = value
    resources = ET.SubElement(model, f"{{{CORE}}}resources")
    build = ET.SubElement(model, f"{{{CORE}}}build")
    for object_id, part in enumerate(sorted(placed, key=lambda p: PRINTABLES.index(p["name"])), 1):
        obj = ET.SubElement(resources, f"{{{CORE}}}object", {"id": str(object_id), "type": "model", "name": part["name"], "partnumber": f"{version}:{part['name']}"})
        mesh = ET.SubElement(obj, f"{{{CORE}}}mesh")
        vertices, indices = index_mesh(part["triangles"])
        vv = ET.SubElement(mesh, f"{{{CORE}}}vertices")
        for point in vertices:
            ET.SubElement(vv, f"{{{CORE}}}vertex", {axis: format(float(value), ".17g") for axis, value in zip("xyz", point)})
        tt = ET.SubElement(mesh, f"{{{CORE}}}triangles")
        for face in indices:
            ET.SubElement(tt, f"{{{CORE}}}triangle", {f"v{i+1}": str(int(value)) for i, value in enumerate(face)})
        ET.SubElement(build, f"{{{CORE}}}item", {"objectid": str(object_id)})
    # Additional JSON metadata is an OPC noncritical sidecar, avoiding custom Core
    # attributes or a required extension that a slicer might reject.
    metadata = {"public_version": version, "source_sha256": source_sha, "included_names": PRINTABLES,
                "hardware_included": False, "plate_coordinate_units": "mm"}
    content_types = ET.Element(f"{{{TYPES}}}Types")
    ET.SubElement(content_types, f"{{{TYPES}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(content_types, f"{{{TYPES}}}Default", {"Extension": "model", "ContentType": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"})
    ET.SubElement(content_types, f"{{{TYPES}}}Default", {"Extension": "json", "ContentType": "application/json"})
    rels = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(rels, f"{{{REL}}}Relationship", {"Target": "/3D/3dmodel.model", "Id": "rel0", "Type": "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in [("[Content_Types].xml", xml_bytes(content_types)), ("_rels/.rels", xml_bytes(rels)),
                           ("3D/3dmodel.model", xml_bytes(model)), ("Metadata/source.json", json.dumps(metadata, indent=2).encode() + b"\n")]:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def validate_archive(path, placed, version, source_sha):
    rows = []
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        meta = json.loads(z.read("Metadata/source.json"))
        assert meta["source_sha256"] == source_sha and meta["hardware_included"] is False
        assert model.attrib["unit"] == "millimeter"
        objects = model.findall(f"{{{CORE}}}resources/{{{CORE}}}object")
        build = model.findall(f"{{{CORE}}}build/{{{CORE}}}item")
        assert len(objects) == len(build) == 7
        expected = {p["name"]: p for p in placed}
        assert {o.attrib["name"] for o in objects} == set(PRINTABLES)
        assert {b.attrib["objectid"] for b in build} == {o.attrib["id"] for o in objects}
        for obj in objects:
            part = expected[obj.attrib["name"]]
            verts = np.array([[float(v.attrib[x]) for x in "xyz"] for v in obj.findall(f"{{{CORE}}}mesh/{{{CORE}}}vertices/{{{CORE}}}vertex")])
            faces = np.array([[int(v.attrib[x]) for x in ("v1", "v2", "v3")] for v in obj.findall(f"{{{CORE}}}mesh/{{{CORE}}}triangles/{{{CORE}}}triangle")])
            tri = verts[faces]
            actual_expected = part["source"] @ part["plate_rotation"].T + part["plate_translation"]
            err = float(np.abs(tri - actual_expected).max())
            source_volume, plate_volume = volume(part["source"]), volume(tri)
            geom = topology(verts, faces)
            sv, sf = index_mesh(part["source"])
            source_geom = topology(sv, sf)
            bounds = [verts.min(0).tolist(), verts.max(0).tolist()]
            areas = area_normals(tri)
            bed_faces = np.max(np.abs(tri[:, :, 2]), axis=1) < 1e-6
            rigid = part["plate_rotation"]
            assert err < 1e-8 and abs(plate_volume - source_volume) < 1e-6
            assert len(faces) == len(part["source"]) and float(areas.min()) > 0
            assert plate_volume > 0 and geom == source_geom and geom["connected_components"] == 1
            assert geom["closed_two_manifold_edges"] and geom["consistent_outward_winding"], "Non-manifold source mesh cannot be exported"
            assert abs(bounds[0][2]) < 1e-8 and np.allclose(rigid.T @ rigid, np.eye(3), atol=1e-10) and abs(np.linalg.det(rigid) - 1) < 1e-10
            rows.append({"name": part["name"], "source_stl_sha256": sha(part["stl"]), "triangle_count": len(faces),
                         "source_volume_mm3": source_volume, "plate_volume_mm3": plate_volume,
                         "absolute_volume_error_mm3": abs(plate_volume - source_volume), "source_rigid_equivalence_max_coordinate_error_mm": err,
                         "rigid_rotation_source_to_plate": rigid.tolist(), "rigid_translation_source_to_plate_mm": part["plate_translation"].tolist(),
                         "rotation_determinant": float(np.linalg.det(rigid)), "bounds_mm": {"min": bounds[0], "max": bounds[1]},
                         "minimum_triangle_area_mm2": float(areas.min()), "bed_contact_area_mm2": float(areas[bed_faces].sum()),
                         "orientation": part["orientation"], "in_plane_rotation_deg": part["in_plane_rotation_deg"], **geom,
                         "source_topology_unchanged": True, "source_topology": source_geom, "validated": True})
    pairs = []
    for i, p in enumerate(placed):
        for q in placed[i+1:]:
            bound = separation_bound(p["hull"], q["hull"])
            assert bound >= GAP - 1e-8
            pairs.append({"parts": [p["name"], q["name"]], "projected_convex_hull_separating_axis_gap_mm": bound, "clear": True})
    points = np.concatenate([p["triangles"].reshape(-1, 3) for p in placed])
    return rows, pairs, points.min(0).tolist(), points.max(0).tolist()


def generate(repo, output, version):
    site = repo / "versions" / version / "site"
    manifest = json.loads((site / "assets/manifest.json").read_text())
    model = json.loads((site / "assets/model.json").read_text())
    names = model["meta"]["printable"]
    assert names == PRINTABLES and manifest["printable_count"] == 7
    fabricated = {n for n, p in manifest["parts"].items() if p["category"] == "Fabricated parts"}
    assert fabricated == set(names)
    assert {p.stem for p in (site / "downloads/parts").glob("*.stl")} == set(names)
    excluded = [{"name": n, "category": p["category"]} for n, p in manifest["parts"].items() if n not in names]
    assert len(excluded) == 41
    parts = []
    source_checks = []
    for name in names:
        stl = site / "downloads/parts" / f"{name}.stl"
        source = read_stl(stl)
        R, orientation = initial_orientation(version, name)
        parts.append({"name": name, "source": source, "base": source @ R.T,
                      "rotation": R, "orientation": orientation, "stl": stl})
        vertices, faces = index_mesh(source)
        source_checks.append({"name": name, "source_stl_sha256": sha(stl), "triangle_count": len(source),
                              "source_volume_mm3": volume(source), **topology(vertices, faces)})
    nonmanifold_sources = [row["name"] for row in source_checks if not (row["closed_two_manifold_edges"] and row["consistent_outward_winding"])]
    if nonmanifold_sources:
        # Do not silently repair immutable STL sources, or present an invalid mesh
        # as a printable download. Preserve the diagnostic outside the addons.
        diagnostics = output.parent / "source_inventory"
        diagnostics.mkdir(parents=True, exist_ok=True)
        report = {"public_version": version, "source_sha256": manifest["source_sha256"],
                  "complete": True, "export_available": False, "included_names": names,
                  "excluded_components": excluded, "parts": source_checks,
                  "source_nonmanifold_meshes": nonmanifold_sources,
                  "unsupported_reason": "The frozen frame STL has pre-existing T-junction/non-manifold edges. A strict printable 3MF cannot be made without changing its source triangulation; the frozen version remains unchanged. Use the v2 or v3 print plate."}
        (diagnostics / f"{version}.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{version}: no 3MF exported; non-manifold frozen source mesh: {', '.join(nonmanifold_sources)}", flush=True)
        return None, None
    attempted = []
    for bed in (256, 300, 350, 400, 450, 500):
        began = time.monotonic()
        placed = place_parts(parts, bed)
        attempted.append({"plate_mm": [bed, bed], "packed": placed is not None})
        print(f"{version}: {bed} mm plate {'fits' if placed else 'did not fit'} ({time.monotonic()-began:.1f}s)", flush=True)
        if placed:
            break
    assert placed is not None
    target = output / version; target.mkdir(parents=True, exist_ok=True)
    filename = f"probe-stage-{version}-print-plate.3mf"
    archive = target / filename
    source_sha = manifest["source_sha256"]
    build_3mf(archive, version, source_sha, placed)
    rows, pairs, minimum, maximum = validate_archive(archive, placed, version, source_sha)
    assert minimum[0] >= MARGIN-1e-8 and minimum[1] >= MARGIN-1e-8 and maximum[0] <= bed-MARGIN+1e-8 and maximum[1] <= bed-MARGIN+1e-8
    notes = ["Includes the seven fabricated polymer parts only; all 41 hardware/reference components are excluded.",
             "Meshes are unchanged from the frozen STL files except for rigid rotation and translation; dimensions are in millimeters.",
             "At least 5 mm bed-edge margin and 5 mm clearance between projected convex hulls; seven separate named build objects.",
             "Generic Core 3MF geometry; select your printer, material, supports, infill, layer height and adhesion in your slicer.",
             "Integral frame braces, clamp projections, bearing bosses and angled probe-holder features can require supports. This is not a support-free or pre-sliced print project."]
    nonmanifold = [row["name"] for row in rows if not (row["closed_two_manifold_edges"] and row["consistent_outward_winding"])]
    if nonmanifold:
        notes.append("Frozen v1 frame STL has pre-existing T-junction/non-manifold edges. These are preserved without repair; a strict mesh reader can flag that one object. Use v2 or v3 for fully closed manifold plate meshes.")
    report = {"public_version": version, "source_sha256": source_sha, "complete": True, "validated": True,
              "format": "3MF Core 2015/02, OPC ZIP", "units": "mm", "object_count": 7, "build_item_count": 7,
              "included_names": names, "excluded_components": excluded, "hardware_included": False,
              "reference_envelopes_included": False, "vendor_printer_settings_included": False,
              "all_meshes_manifold_and_oriented": not nonmanifold, "source_nonmanifold_meshes_preserved": nonmanifold,
              "plate_mm": [bed, bed], "packed_extents_mm": [maximum[i]-minimum[i] for i in range(3)],
              "build_bounds_mm": {"min": minimum, "max": maximum}, "edge_margin_mm": MARGIN,
              "minimum_projected_convex_hull_clearance_mm": min(p["projected_convex_hull_separating_axis_gap_mm"] for p in pairs),
              "separation_method": "Conservative XY convex-hull separating axes with 5 mm gap; all projected source triangles are inside their respective hulls.",
              "packing_attempts": attempted, "parts": rows, "part_pairs": pairs, "notes": notes}
    (target / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    public_manifest = {"public_version": version, "source_sha256": source_sha, "format": "3MF", "file": filename,
                       "sha256": sha(archive), "bytes": archive.stat().st_size, "names": names, "object_count": 7,
                       "plate_mm": [bed, bed], "packed_extents_mm": report["packed_extents_mm"], "hardware_included": False,
                       "all_meshes_manifold_and_oriented": not nonmanifold,
                       "report": "validation.json", "report_sha256": sha(target / "validation.json"), "notes": notes}
    (target / "manifest.json").write_text(json.dumps(public_manifest, indent=2) + "\n")
    return placed, bed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--versions", nargs="+", default=["v2", "v3", "v4"])
    args = ap.parse_args()
    for version in args.versions:
        generate(args.repo, args.output, version)


if __name__ == "__main__":
    main()
