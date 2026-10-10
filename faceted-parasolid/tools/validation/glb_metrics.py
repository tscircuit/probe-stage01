"""Audit the actual GLB triangle buffers independently of OCCT tessellation.

Coordinates are measured after scene transforms, in glTF meters, then reported
in millimeters. Topology is checked separately for each native body: coincident
or touching assembly parts must not be welded to one another. This verifier
supports the indexed, uncompressed GLB profile emitted by parasolid-kit.
"""

import json
import math
import struct
from collections import defaultdict


RELATIVE_TOLERANCE = 1e-5  # GLB positions use float32; OCCT uses float64.


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _length(a):
    return math.sqrt(_dot(a, a))


def _identity():
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _multiply(a, b):
    return [sum(a[k * 4 + row] * b[column * 4 + k] for k in range(4))
            for column in range(4) for row in range(4)]


def _node_matrix(node):
    if "matrix" in node:
        matrix = node["matrix"]
    else:
        # Current preview nodes use only translation and positive uniform scale.
        # Refuse an unexpected encoding rather than silently mismeasure a mesh.
        if "rotation" in node:
            raise ValueError("GLB mesh audit does not support quaternion nodes")
        matrix = _identity()
        for axis, scale in enumerate(node.get("scale", [1, 1, 1])):
            matrix[axis * 5] = scale
        matrix[12:15] = node.get("translation", [0, 0, 0])
    if (len(matrix) != 16 or not all(math.isfinite(x) for x in matrix)
            or [matrix[i] for i in (3, 7, 11, 15)] != [0, 0, 0, 1]):
        raise ValueError("GLB mesh audit requires a finite affine node matrix")
    return matrix


def _point(matrix, point):
    return tuple(1000 * (sum(matrix[c * 4 + r] * point[c] for c in range(3))
                         + matrix[12 + r]) for r in range(3))


def _normal(matrix, normal):
    columns = [matrix[c * 4:c * 4 + 3] for c in range(3)]
    cofactors = [_cross(columns[1], columns[2]),
                 _cross(columns[2], columns[0]),
                 _cross(columns[0], columns[1])]
    determinant = _dot(columns[0], cofactors[0])
    if determinant <= 0 or not math.isfinite(determinant):
        raise ValueError("GLB preview must use nonsingular, orientation-preserving nodes")
    return tuple(sum(cofactors[c][r] * normal[c] for c in range(3)) / determinant
                 for r in range(3))


def audit_glb_mesh(glb, manifest, occt_metrics):
    """Reject missing faces, broken topology, bad normals, and metric drift."""
    if len(glb) < 28 or struct.unpack_from("<4sII", glb)[0:2] != (b"glTF", 2):
        raise ValueError("Expected a GLB v2 file")
    json_length, chunk_type = struct.unpack_from("<II", glb, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError("Expected GLB JSON chunk")
    document = json.loads(glb[20:20 + json_length])
    binary_offset = 20 + json_length
    binary_length, chunk_type = struct.unpack_from("<II", glb, binary_offset)
    if chunk_type != 0x004E4942:
        raise ValueError("Expected GLB BIN chunk")
    binary = glb[binary_offset + 8:binary_offset + 8 + binary_length]

    def accessor(index):
        value = document["accessors"][index]
        if "sparse" in value or value.get("normalized", False):
            raise ValueError("Unsupported GLB accessor encoding in mesh audit")
        view = document["bufferViews"][value["bufferView"]]
        if view.get("buffer", 0) != 0:
            raise ValueError("GLB mesh audit requires one embedded buffer")
        formats = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}
        components = {"VEC3": 3, "SCALAR": 1}
        fmt = "<" + formats[value["componentType"]] * components[value["type"]]
        stride = view.get("byteStride", struct.calcsize(fmt))
        offset = view.get("byteOffset", 0) + value.get("byteOffset", 0)
        return [struct.unpack_from(fmt, binary, offset + i * stride)
                for i in range(value["count"])]

    owners = {}
    for primitive in manifest["primitives"]:
        if primitive["kind"] != "face":
            continue
        bodies = primitive["body_ids"]
        if len(bodies) != 1 or primitive["target_key"] in owners:
            raise ValueError("Each preview face must belong to exactly one native body")
        owners[primitive["target_key"]] = bodies[0]
    triangles = defaultdict(list)
    seen = set()

    def walk(index, parent, ancestors):
        if index in ancestors:
            raise ValueError("Cycle in GLB scene graph")
        node = document["nodes"][index]
        matrix = _multiply(parent, _node_matrix(node))
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    raise ValueError("Expected only triangle primitives in solid preview")
                target = primitive.get("extras", {}).get("targetKey")
                if target not in owners or target in seen:
                    raise ValueError("Unexpected or duplicated GLB face primitive")
                seen.add(target)
                points = [_point(matrix, p) for p in accessor(primitive["attributes"]["POSITION"])]
                normals = [_normal(matrix, n) for n in accessor(primitive["attributes"]["NORMAL"])]
                indices = [item[0] for item in accessor(primitive["indices"])]
                if len(indices) == 0 or len(indices) % 3 or len(normals) != len(points):
                    raise ValueError("Incomplete GLB triangle/normal buffers")
                for offset in range(0, len(indices), 3):
                    ids = indices[offset:offset + 3]
                    if any(i >= len(points) for i in ids):
                        raise ValueError("GLB triangle index is out of range")
                    triangle = [points[i] for i in ids]
                    direction = _cross(_sub(triangle[1], triangle[0]),
                                       _sub(triangle[2], triangle[0]))
                    magnitude = _length(direction)
                    if not math.isfinite(magnitude) or magnitude <= 0:
                        raise ValueError("Degenerate GLB triangle")
                    for i in ids:
                        size = _length(normals[i])
                        if (not math.isfinite(size) or size <= 0
                                or _dot(direction, normals[i]) / (magnitude * size) < 1 - 1e-5):
                            raise ValueError("GLB triangle normal disagrees with its winding")
                    triangles[owners[target]].append(triangle)
        for child in node.get("children", []):
            walk(child, matrix, ancestors | {index})

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(root, _identity(), set())
    if seen != set(owners):
        raise ValueError("GLB is missing native face primitives")
    if set(triangles) != {body["id"] for body in manifest["bodies"]}:
        raise ValueError("GLB is missing native solid bodies")

    bodies = []
    for body, faces in sorted(triangles.items()):
        edges = defaultdict(list)
        # A nearby origin avoids volume cancellation for translated small parts.
        origin = faces[0][0]
        areas, volumes = [], []
        for triangle in faces:
            a, b, c = triangle
            areas.append(_length(_cross(_sub(b, a), _sub(c, a))) / 2)
            volumes.append(_dot(_sub(a, origin), _cross(_sub(b, origin), _sub(c, origin))) / 6)
            for i in range(3):
                start, end = triangle[i], triangle[(i + 1) % 3]
                # Shared OCCT edges have identical float32 positions. Do not use
                # tolerance welding, which could conceal cracks in the GLB.
                key = tuple(sorted((start, end)))
                edges[key].append(1 if start < end else -1)
        if any(len(uses) != 2 for uses in edges.values()):
            raise ValueError(f"GLB body {body} has open or non-manifold triangle edges")
        if any(sum(uses) != 0 for uses in edges.values()):
            raise ValueError(f"GLB body {body} has inconsistent triangle edge winding")
        volume = math.fsum(volumes)
        if not math.isfinite(volume) or volume <= 0:
            raise ValueError(f"GLB body {body} has non-positive signed volume")
        bodies.append({"body_id": body, "triangles": len(faces),
                       "surface_area_mm2": math.fsum(areas), "signed_volume_mm3": volume})

    area = math.fsum(body["surface_area_mm2"] for body in bodies)
    volume = math.fsum(body["signed_volume_mm3"] for body in bodies)
    area_error = abs(area - occt_metrics["surface_area"]) / occt_metrics["surface_area"]
    volume_error = abs(volume - occt_metrics["volume"]) / occt_metrics["volume"]
    if not (area_error <= RELATIVE_TOLERANCE and volume_error <= RELATIVE_TOLERANCE):
        raise ValueError(f"GLB/OCCT area or volume mismatch: area={area_error:g}, volume={volume_error:g}")
    return {"valid": True, "body_count": len(bodies), "triangle_count": sum(b["triangles"] for b in bodies),
            "surface_area_mm2": area, "signed_volume_mm3": volume,
            "area_relative_error": area_error, "volume_relative_error": volume_error,
            "relative_tolerance": RELATIVE_TOLERANCE, "bodies": bodies}
