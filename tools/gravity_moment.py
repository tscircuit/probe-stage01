"""Independent static-gravity estimate from build123d mass centroids.

All dimensions are mm. CAD volume gives a 100%-solid PETG equivalent;
uniform effective material fractions are sensitivity cases, not slicer
infill settings. The microscope and specimen are existing equipment and
excluded; the modeled metal probe is included. No structural strength or
dynamic/probe-force claim is made.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path


GRAVITY = 9.80665
PETG_DENSITY_G_CM3 = 1.27
STEEL_DENSITY_G_CM3 = 7.85
MOTOR_MASSES_G = {"NEMA17_body": 270.0, "NEMA17_face": 9.0, "motor_shaft": 1.0}
BEARING_MASS_G = 5.0
REFERENCE_MM = (0.0, 9.0, 0.0)
EXCLUDED = {"microscope_reference", "specimen_plate_reference", "optical_view_reference"}


def load_source(path):
    spec = importlib.util.spec_from_file_location("moment_cad", path)
    model = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = model
    spec.loader.exec_module(model)
    return model


def phi_for_height(model, height):
    p = model.P
    low = model.kinematics(-p.limit, p)[2]
    left, right = -p.limit, p.limit
    for _ in range(80):
        middle = (left + right) / 2
        if model.kinematics(middle, p)[2] - low < height:
            left = middle
        else:
            right = middle
    return (left + right) / 2


def rotate_xy(point, angle_degrees, center=(0, 0, 0)):
    a = math.radians(angle_degrees)
    x, y = point[0] - center[0], point[1] - center[1]
    return (center[0] + x * math.cos(a) - y * math.sin(a),
            center[1] + x * math.sin(a) + y * math.cos(a), point[2])


def moved_centroid(model, name, centroid_zero, phi):
    p = model.P
    cx, cy, sy, rod_angle = model.kinematics(phi, p)
    _, _, sy_zero, rod_angle_zero = model.kinematics(0, p)
    motion = model.motion(name)
    x, y, z = centroid_zero
    if motion == "wheel":
        return rotate_xy(centroid_zero, phi)
    if motion == "pinion":
        return rotate_xy(centroid_zero, phi * p.ring_teeth / p.pinion_teeth,
                         (-p.motor_offset, 0, 0))
    if motion == "rod":
        x, y, z = rotate_xy(centroid_zero, rod_angle - rod_angle_zero,
                            (p.crank_r, 0, 0))
        return (x + cx - p.crank_r, y + cy, z)
    if motion in {"slider", "slider_pivot"}:
        return (x, y + sy - sy_zero, z)
    if motion == "crank_pivot":
        return (x + cx - p.crank_r, y + cy, z)
    return centroid_zero


def world_point(model, local):
    # Delegating the global transform to the source supports future drive-plane
    # yaw without assuming that the model has translation-only placement.
    vertex = model.b.Vertex(*local)
    return list(model.to_world(vertex, model.P).center())


def aggregate(parts):
    mass = sum(p["mass_g"] for p in parts)
    sums = [sum(p["mass_g"] * (p["centroid_world_mm"][i] - REFERENCE_MM[i])
                for p in parts) for i in range(3)]
    centroid = [sum(p["mass_g"] * p["centroid_world_mm"][i] for p in parts) / mass
                for i in range(3)]
    # r x F for F=(0,-m*g,0): torque=(+m*g*z, 0, -m*g*x).
    torque = [GRAVITY * 1e-6 * sums[2], 0.0, -GRAVITY * 1e-6 * sums[0]]
    lateral = math.hypot(centroid[0] - REFERENCE_MM[0],
                         centroid[2] - REFERENCE_MM[2])
    return {"mass_g": mass, "centroid_world_mm": centroid,
            "radial_moment_arm_mm": lateral,
            "gravity_torque_vector_Nm": torque,
            "gravity_bending_moment_Nm": math.hypot(torque[0], torque[2]),
            "mass_first_moment_xz_g_mm": [sums[0], sums[2]]}


def assess(source, peak_samples=401):
    source_hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
    model = load_source(source)
    print("Building zero-angle source solids", flush=True)
    parts = model.make_parts(0, model.P)
    zero = {name: {"volume_mm3": shape.volume,
                   "centroid_local_mm": list(shape.center(model.b.CenterOf.MASS)),
                   "valid": shape.is_valid, "solid_count": len(shape.solids())}
            for name, shape in parts.items()}
    report = {
        "source": str(source.resolve()),
        "source_sha256": source_hash_before,
        "reference_point_world_mm": REFERENCE_MM,
        "gravity_direction_world": [0, -1, 0],
        "assumptions": {
            "petg_solid_density_g_cm3": PETG_DENSITY_G_CM3,
            "steel_density_g_cm3": STEEL_DENSITY_G_CM3,
            "motor_assumed_total_mass_g": sum(MOTOR_MASSES_G.values()),
            "motor_mass_allocation_g": MOTOR_MASSES_G,
            "625ZZ_assumed_mass_each_g": BEARING_MASS_G,
            "print_effective_material_fractions": [1.0, 0.6, 0.35],
            "excluded_existing_equipment": sorted(EXCLUDED),
            "included_probe": "Actual tapered metal reference, modeled as steel",
            "motor_centroid_note": "270/9/1 g body/face/shaft allocation is an assumption, not a measured motor mass distribution.",
            "print_note": "100%-solid CAD equivalent; lower uniform fractions are sensitivity cases and are not slicer infill percentages.",
            "limitations": "Static gravity only. No acceleration, contact force, cable load, material anisotropy, stress, clamp slip or stiffness validation."
        },
        "parameters": {name: value for name, value in vars(model.P).items()},
        "zero_angle_solid_properties": zero,
        "printed_zero_angle_solid_properties": {name: zero[name] for name in model.PRINTABLE},
        "printed_solid_volume_mm3": sum(zero[name]["volume_mm3"] for name in model.PRINTABLE),
        "poses": []
    }
    world_origin = world_point(model, (0, 0, 0))
    world_axes = [[world_point(model, tuple(1 if i == j else 0 for i in range(3)))[k] - world_origin[k]
                   for k in range(3)] for j in range(3)]

    def mapped_world(local):
        return [world_origin[k] + sum(local[j] * world_axes[j][k] for j in range(3))
                for k in range(3)]

    def calculate_pose(phi, include_parts=False):
        centroid = {name: mapped_world(moved_centroid(model, name, row["centroid_local_mm"], phi))
                    for name, row in zero.items() if name not in EXCLUDED}
        cases = []
        for fraction in report["assumptions"]["print_effective_material_fractions"]:
            rows = []
            for name, row in zero.items():
                if name in EXCLUDED:
                    continue
                if name in model.PRINTABLE:
                    mass = row["volume_mm3"] * PETG_DENSITY_G_CM3 * fraction / 1000
                    group = "printed"
                elif name in MOTOR_MASSES_G:
                    mass = MOTOR_MASSES_G[name]
                    group = "motor"
                elif name.startswith("625ZZ"):
                    mass = BEARING_MASS_G
                    group = "other_hardware"
                else:
                    mass = row["volume_mm3"] * STEEL_DENSITY_G_CM3 / 1000
                    group = "other_hardware"
                rows.append({"part": name, "group": group, "volume_mm3": row["volume_mm3"],
                             "mass_g": mass, "centroid_world_mm": centroid[name]})
            case = {"effective_material_fraction": fraction, **aggregate(rows)}
            if include_parts:
                case["groups"] = {group: aggregate([r for r in rows if r["group"] == group])
                                  for group in ["printed", "motor", "other_hardware"]}
                case["parts"] = rows
            cases.append(case)
        height = model.kinematics(phi, model.P)[2] - model.kinematics(-model.P.limit, model.P)[2]
        return {"height_mm": height, "wheel_angle_degrees": phi, "cases": cases}

    for height in [0, 20, 40]:
        phi = phi_for_height(model, height)
        pose = calculate_pose(phi, True)
        pose["height_mm"] = height
        report["poses"].append(pose)
        print("Calculated lift", height, "mm", flush=True)

    samples = [calculate_pose(-model.P.limit + 2 * model.P.limit * i / (peak_samples - 1))
               for i in range(peak_samples)]
    peaks = []
    for case_index, fraction in enumerate(report["assumptions"]["print_effective_material_fractions"]):
        def score(phi):
            return calculate_pose(phi)["cases"][case_index]["gravity_bending_moment_Nm"]

        candidates = [samples[0], samples[-1]]
        brackets = []
        for i in range(1, peak_samples - 1):
            a, c, d = [samples[j]["cases"][case_index]["gravity_bending_moment_Nm"]
                       for j in [i - 1, i, i + 1]]
            if c >= a and c >= d:
                left = samples[i - 1]["wheel_angle_degrees"]
                right = samples[i + 1]["wheel_angle_degrees"]
                brackets.append([left, right])
                # Bounded numerical refinement of every detected local maximum.
                golden = (math.sqrt(5) - 1) / 2
                x1 = right - golden * (right - left)
                x2 = left + golden * (right - left)
                f1, f2 = score(x1), score(x2)
                for _ in range(65):
                    if f1 < f2:
                        left, x1, f1 = x1, x2, f2
                        x2 = left + golden * (right - left)
                        f2 = score(x2)
                    else:
                        right, x2, f2 = x2, x1, f1
                        x1 = right - golden * (right - left)
                        f1 = score(x1)
                candidates.append(calculate_pose((left + right) / 2))
        peak = max(candidates, key=lambda pose: pose["cases"][case_index]["gravity_bending_moment_Nm"])
        peaks.append({"effective_material_fraction": fraction,
                      "height_mm": peak["height_mm"],
                      "wheel_angle_degrees": peak["wheel_angle_degrees"],
                      **peak["cases"][case_index],
                      "local_maximum_brackets_degrees": brackets})
    report["full_stroke_gravity"] = {
        "method": "401 uniform wheel-angle samples across the full 0-40 mm lift, then bounded numerical refinement of every detected local maximum; endpoints included. Static estimate, not a structural validation.",
        "sample_count": peak_samples,
        "numerically_refined_peaks": peaks,
        "samples": samples
    }
    source_hash_after = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash_after != source_hash_before:
        raise RuntimeError("CAD source changed during the estimate")
    report["source_unchanged_during_estimate"] = True
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--peak-samples", type=int, default=401)
    args = ap.parse_args()
    report = assess(args.source, args.peak_samples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"out": str(args.out), "volume_mm3": report["printed_solid_volume_mm3"],
                      "poses": [{"height_mm": p["height_mm"],
                                 "solid_mass_g": p["cases"][0]["mass_g"],
                                 "solid_moment_Nm": p["cases"][0]["gravity_bending_moment_Nm"]}
                                for p in report["poses"]]}, indent=2), flush=True)
