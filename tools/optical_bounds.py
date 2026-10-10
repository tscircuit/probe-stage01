"""Prove continuous nonprobe optical exclusion in world coordinates.

Uses conservative envelopes of the model's declared planar motion. Moving
parts must remain outside the R24 optical column for every crank angle;
fixed parts receive an exact intersection check with the entire column.
The only allowed part is the metal probe reference.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import build123d as b


def load(source):
    spec = importlib.util.spec_from_file_location('compact_optical_model', source)
    model = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = model
    spec.loader.exec_module(model)
    return model


def bounds(shape):
    q = shape.bounding_box()
    return [list(q.min), list(q.max)]


def volume_intersection(a, c):
    common = a.intersect(c)
    return 0.0 if common is None else sum(s.volume for s in common.solids())


def world_transform(model):
    origin = model.to_world(b.Vertex(0, 0, 0)).center()
    columns = []
    for xyz in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        point = model.to_world(b.Vertex(*xyz)).center()
        columns.append(list(point-origin))
    matrix = [[columns[j][i] for j in range(3)] for i in range(3)]
    return list(origin), matrix


def affine_lower(origin, coefficients, ranges):
    return origin + sum(min(coefficient*lo, coefficient*hi)
                        for coefficient, (lo, hi) in zip(coefficients, ranges))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    source = args.source.resolve()
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    m = load(source)
    p = m.P
    neutral = m.make_parts(0)
    endpoints = [m.make_parts(-p.limit), m.make_parts(p.limit)]
    origin, rotation = world_transform(m)
    if any(abs(rotation[i][1]-(1 if i == 1 else 0)) > 1e-9 for i in range(3)):
        raise AssertionError('Local slider Y must coincide with vertical world Y.')
    if not 0 < p.limit < 90 or not p.rod_length > p.crank_r:
        raise AssertionError('This bound requires crank angles strictly within ±90 degrees.')
    radii = [p.microscope_d/2, p.microscope_d/2+2]
    corridor = m.cylinder(radii[-1], p.working_distance,
                          (0, -p.working_distance, 0), (0, 1, 0))
    low, high = [m.kinematics(a)[2] for a in (-p.limit, p.limit)]
    rows = []
    allowed = ['probe_reference']
    for name, shape in neutral.items():
        if name in allowed:
            continue
        motion = m.motion(name)
        row = {'part': name, 'motion': motion, 'printed': name in m.PRINTABLE,
               'validated': False}
        bb = bounds(shape)
        if motion == 'fixed':
            volume = volume_intersection(m.to_world(shape), corridor)
            row.update(intersection_volume_mm3=volume,
                       method='Exact BRep check against the entire R24 column; the part remains fixed.',
                       validated=volume <= 1e-5)
        else:
            # All declared moving parts use XY translations and rotations.
            # Endpoint checks also catch incorrect moving-part classifications.
            for ep in endpoints:
                eb = bounds(ep[name])
                if any(abs(eb[i][2]-bb[i][2]) > 1e-6 for i in (0, 1)):
                    raise AssertionError('Declared planar motion changed local axial bounds: '+name)
            if motion in ('slider', 'slider_pivot'):
                wb = bounds(m.to_world(shape))
                lower_x = wb[0][0]
                ranges = None
                lower_y = None
                method = 'Exact solid X bound, invariant under translation along world Y.'
            else:
                if motion in ('wheel', 'pinion'):
                    pivot = 0.0 if motion == 'wheel' else -p.motor_offset
                    radial = math.hypot(max(abs(bb[0][0]-pivot), abs(bb[1][0]-pivot)),
                                        max(abs(bb[0][1]), abs(bb[1][1])))
                    ranges = [(pivot-radial, pivot+radial), (-radial, radial),
                              (bb[0][2], bb[1][2])]
                    method = 'Conservative full-rotation cylinder from local bounding-box radial extent and invariant axial extent.'
                elif motion == 'crank_pivot':
                    cx0 = m.kinematics(0)[0]
                    ranges = [(p.crank_r*math.cos(math.radians(p.limit))+bb[0][0]-cx0,
                               p.crank_r+bb[1][0]-cx0),
                              (-p.stroke/2+bb[0][1], p.stroke/2+bb[1][1]),
                              (bb[0][2], bb[1][2])]
                    method = 'Crank-center arc envelope plus the rigid hardware bounds.'
                elif motion == 'rod':
                    raw = bounds(m.connecting_rod())
                    radial = math.hypot(max(abs(raw[0][0]), abs(raw[1][0])),
                                        max(0.0, raw[1][1], -p.rod_length-raw[0][1]))
                    ranges = [(-radial, p.crank_r+radial),
                              (low-radial, p.crank_r+radial),
                              (raw[0][2], raw[1][2])]
                    method = 'Conservative capsule around both joint centers, derived from the unplaced rod bounds.'
                else:
                    raise AssertionError('Unsupported nonprobe motion: '+name+' / '+motion)
                lower_x = affine_lower(origin[0], rotation[0], ranges)
                lower_y = affine_lower(origin[1], rotation[1], ranges)
            row.update(minimum_world_x_bound_mm=lower_x,
                       minimum_world_y_bound_mm=lower_y,
                       margin_from_R24_mm=lower_x-radii[-1],
                       conservative_local_envelope_mm=ranges,
                       method=method,
                       validated=lower_x > radii[-1]+1e-6 or (lower_y is not None and lower_y > 1e-6))
        rows.append(row)
    final_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {
        'source': str(source), 'source_sha256': source_sha,
        'final_source_sha256': final_sha, 'source_unchanged': final_sha == source_sha,
        'complete': len(rows) == len(neutral)-len(allowed) and final_sha == source_sha,
        'part_count': len(neutral), 'allowed_part_names': allowed,
        'checked_part_names': [r['part'] for r in rows],
        'world_origin_mm': origin, 'local_to_world_rotation_matrix': rotation,
        'working_distance_mm': p.working_distance, 'vertical_stroke_mm': p.stroke,
        'checked_radii_mm': radii, 'world_y_interval_mm': [-p.working_distance, 0],
        'all_moving_nonprobe_parts_clear': all(r['validated'] for r in rows if r['motion'] != 'fixed'),
        'all_fixed_nonprobe_parts_clear': all(r['validated'] for r in rows if r['motion'] == 'fixed'),
        'validated': all(r['validated'] for r in rows) and final_sha == source_sha,
        'scope': 'Continuous optical exclusion under declared planar crank, rod, and vertical slider motion. Every actual component except the metal probe is checked. R24 includes a 2 mm margin around the projected Ø44 barrel footprint; this footprint is not a measured lens field of view.',
        'rows': rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({'checked_parts': len(rows), 'complete': report['complete'],
                      'validated': report['validated']}), flush=True)
    if not report['validated']:
        raise AssertionError('Continuous optical exclusion could not be certified.')


if __name__ == '__main__':
    main()
