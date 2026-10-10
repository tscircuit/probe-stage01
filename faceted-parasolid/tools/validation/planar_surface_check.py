"""Compare complete planar surface regions with independently read-back OCCT.

Every input triangle and every OCCT face participates. Each supporting plane's
source triangles and OCCT face loops are projected into the same orthonormal
coordinates, unioned, and compared as regions. The 1e-7 mm GEOS precision grid
limits floating-point seam noise; it is 100 times smaller than the allowed
surface-region distance. No B-Rep healing or source exporter code is used.
"""

import argparse
import itertools
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import shapely
from shapely.geometry import Polygon


SURFACE_REGION_TOLERANCE_MM = 1e-5
PLANE_OFFSET_TOLERANCE_MM = 1e-6
NORMAL_TOLERANCE = 1e-8
PRECISION_GRID_MM = 1e-7


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if not math.isfinite(length) or length <= 0:
        raise ValueError("Non-finite or degenerate supporting plane")
    return tuple(x / length for x in a)


def _plane(normal, point):
    normal = _unit(normal)
    # First substantial component gives a stable orientation for opposite
    # source/native normals, including planes with equal dominant components.
    if next(x for x in normal if abs(x) > 1e-6) < 0:
        normal = tuple(-x for x in normal)
    return normal, _dot(normal, point)


class _PlaneGroups:
    def __init__(self):
        self.groups = []
        self.bins = defaultdict(list)

    @staticmethod
    def key(normal, offset):
        return tuple(math.floor(x / NORMAL_TOLERANCE) for x in normal) + (
            math.floor(offset / PLANE_OFFSET_TOLERANCE_MM),)

    def find(self, normal, offset, create=False):
        key = self.key(normal, offset)
        for delta in itertools.product((-1, 0, 1), repeat=4):
            neighbor = tuple(x + d for x, d in zip(key, delta, strict=True))
            for index in self.bins.get(neighbor, ()):
                group = self.groups[index]
                normal_difference = math.sqrt(_dot(_sub(normal, group["normal"]),
                                                   _sub(normal, group["normal"])))
                offset_difference = abs(offset - group["offset"])
                if (normal_difference <= NORMAL_TOLERANCE
                        and offset_difference <= PLANE_OFFSET_TOLERANCE_MM):
                    group["max_normal_difference"] = max(group["max_normal_difference"], normal_difference)
                    group["max_plane_offset_mm"] = max(group["max_plane_offset_mm"], offset_difference)
                    return group
        if not create:
            raise ValueError("Read-back face has no matching source supporting plane")
        least = min(range(3), key=lambda i: abs(normal[i]))
        axis = tuple(float(i == least) for i in range(3))
        u = _unit(_cross(normal, axis))
        v = _cross(normal, u)
        group = {"normal": normal, "offset": offset,
                 "origin": tuple(offset * x for x in normal), "u": u, "v": v,
                 "source": [], "actual": [], "source_triangles": 0,
                 "actual_faces": 0, "max_normal_difference": 0.0,
                 "max_plane_offset_mm": 0.0}
        self.bins[key].append(len(self.groups))
        self.groups.append(group)
        return group


def _project(points, group):
    result = []
    for point in points:
        if len(point) != 3 or not all(math.isfinite(x) for x in point):
            raise ValueError("Surface region contains a non-finite point")
        local = _sub(point, group["origin"])
        residual = abs(_dot(local, group["normal"]))
        if residual > PLANE_OFFSET_TOLERANCE_MM:
            raise ValueError(f"Surface point is {residual:g} mm off its matched plane")
        result.append((_dot(local, group["u"]), _dot(local, group["v"])))
    return result


def _polygon(points, group, holes=()):
    polygon = Polygon(_project(points, group), [_project(ring, group) for ring in holes])
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
        raise ValueError("Invalid or empty projected planar surface region")
    # Precision reduction must not silently omit a thin source/native region.
    if shapely.set_precision(polygon, PRECISION_GRID_MM).is_empty:
        raise ValueError("Planar region collapses below the comparison precision grid")
    return polygon


def _occt_faces(converted):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    shape = converted.shape
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    for i in range(1, faces.Extent() + 1):
        yield TopoDS.Face_s(faces.FindKey(i))


def _face_loops(face):
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    outer = BRepTools.OuterWire_s(face)
    if outer.IsNull():
        raise ValueError("Independent OCCT planar face has no outer wire")
    wires = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(face, TopAbs_WIRE, wires)
    result = []
    for i in range(1, wires.Extent() + 1):
        wire = TopoDS.Wire_s(wires.FindKey(i))
        expected = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(wire, TopAbs_EDGE, expected)
        walker = BRepTools_WireExplorer(wire, face)
        points = []
        count = 0
        while walker.More():
            edge = walker.Current()
            if BRepAdaptor_Curve(edge).GetType() != GeomAbs_Line:
                raise ValueError("Expected only independently reconstructed straight face edges")
            point = BRep_Tool.Pnt_s(walker.CurrentVertex())
            points.append((point.X(), point.Y(), point.Z()))
            count += 1
            walker.Next()
        if count != expected.Extent() or count < 3:
            raise ValueError("OCCT ordered wire walk omitted edges or cannot bound a region")
        result.append((wire.IsSame(outer), points))
    outers = [points for is_outer, points in result if is_outer]
    if len(outers) != 1:
        raise ValueError("Independent OCCT face must have exactly one recognized outer loop")
    return outers[0], [points for is_outer, points in result if not is_outer]


def compare_surfaces(mesh_path, converted):
    """Return a JSON-safe whole-surface report; raise on any mismatch."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    start = time.perf_counter()
    source = json.loads(Path(mesh_path).read_text())
    if source.get("units") != "mm":
        raise ValueError("Source mesh surface comparison requires mm")
    vertices = source["vertices"]
    triangles = source["triangles"]
    if not triangles:
        raise ValueError("Source mesh has no surface triangles")
    planes = _PlaneGroups()
    for triangle in triangles:
        if len(triangle) != 3:
            raise ValueError("Source mesh must contain complete triangles")
        points = [vertices[i] for i in triangle]
        normal, offset = _plane(_cross(_sub(points[1], points[0]), _sub(points[2], points[0])), points[0])
        group = planes.find(normal, offset, create=True)
        group["source"].append(_polygon(points, group))
        group["source_triangles"] += 1
    face_count = 0
    for face in _occt_faces(converted):
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() != GeomAbs_Plane:
            raise ValueError("Native X_T read-back contains a non-planar face")
        plane = adaptor.Plane()
        direction, location = plane.Axis().Direction(), plane.Location()
        normal, offset = _plane((direction.X(), direction.Y(), direction.Z()),
                                (location.X(), location.Y(), location.Z()))
        group = planes.find(normal, offset)
        outer, holes = _face_loops(face)
        group["actual"].append(_polygon(outer, group, holes))
        group["actual_faces"] += 1
        face_count += 1
    if not face_count:
        raise ValueError("Native X_T read-back has no complete planar faces")
    max_distance = max_difference = total_difference = 0.0
    max_area_limit = 0.0
    for index, group in enumerate(planes.groups):
        if not group["actual"]:
            raise ValueError(f"Native X_T is missing source supporting plane {index}")
        original = shapely.union_all(group["source"], grid_size=PRECISION_GRID_MM)
        actual = shapely.union_all(group["actual"], grid_size=PRECISION_GRID_MM)
        if not original.is_valid or not actual.is_valid or original.is_empty or actual.is_empty:
            raise ValueError("Projected union is invalid or empty")
        difference = original.symmetric_difference(actual).area
        # Area tolerance scales with boundary length, corresponding to a narrow
        # region strip within 1e-6 mm, and remains below boundary-distance limit.
        area_limit = max(1e-8, (original.length + actual.length) * 1e-6)
        distance = original.boundary.hausdorff_distance(actual.boundary)
        if not math.isfinite(difference) or not math.isfinite(distance):
            raise ValueError("Projected surface comparison produced non-finite metrics")
        if difference > area_limit:
            raise ValueError(f"Planar surface region {index} differs: symmetric_difference={difference:g} mm2 "
                             f"(limit {area_limit:g}); boundary_distance={distance:g} mm")
        # Every point of both full SURFACE REGIONS must be inside a tolerance
        # neighborhood of its counterpart. Compare regions, rather than trim
        # boundaries: numerical T-junction seams in the source union can create
        # long internal boundaries despite a vanishingly small area difference.
        # No source triangles or native faces are removed, and neither original
        # region is buffered/closed before computing symmetric difference.
        # Round buffer arcs are inscribed, making coverage conservative.
        for left, right in ((original, actual), (actual, original)):
            left = shapely.set_precision(left, 0)
            right = shapely.set_precision(right, 0)
            tube = right.buffer(SURFACE_REGION_TOLERANCE_MM, quad_segs=8)
            outside = left.difference(tube)
            if not outside.is_empty:
                raise ValueError(f"Complete planar surface region {index} exceeds the tolerance neighborhood: "
                                 f"outside_area={outside.area:g} mm2; bounds={outside.bounds}; "
                                 f"discrete_hausdorff={distance:g} mm")
        max_distance = max(max_distance, distance)
        max_difference = max(max_difference, difference)
        total_difference += difference
        max_area_limit = max(max_area_limit, area_limit)
    return {"valid": True, "method": "whole supporting-plane region union area and reciprocal region coverage",
            "source_triangles": len(triangles), "readback_faces": face_count,
            "supporting_plane_groups": len(planes.groups), "all_source_triangles_compared": True,
            "all_readback_faces_compared": True,
            "precision_grid_mm": PRECISION_GRID_MM, "max_boundary_hausdorff_mm": max_distance,
            "hausdorff_reporting": "boundary Hausdorff is a discrete diagnostic; internal source tessellation seams can increase it",
            "complete_bidirectional_surface_region_coverage": True,
            "surface_region_hausdorff_upper_bound_mm": SURFACE_REGION_TOLERANCE_MM,
            "surface_region_tolerance_mm": SURFACE_REGION_TOLERANCE_MM,
            "max_symmetric_difference_area_mm2": max_difference,
            "total_symmetric_difference_area_mm2": total_difference,
            "max_allowed_symmetric_difference_area_mm2": max_area_limit,
            "symmetric_difference_area_tolerance_rule": "max(1e-8 mm2, (source_perimeter+readback_perimeter)*1e-6 mm)",
            "max_plane_offset_mm": max(g["max_plane_offset_mm"] for g in planes.groups),
            "max_normal_difference": max(g["max_normal_difference"] for g in planes.groups),
            "plane_offset_tolerance_mm": PLANE_OFFSET_TOLERANCE_MM,
            "normal_tolerance": NORMAL_TOLERANCE, "seconds": time.perf_counter() - start,
            "shapely_version": shapely.__version__}


def main():
    from parasolid_kit import read_brep
    from parasolid_kit.interop.occt import to_occt

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh", type=Path)
    parser.add_argument("xt", type=Path)
    args = parser.parse_args()
    parsed = read_brep(args.xt)
    if not parsed.complete:
        raise ValueError("Independent native X_T parse is incomplete")
    converted = to_occt(parsed.brep, source_unit="m", target_unit="mm", require_complete=True, heal=False)
    print(json.dumps(compare_surfaces(args.mesh, converted), indent=2))


if __name__ == "__main__":
    main()
