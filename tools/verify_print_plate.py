#!/usr/bin/env python3
"""Independently read printable plates with official lib3mf and frozen STL inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import xml.etree.ElementTree as ET

import lib3mf
import numpy as np
from scipy.spatial import ConvexHull


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stl_triangles(path):
    data = path.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    assert len(data) == 84 + count * 50
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attribute', '<u2')])
    return np.frombuffer(data, dtype=dtype, count=count, offset=84)['vertices'].astype(float)


def volume(triangles):
    t = triangles - triangles[0, 0]
    return float(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)


def hull(points):
    unique = np.unique(points, axis=0)
    return unique[ConvexHull(unique).vertices]


def separation(a, b):
    best = float('-inf')
    for polygon in (a, b):
        edges = np.roll(polygon, -1, axis=0) - polygon
        axes = np.column_stack((-edges[:, 1], edges[:, 0]))
        axes /= np.linalg.norm(axes, axis=1)[:, None]
        aa, bb = a @ axes.T, b @ axes.T
        best = max(best, float(np.maximum(bb.min(0) - aa.max(0), aa.min(0) - bb.max(0)).max()))
    return best


def verify(repo, plates, version, output):
    addon = plates / version
    manifest = json.loads((addon / 'manifest.json').read_text())
    report = json.loads((addon / 'validation.json').read_text())
    site = repo / 'versions' / version / 'site'
    source_manifest = json.loads((site / 'assets/manifest.json').read_text())
    source_model = json.loads((site / 'assets/model.json').read_text())
    names = set(source_model['meta']['printable'])
    assert len(names) == 7 and set(manifest['names']) == names
    assert all(source_manifest['parts'][name]['category'] == 'Fabricated parts' for name in names)
    source = site / source_manifest['downloads']['source']
    assert manifest['source_sha256'] == source_manifest['source_sha256'] == digest(source)
    assert report['complete'] and report['validated'] and report['hardware_included'] is False
    file = addon / manifest['file']
    assert digest(file) == manifest['sha256'] and file.stat().st_size == manifest['bytes']
    assert digest(addon / 'validation.json') == manifest['report_sha256']
    ns = {'m': 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
    with zipfile.ZipFile(file) as z:
        assert z.testzip() is None
        xml = ET.fromstring(z.read('3D/3dmodel.model'))
        objects = xml.findall('./m:resources/m:object', ns)
        build = xml.findall('./m:build/m:item', ns)
        assert len(objects) == len(build) == 7
        assert {x.get('name') for x in objects} == names
        assert {x.get('objectid') for x in build} == {x.get('id') for x in objects}
        assert len({x.get('objectid') for x in build}) == 7
        assert all(not x.get('transform') for x in build)
    wrapper = lib3mf.get_wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader('3mf')
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(file))
    assert reader.GetWarningCount() == 0
    assert model.GetUnit() == lib3mf.ModelUnit.MilliMeter
    assert model.GetBuildItems().Count() == 7
    rows = {r['name']: r for r in report['parts']}
    parsed, projections = [], []
    it = model.GetMeshObjects()
    while it.MoveNext():
        mesh = it.GetCurrentMeshObject()
        name = mesh.GetName()
        assert name in names and mesh.IsValid() and mesh.IsManifoldAndOriented()
        vertices = np.array([list(v.Coordinates) for v in mesh.GetVertices()], dtype=float)
        indices = np.array([list(t.Indices) for t in mesh.GetTriangleIndices()], dtype=int)
        triangles = vertices[indices]
        source_stl = site / 'downloads/parts' / (name + '.stl')
        original = stl_triangles(source_stl)
        row = rows[name]
        assert digest(source_stl) == row['source_stl_sha256']
        rotation = np.array(row['rigid_rotation_source_to_plate'])
        translation = np.array(row['rigid_translation_source_to_plate_mm'])
        assert np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-10)
        assert abs(np.linalg.det(rotation) - 1) < 1e-10
        expected = original @ rotation.T + translation
        assert len(triangles) == len(original) == row['triangle_count']
        error = float(np.abs(triangles - expected).max())
        assert error < 3e-5
        before, after = volume(original), volume(triangles)
        relative_error = abs(after / before - 1)
        assert before > 0 and after > 0 and relative_error < 1e-5
        minimum, maximum = vertices.min(0), vertices.max(0)
        assert abs(minimum[2]) < 1e-6
        assert all(minimum[:2] >= 5 - 3e-5)
        assert all(maximum[:2] <= np.array(manifest['plate_mm']) - 5 + 3e-5)
        projections.append((name, hull(vertices[:, :2])))
        parsed.append({'name': name, 'valid': True, 'manifold_oriented': True,
                       'triangles': len(triangles), 'source_stl_sha256': digest(source_stl),
                       'readback_rigid_coordinate_error_mm': error,
                       'readback_volume_relative_error': relative_error,
                       'bed_z_min_mm': float(minimum[2])})
    assert len(parsed) == 7 and {r['name'] for r in parsed} == names
    pairs = []
    for i, (name, p) in enumerate(projections):
        for other, q in projections[i+1:]:
            gap = separation(p, q)
            assert gap >= 5 - 3e-5
            pairs.append({'names': [name, other], 'projected_separation_mm': gap})
    result = {'public_version': version, 'passed': True, 'reader': 'official lib3mf',
              'reader_version': list(wrapper.GetLibraryVersion()), 'strict_mode': True,
              'reader_warnings': 0, 'units': 'mm', 'source_sha256': manifest['source_sha256'],
              'file_sha256': digest(file), 'build_items': 7, 'mesh_objects': 7,
              'hardware_included': False, 'parts': parsed, 'separation_pairs': pairs}
    output.mkdir(parents=True, exist_ok=True)
    (output / f'{version}-independent-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    return {'version': version, 'passed': True, 'reader_warnings': 0, 'mesh_objects': 7,
            'max_readback_coordinate_error_mm': max(r['readback_rigid_coordinate_error_mm'] for r in parsed)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--plates', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--versions', nargs='+', default=['v2', 'v3', 'v4'])
    args = ap.parse_args()
    print(json.dumps([verify(args.repo, args.plates, v, args.output) for v in args.versions], indent=2))
