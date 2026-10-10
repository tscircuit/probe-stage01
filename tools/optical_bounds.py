"""Check a conservative optical exclusion bound for every printed part.

Moving parts use planar envelope bounds valid throughout the stroke, while
fixed parts are intersected with the full below-barrel optical corridor.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import argparse


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'versions/v1/site/downloads/slider_crank_v3.py')
    ap.add_argument('--output', type=Path, default=Path.cwd() / 'regenerated/v1_optical_bounds.json')
    args = ap.parse_args()
    source = args.source
    spec = importlib.util.spec_from_file_location('optical_bound_model', source)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    p = m.P
    assert p.tilt == 0
    parts = m.make_parts(0)
    center_x = p.world_origin[0]
    corridor_radius = p.microscope_d / 2 + 2
    corridor = m.cylinder(corridor_radius, p.working_distance, (0, -p.working_distance, 0), (0, 1, 0))
    rows = []
    for name in m.PRINTABLE:
        shape = parts[name]
        motion = m.motion(name)
        row = {'part': name, 'motion': motion}
        if motion in ('wheel', 'pinion'):
            pivot_x = 0 if motion == 'wheel' else -p.motor_offset
            vertices, _ = shape.tessellate(.05, .1)
            envelope = max(math.hypot(v.X - pivot_x, v.Y) for v in vertices) + .05
            lower_x = center_x + pivot_x - envelope
            row.update(minimum_world_x_bound_mm=lower_x, bound='Full rotation disk, expanded by tessellation tolerance.')
            assert lower_x > corridor_radius
        elif motion == 'rod':
            cx, cy, sy, _ = m.kinematics(0)
            a, c = (cx, cy), (0, sy)
            vx, vy = c[0] - a[0], c[1] - a[1]
            vertices, _ = shape.tessellate(.05, .1)
            distances = []
            for v in vertices:
                t = max(0, min(1, ((v.X-a[0])*vx + (v.Y-a[1])*vy)/(vx*vx+vy*vy)))
                distances.append(math.hypot(v.X-a[0]-t*vx, v.Y-a[1]-t*vy))
            envelope = max(distances) + .05
            # Both joint center X positions are nonnegative for ±53.13°.
            assert p.limit < 90 and cx > 0
            lower_x = center_x - envelope
            row.update(minimum_world_x_bound_mm=lower_x, bound='Capsule about the two joint centers; centerline stays at nonnegative local X.')
            assert lower_x > corridor_radius
        elif motion == 'slider':
            lower_x = m.to_world(shape).bounding_box().min.X
            row.update(minimum_world_x_bound_mm=lower_x, bound='Exact solid bound; vertical translation keeps X and Z constant.')
            assert lower_x > corridor_radius
        elif motion == 'fixed':
            common = m.to_world(shape).intersect(corridor)
            volume = 0 if common is None else sum(s.volume for s in common.solids())
            row.update(optical_corridor_intersection_mm3=volume, bound='Fixed solid intersects the entire below-barrel corridor by zero volume.')
            assert volume < 1e-5
        else:
            raise AssertionError('Unsupported printed part motion: '+motion)
        rows.append(row)
    report = {
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'working_distance_mm': p.working_distance,
        'vertical_stroke_mm': p.stroke,
        'optical_projection_radius_mm': p.microscope_d / 2,
        'checked_corridor_radius_mm': corridor_radius,
        'world_y_interval_mm': [-p.working_distance, 0],
        'scope': 'Continuous printed-part optical exclusion for the prescribed vertical motion. Physical drive collisions are checked separately with an all-pairs BRep pose audit. The optical corridor is a conservative projected housing footprint, not a measured lens field of view.',
        'parts': rows,
    }
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({'printed_parts': len(rows), 'optical_radius_mm': p.microscope_d / 2, 'checked_radius_mm': corridor_radius, 'all_clear': True}))


if __name__ == '__main__':
    main()
