"""Read native Parasolid standard RGB attributes and color their GLB faces.

Appearance comes only from parasolid-kit's parsed X_T records. The source JSCAD
model is never passed to this module. Face SDL/TYSA_COLOUR (8001) overrides body
SDL/TYSA_COLOUR_2 (8040), following native topology ownership in the manifest.
"""

import json
import math
import struct


def _values(node, field_index):
    return [item.value for item in node.fields[field_index].values]


def _single(node, field_index):
    values = _values(node, field_index)
    if len(values) != 1:
        raise ValueError("Expected one native attribute field value")
    return values[0]


def read_native_colors(parsed):
    """Return native RGB values keyed by the independent reader's B-Rep IDs."""
    nodes = {node.index: node for node in parsed.document.nodes}

    def resolve(pointer, node_type):
        node = nodes.get(pointer)
        if node is None or node.node_type != node_type:
            raise ValueError(f"Native color attribute requires record {node_type} at {pointer}")
        return node

    def color_for(owner_index, owner_kind):
        owner = nodes[owner_index]
        annotations = next(field for field in owner.fields if field.definition.name == "annotations")
        pointer = annotations.values[0].value
        visited = set()
        result = None
        while pointer:
            if pointer in visited:
                raise ValueError("Cycle in native color annotation list")
            visited.add(pointer)
            attribute = resolve(pointer, 81)
            if _single(attribute, 2) != owner_index:
                raise ValueError("Native color annotation points to the wrong owner")
            definition = resolve(_single(attribute, 1), 80)
            identifier = resolve(_single(definition, 1), 79)
            characters = _values(identifier, 0)
            name = "".join(chr(char) if isinstance(char, int) else char for char in characters)
            if name in ("SDL/TYSA_COLOUR", "SDL/TYSA_COLOUR_2"):
                expected_name, expected_kind = (
                    ("SDL/TYSA_COLOUR_2", 8040) if owner_kind == "body"
                    else ("SDL/TYSA_COLOUR", 8001)
                )
                if name != expected_name or _single(definition, 2) != expected_kind:
                    raise ValueError("Native standard RGB definition does not match its owner")
                if _values(definition, 6) != [2]:
                    raise ValueError("Native RGB definition must have one real-array value")
                arrays = _values(attribute, 7)
                if len(arrays) != 1:
                    raise ValueError("Native RGB attribute must reference one value array")
                rgb = _values(resolve(arrays[0], 83), 0)
                if len(rgb) != 3 or not all(
                    isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1
                    for value in rgb
                ):
                    raise ValueError("Native RGB attribute must contain three finite unit-interval components")
                if result is not None and result != rgb:
                    raise ValueError("Conflicting native RGB attributes on one entity")
                result = rgb
            pointer = _single(attribute, 3)
        return result

    body_colors = {}
    face_colors = {}
    for body in parsed.brep.bodies:
        color = color_for(body.source.node_index, "body")
        if color is not None:
            body_colors[body.id] = color
    for face in parsed.brep.faces:
        color = color_for(face.source.node_index, "face")
        if color is not None:
            face_colors[face.id] = color
    return body_colors, face_colors


def _linear(component):
    # This exporter writes JSCAD/CSS sRGB values; glTF factors are linear.
    return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4


def apply_native_colors(glb, manifest, parsed):
    """Apply only recovered native appearance, leaving all geometry buffers intact."""
    body_colors, face_colors = read_native_colors(parsed)
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20:20 + json_length])
    metadata = {item["target_key"]: item for item in manifest["primitives"] if item["kind"] == "face"}
    materials = document.setdefault("materials", [])
    material_by_color = {}
    colored_primitives = 0
    uncolored_primitives = 0
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            target = primitive.get("extras", {}).get("targetKey")
            if target not in metadata:
                raise ValueError("GLB color mapping requires an independently mapped native face")
            source = metadata[target]
            colors = [face_colors[face] for face in source["parasolid_face_ids"] if face in face_colors]
            if not colors:
                colors = [body_colors[body] for body in source["body_ids"] if body in body_colors]
            if not colors:
                uncolored_primitives += 1
                continue
            if any(color != colors[0] for color in colors):
                raise ValueError("GLB face has conflicting native source colors")
            color = tuple(colors[0])
            if color not in material_by_color:
                material_by_color[color] = len(materials)
                materials.append({
                    "name": "native-rgb-" + "-".join(format(value, ".6g") for value in color),
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [_linear(value) for value in color] + [1],
                        "metallicFactor": 0,
                        "roughnessFactor": 0.85,
                    },
                    "extras": {"nativeSrgb": list(color)},
                })
            primitive["material"] = material_by_color[color]
            colored_primitives += 1
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    remaining = glb[20 + json_length:]
    updated = (
        struct.pack("<4sII", b"glTF", 2, 20 + len(payload) + len(remaining))
        + struct.pack("<I4s", len(payload), b"JSON") + payload + remaining
    )
    report = {
        "source": "native_x_t_attributes",
        "body_colors": [{"body_id": key, "rgb": value} for key, value in sorted(body_colors.items())],
        "face_color_count": len(face_colors),
        "palette": [list(color) for color in sorted(material_by_color)],
        "colored_primitive_count": colored_primitives,
        "uncolored_primitive_count": uncolored_primitives,
        "material_color_space": "linear_srgb",
    }
    return updated, report
