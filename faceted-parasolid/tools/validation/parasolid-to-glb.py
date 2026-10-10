"""Independently read native X_T, validate with OCCT, and tessellate to GLB.

OpenCascade does not read Parasolid directly: parasolid-kit reads the native
transmit file and constructs the OCCT B-Rep. No source JSCAD geometry is used.
This validates the supported planar subset, not Siemens/Shapr3D interoperability.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path

from glb_metrics import audit_glb_mesh
from native_colors import apply_native_colors

from parasolid_kit import read_brep
from parasolid_kit.interop.occt import to_occt
from parasolid_kit.interop.preview import (
    PreviewOptions,
    tessellate_preview,
    validate_glb_bytes,
)


def glb_millimeters_to_meters(glb):
    """Preserve OCCT buffers; use a glTF scene transform for standard meter units."""
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20:20 + json_length])
    for scene in document["scenes"]:
        parent = len(document["nodes"])
        document["nodes"].append({"children": scene["nodes"], "scale": [0.001] * 3})
        scene["nodes"] = [parent]
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    remaining = glb[20 + json_length:]
    length = 20 + len(payload) + len(remaining)
    return (
        struct.pack("<4sII", b"glTF", 2, length)
        + struct.pack("<I4s", len(payload), b"JSON")
        + payload + remaining
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--source-mesh", type=Path)
    args = parser.parse_args()

    input_xt_sha256 = hashlib.sha256(args.input.read_bytes()).hexdigest()
    parsed = read_brep(args.input)
    if not parsed.complete:
        raise ValueError("Native X_T parsing did not produce a complete B-Rep")
    converted = to_occt(
        parsed.brep,
        source_unit="m",
        target_unit="mm",
        require_complete=True,
        heal=False,
    )
    report = converted.report.to_dict()
    report['input_xt_sha256'] = input_xt_sha256
    if args.source_mesh is not None:
        from planar_surface_check import compare_surfaces
        mesh_sha256=hashlib.sha256(args.source_mesh.read_bytes()).hexdigest()
        report['surface_correspondence']=compare_surfaces(args.source_mesh,converted)
        if hashlib.sha256(args.source_mesh.read_bytes()).hexdigest()!=mesh_sha256:
            raise ValueError('Source mesh changed during surface comparison')
        report['source_mesh_sha256']=mesh_sha256
    if not report["occt_valid"] or not report["conversion_complete"]:
        raise ValueError("X_T did not reconstruct as a complete, valid OCCT shape")
    if report["output_topology"].get("solids", 0) == 0:
        raise ValueError("X_T did not reconstruct any solids")
    if report["metrics"]["volume"] is None or report["metrics"]["volume"] <= 0:
        raise ValueError("X_T reconstructed with missing or non-positive solid volume")

    preview = tessellate_preview(
        converted,
        parsed.brep,
        options=PreviewOptions(
            linear_deflection=0.05,
            angular_deflection=0.5,
            include_edges=False,
            allow_partial=False,
        ),
    )
    glb = glb_millimeters_to_meters(preview.glb)
    glb, report["native_colors"] = apply_native_colors(glb, preview.manifest, parsed)
    validation = validate_glb_bytes(glb)
    if not validation.valid or preview.missing_face_count or not preview.triangle_count:
        raise ValueError("OCCT did not tessellate all faces into a valid GLB")
    # Check the emitted buffers, not just OCCT's pre-tessellation B-Rep metrics.
    report["mesh_validation"] = audit_glb_mesh(glb, preview.manifest, report["metrics"])
    report["preview"] = {
        "triangle_count": preview.triangle_count,
        "vertex_count": preview.vertex_count,
        "missing_face_count": preview.missing_face_count,
        "glb_valid": validation.valid,
    }
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != input_xt_sha256:
        raise ValueError('Input X_T changed during independent validation')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(glb)
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
