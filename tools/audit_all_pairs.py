"""Unrestricted actual BRep audit: every pair of every assembly component.

No carriage/arm regions or hardware are excluded. Modeled M3 screw entries
into solid motor reference envelopes are explicitly labeled, never removed.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import multiprocessing
from pathlib import Path
import sys

import build123d as b

MODEL = None
SOURCE = None
SOURCE_SHA = None
OUT = None
ZERO = None


def load_model(source):
    global MODEL, SOURCE, SOURCE_SHA
    SOURCE = Path(source)
    spec = importlib.util.spec_from_file_location('unrestricted_audit_target', SOURCE)
    MODEL = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = MODEL
    spec.loader.exec_module(MODEL)
    SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def bbox_overlap(a, c):
    aa, cc = a.bounding_box(), c.bounding_box()
    return all(min(getattr(aa.max, x), getattr(cc.max, x)) >
               max(getattr(aa.min, x), getattr(cc.min, x)) + 1e-8
               for x in ('X', 'Y', 'Z'))


def intersect(a, c):
    if not bbox_overlap(a, c):
        return 0.0, None
    common = a.intersect(c)
    if common is None or not common.solids():
        return 0.0, None
    v = sum(s.volume for s in common.solids())
    if v <= 1e-6:
        return v, None
    bounds = common.bounding_box()
    return v, {'minimum_mm': list(bounds.min), 'maximum_mm': list(bounds.max)}


def intent_label(a, c):
    motor = ('NEMA17_body', 'NEMA17_face')
    if (a.startswith('M3_motor_') and c in motor) or (c.startswith('M3_motor_') and a in motor):
        return 'Motor mounting screw occupies unmodeled tapped hole in solid motor reference envelope.'
    return None


def initialize(source):
    load_model(source)


def audit_pose(phi):
    # Call the actual assembly generator for this pose. This avoids trusting
    # prior viewer transforms or reproducing hardware-pivot classifications.
    parts_local = MODEL.make_parts(phi)
    parts = {n: MODEL.to_world(s) for n, s in parts_local.items()}
    p = MODEL.P
    height = MODEL.kinematics(phi)[2]-MODEL.kinematics(-p.limit)[2]
    names = list(parts)
    result = {'wheel_angle_degrees': phi, 'height_above_contact_mm': height,
              'source_sha256': SOURCE_SHA,
              'part_count': len(parts), 'pair_count': len(names)*(len(names)-1)//2,
              'invalid_parts': [n for n,s in parts.items() if not s.is_valid],
              'non_single_solid_parts': {n:len(s.solids()) for n,s in parts.items() if len(s.solids())!=1},
              'broadphase_candidates': 0, 'intersections': [], 'optical_keepout': [],
              'optical_other_nonprobe_checks': [], 'conservative_probe_checks': []}
    for a, c in itertools.combinations(names, 2):
        if not bbox_overlap(parts[a], parts[c]):
            continue
        result['broadphase_candidates'] += 1
        volume, bounds = intersect(parts[a], parts[c])
        if volume > 1e-5:
            row = {'a': a, 'b': c, 'intersection_volume_mm3': volume,
                   'intersection_bounds_world_mm': bounds, 'intentional_reference_engagement': intent_label(a, c)}
            result['intersections'].append(row)
            print('INTERSECTION', round(height, 4), a, c, round(volume, 6), flush=True)
    # Protect the barrel's optical projection below Y=0, with 2 mm clearance.
    # The print bodies are checked individually; only metallic probe is allowed.
    for radius in (p.microscope_d/2, p.microscope_d/2+2):
        keepout = MODEL.cylinder(radius, p.working_distance, (0, -p.working_distance, 0), (0, 1, 0))
        for name in MODEL.PRINTABLE:
            v, bounds = intersect(parts[name], keepout)
            result['optical_keepout'].append({'part': name, 'keepout_radius_mm': radius,
                                             'intersection_volume_mm3': v, 'intersection_bounds_world_mm': bounds})
        for name in names:
            if name in MODEL.PRINTABLE or name == 'probe_reference':
                continue
            v, bounds = intersect(parts[name],keepout)
            result['optical_other_nonprobe_checks'].append({'part':name,'keepout_radius_mm':radius,
                'intersection_volume_mm3':v,'intersection_bounds_world_mm':bounds})
    if hasattr(MODEL,'conservative_probe'):
        probe = MODEL.to_world(MODEL.conservative_probe(phi))
        primary = ('microscope_reference','frame_front_clamp','rear_clamp','probe_carriage','specimen_plate_reference')
        for name in names:
            if name == 'probe_reference':
                continue
            v,bounds=intersect(probe,parts[name])
            row={'a':'alternative_conservative_probe_6mm','b':name,'intersection_volume_mm3':v,
                 'intersection_bounds_world_mm':bounds,'clearance_mm':probe.distance_to(parts[name]) if name in primary else None}
            result['conservative_probe_checks'].append(row)
            if v>1e-5:
                print('CONSERVATIVE PROBE COLLISION',round(height,4),name,v,flush=True)
    result['selected_part_bounds_world_mm'] = {n: {'min': list(parts[n].bounding_box().min),
                                                 'max': list(parts[n].bounding_box().max)}
                                             for n in ('frame_front_clamp','front_axle_bridge','M5_wheel_axle','sector_crank','motor_pinion','connecting_rod','probe_carriage','625ZZ_crank','M5_crank_nut','probe_reference')}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'versions/v1/site/downloads/slider_crank_v3.py')
    ap.add_argument('--output', type=Path, default=Path.cwd() / 'regenerated/v1_all_pairs.json')
    ap.add_argument('--frames', type=int, default=41)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--contact-only', action='store_true')
    args = ap.parse_args()
    load_model(args.source)
    p = MODEL.P
    report = {'source': str(args.source.resolve()), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'no_excluded_parts_or_regions': True, 'poses': [],
              'conservative_probe_scope':'Alternative pointed full-length 6 mm diameter metal probe against every actual part except the existing probe_reference, which represents the same physical part.',
              'optical_keepout_definition': {'world_y_interval_mm': [-p.working_distance,0], 'radii_mm':[p.microscope_d/2,p.microscope_d/2+2]}}
    angles = [-p.limit] if args.contact_only else [-p.limit+2*p.limit*i/(args.frames-1) for i in range(args.frames)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pool = multiprocessing.get_context('spawn').Pool(args.workers, initializer=initialize, initargs=(str(args.source.resolve()),))
    for i, pose in enumerate(pool.imap_unordered(audit_pose, angles)):
        report['poses'].append(pose)
        report['poses'].sort(key=lambda r:r['height_above_contact_mm'])
        args.output.write_text(json.dumps(report,indent=2))
        print('AUDIT POSE',i+1,'/',len(angles),'height',pose['height_above_contact_mm'],'pairs',pose['pair_count'],'completed',flush=True)
    pool.close();pool.join()
    report['unexpected_intersections'] = [dict(height_above_contact_mm=pose['height_above_contact_mm'], **row)
                                          for pose in report['poses'] for row in pose['intersections']
                                          if row['intentional_reference_engagement'] is None]
    report['optical_print_failures'] = [dict(height_above_contact_mm=pose['height_above_contact_mm'], **row)
                                       for pose in report['poses'] for row in pose['optical_keepout']
                                       if row['intersection_volume_mm3'] > 1e-5]
    report['optical_other_nonprobe_failures'] = [dict(height_above_contact_mm=pose['height_above_contact_mm'], **row)
        for pose in report['poses'] for row in pose['optical_other_nonprobe_checks'] if row['intersection_volume_mm3']>1e-5]
    report['conservative_probe_failures'] = [dict(height_above_contact_mm=pose['height_above_contact_mm'], **row)
        for pose in report['poses'] for row in pose['conservative_probe_checks'] if row['intersection_volume_mm3']>1e-5]
    args.output.write_text(json.dumps(report,indent=2))
    print('COMPLETE',args.output,'unexpected intersections',len(report['unexpected_intersections']),
          'optical print failures',len(report['optical_print_failures']),flush=True)


if __name__ == '__main__':
    main()
