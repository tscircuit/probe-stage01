"""Read-only verification of an archived release; requires only Python stdlib."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile


def read_json(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def report_path(site, manifest, key, fallback):
    reference = manifest.get('reports', {}).get(key, './downloads/' + fallback)
    path = (site / reference).resolve()
    require(path.is_relative_to(site.resolve()), f'Report path leaves the version: {key}')
    return path


def hash_values(value):
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if 'sha256' in key.lower() and isinstance(child, str) and re.fullmatch(r'[0-9a-f]{64}', child):
                found.add(child)
            found.update(hash_values(child))
    elif isinstance(value, list):
        for child in value:
            found.update(hash_values(child))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', default='v1', help='Archived release directory name.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1],
                        help='Repository root; defaults to the parent of tools/.')
    args = parser.parse_args()
    require(re.fullmatch(r'v[0-9]+', args.release) is not None, 'Release must be v followed by digits.')
    release = args.root.resolve() / 'versions' / args.release
    snapshot = read_json(release / 'SNAPSHOT.json')
    require(snapshot['release'] == args.release, 'Snapshot release name differs.')
    expected_files = snapshot['files']
    actual_files = {str(path.relative_to(release)) for path in (release / 'site').rglob('*') if path.is_file()}
    require(actual_files == set(expected_files), 'Archived Site file list changed.')
    for name, expected in expected_files.items():
        path = release / name
        require(not path.is_symlink() and path.is_file(), f'Expected ordinary file: {name}')
        require(path.stat().st_size == expected['bytes'], f'Archived file size changed: {name}')
        require(digest(path) == expected['sha256'], f'Archived file bytes changed: {name}')
    require(len(actual_files) == snapshot['site_file_count'], 'Snapshot file count differs.')

    site = release / 'site'
    downloads = site / 'downloads'
    manifest = read_json(site / 'assets/manifest.json')
    model = read_json(site / 'assets/model.json')
    source = downloads / Path(manifest['downloads']['source']).name
    source_hash = digest(source)
    require(source_hash == snapshot['source_sha256'] == manifest['source_sha256'], 'Source hash differs.')
    checksums = read_json(downloads / 'sha256_checksums.json')
    for name, expected in checksums.items():
        require((downloads / name).is_file() and digest(downloads / name) == expected,
                f'Download checksum differs: {name}')

    dimensions = read_json(report_path(site, manifest, 'dimensions', 'dimensions_and_checks.json'))
    audit = read_json(report_path(site, manifest, 'allPairs', 'v3_all_pairs.json'))
    optical = read_json(report_path(site, manifest, 'optical', 'optical_bounds.json'))
    roundtrip = read_json(report_path(site, manifest, 'roundtrip', 'step_roundtrip_checks.json'))
    names = {part['name'] for part in model['parts']}
    printable = set(model['meta']['printable'])
    count = len(names)
    pair_count = count * (count - 1) // 2
    require(count == snapshot['component_count'] == manifest['component_count'], 'Component count differs.')
    require(len(printable) == snapshot['printable_count'] == manifest['printable_count'], 'Printable count differs.')
    require(names == set(dimensions['parts']) == set(manifest['parts']), 'Component names differ.')
    require(all(part['valid'] and part['solids'] == 1 for part in dimensions['parts'].values()),
            'An exported component is invalid or not a single solid.')
    if 'step_models' in roundtrip:
        require(roundtrip['step_models'] == count and not roundtrip['bad'], 'STEP roundtrip report failed.')
    else:
        require(roundtrip.get('part_count') == count and roundtrip.get('source_unchanged') is True
                and roundtrip.get('valid_single_solid_all') is True, 'STEP roundtrip report failed.')
        rows = roundtrip['parts']
        require(len(rows) == count and {row['part'] for row in rows} == names,
                'STEP roundtrip component coverage differs.')
        require(all(row['valid'] and row['solids'] == 1 and row['absolute_volume_error_mm3'] <= 1e-3
                    for row in rows), 'A component STEP roundtrip failed.')
        assembly = roundtrip['assembly']
        require(assembly['valid'] and assembly['solids'] == count
                and assembly['absolute_volume_error_mm3'] <= 1e-3, 'Assembly STEP roundtrip failed.')
    require(source_hash == audit['source_sha256'] == optical['source_sha256'] == roundtrip['source_sha256'],
            'Verification report source hashes differ.')
    require(audit['no_excluded_parts_or_regions'] is True, 'Audit contains exclusions.')
    if args.release != 'v1':
        require(audit.get('complete') is True, 'All-pairs audit is not complete.')
    require(len(audit['poses']) == snapshot['checked_pose_count'], 'Audit pose count differs.')
    require(pair_count == snapshot['pairs_per_pose'], 'Pair count differs.')
    threshold = 1e-5
    for pose in audit['poses']:
        require(pose['source_sha256'] == source_hash, 'A pose uses a different source.')
        require(pose['part_count'] == count and pose['pair_count'] == pair_count, 'A pose is incomplete.')
        require(not pose['invalid_parts'] and not pose['non_single_solid_parts'], 'A posed solid is invalid.')
        require(not pose['intersections'], 'Saved audit contains an intersection.')
        require(all(row['intersection_volume_mm3'] <= threshold for row in pose['optical_keepout']),
                'Saved printed optical corridor checks failed.')
        require(all(row['intersection_volume_mm3'] <= threshold for row in pose['optical_other_nonprobe_checks']),
                'Saved non-probe optical corridor checks failed.')
        require(len(pose['conservative_probe_checks']) == count - 1, 'Alternative probe audit is incomplete.')
        require({row['b'] for row in pose['conservative_probe_checks']} == names - {'probe_reference'},
                'Alternative probe obstacle list differs.')
        require(all(row['intersection_volume_mm3'] <= threshold for row in pose['conservative_probe_checks']),
                'Saved alternative probe collision checks failed.')
    for key in ('unexpected_intersections', 'optical_print_failures', 'optical_other_nonprobe_failures',
                'conservative_probe_failures'):
        require(not audit[key], f'Saved audit contains failures: {key}')
    heights = sorted(pose['height_above_contact_mm'] for pose in audit['poses'])
    require(math.isclose(heights[0], 0, abs_tol=1e-6) and math.isclose(heights[-1], 40, abs_tol=1e-6),
            'Saved audit does not include both travel endpoints.')
    if 'rows' in optical:
        for key in ('complete', 'validated', 'all_moving_nonprobe_parts_clear', 'all_fixed_nonprobe_parts_clear'):
            require(optical.get(key) is True, f'World-space optical validation failed: {key}')
        optical_names = names - {'probe_reference'}
        require(optical['part_count'] == count and optical['allowed_part_names'] == ['probe_reference'],
                'World-space optical component contract differs.')
        require(set(optical['checked_part_names']) == optical_names and
                {row['part'] for row in optical['rows']} == optical_names,
                'World-space optical component coverage differs.')
        require(optical['rows'] and all(row.get('validated') is True for row in optical['rows']),
                'A world-space optical validation row failed.')
    else:
        # Preserve the original v1 contract; newer versions use validated
        # world-space rows instead of inheriting these baseline X bounds.
        require(args.release == 'v1', 'New versions require a world-space optical report.')
        require({row['part'] for row in optical['parts']} == printable, 'Optical bound component list differs.')
        for row in optical['parts']:
            if 'minimum_world_x_bound_mm' in row:
                require(row['minimum_world_x_bound_mm'] > optical['checked_corridor_radius_mm'],
                        'Saved moving printed-part optical bound failed.')
            else:
                require(row['optical_corridor_intersection_mm3'] <= threshold,
                        'Saved fixed printed-part optical bound failed.')
    if 'comparison' in manifest.get('reports', {}):
        comparison = read_json(report_path(site, manifest, 'comparison', 'mass_moment_comparison.json'))
        baseline = read_json(args.root.resolve() / 'versions/v1/SNAPSHOT.json')
        provenance = hash_values(comparison)
        require(comparison.get('complete') is True and source_hash in provenance and
                baseline['source_sha256'] in provenance, 'Comparison source provenance differs.')

    reference_count = snapshot.get('reference_step_count', 0)
    if 'controller' in manifest.get('reports', {}):
        for key in ('all_controller_reservations_clear', 'all_open_rear_access_clear'):
            require(audit.get(key) is True, f'Sampled controller/rear-access report failed: {key}')
        for key in ('controller_reservation_failures', 'controller_reservation_optical_failures',
                    'controller_reservation_conservative_probe_failures', 'open_rear_access_failures'):
            require(audit.get(key) == [], f'Sampled controller/rear-access failures: {key}')
        controller = read_json(report_path(site, manifest, 'controller', 'controller_clearance.json'))
        require(controller['source_sha256'] == source_hash, 'Controller clearance source differs.')
        for key in ('complete', 'validated', 'source_unchanged', 'continuous',
                    'back_faces_away_from_barrel', 'all_reservations_clear', 'all_open_rear_corridor_clear'):
            require(controller.get(key) is True, f'Controller/rear-access report failed: {key}')
        require(controller['part_count'] == count and set(controller['checked_part_names']) == names,
                'Controller obstacle coverage differs.')
        require(len(controller['rows']) == count and {row['part'] for row in controller['rows']} == names
                and all(row.get('validated') is True for row in controller['rows']),
                'Controller continuous validation rows failed.')
        reservation = model['meta']['controllerReservation']
        require(controller['nominal_dimensions_mm'] == reservation['nominal_dimensions_mm'] == [42, 42, 20]
                and controller['clearance_dimensions_mm'] == [46, 46, 22]
                and reservation['clearance_mm'] == 2, 'Controller reservation dimensions differ.')
        require(controller['rear_normal_world'] == reservation['rear_normal_world'] == [0, 0, -1],
                'Motor rear direction differs.')
        proof = reservation['verification']
        require(proof['source_sha256'] == source_hash and proof['validated'] is True
                and proof['continuous'] is True and proof['open_rear'] is True,
                'Viewer controller annotation lacks source-matched proof.')
        for report_key, derived_key in (('nominal_world_bounds_mm', 'controller_world_bounds_mm'),
                                        ('clearance_world_bounds_mm', 'controller_keepout_world_bounds_mm')):
            for end in ('min', 'max'):
                a, e = controller[report_key][end], dimensions['derived'][derived_key][end]
                require(len(a) == len(e) == 3 and all(math.isfinite(x) and math.isclose(x, y, abs_tol=1e-6)
                        for x, y in zip(a, e)), 'Controller world-space bounds differ.')
        refs = roundtrip['reserved_reference_exports']
        reference_names = {'motor_controller_reserved_envelope', 'motor_controller_clearance_keepout'}
        require(reference_count == 2 and len(refs) == 2 and {r['name'] for r in refs} == reference_names
                and all(r['reference_only'] and r['valid'] and r['solids'] == 1 and
                        r['absolute_volume_error_mm3'] <= 1e-3 for r in refs),
                'Controller STEP reference roundtrips failed.')
        require({p.stem for p in (downloads / 'references').glob('*.step')} == reference_names,
                'Controller reference STEP inventory differs.')
    else:
        require(reference_count == 0, 'Unexpected extra STEP references.')

    steps = list((downloads / 'parts').glob('*.step'))
    stls = list((downloads / 'parts').glob('*.stl'))
    require({path.stem for path in steps} == names, 'Component STEP inventory differs.')
    require({path.stem for path in stls} == printable, 'Printable STL inventory differs.')
    assembly_step = downloads / Path(manifest['downloads']['assemblyStep']).name
    for path in steps + [assembly_step]:
        with path.open('rb') as stream:
            require(stream.read(13) == b'ISO-10303-21;', f'Invalid STEP header: {path.name}')
    bundle = downloads / Path(manifest['downloads']['bundle']).name
    with zipfile.ZipFile(bundle) as archive:
        require(archive.testzip() is None, 'Bundle ZIP integrity check failed.')
        require(sum(name.endswith('.step') for name in archive.namelist()) == count + 1 + reference_count,
                'Bundle STEP count differs.')
        require(sum(name.endswith('.stl') for name in archive.namelist()) == len(printable),
                'Bundle STL count differs.')
    print(json.dumps({
        'release': args.release, 'site_files': len(actual_files), 'download_checksums': len(checksums),
        'source_sha256': source_hash, 'component_step_files': len(steps), 'printable_stls': len(stls),
        'checked_poses': len(audit['poses']), 'pairs_per_pose': pair_count,
        'reference_step_files': reference_count,
        'all_intersections': 0, 'archived_bytes_unchanged': True,
        'verification': 'Read-only integrity and saved-report checks; no CAD regeneration.',
    }, indent=2))


if __name__ == '__main__':
    main()
