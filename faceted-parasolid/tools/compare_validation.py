"""Require the actual X_T read-back to retain the complete source mesh."""
import hashlib
import json
import math
from pathlib import Path


def compare(mesh_path, report_path, xt_path):
    source=json.loads(Path(mesh_path).read_text())
    report=json.loads(Path(report_path).read_text())
    xt_sha256=hashlib.sha256(Path(xt_path).read_bytes()).hexdigest()
    if report.get('input_xt_sha256') != xt_sha256:
        raise ValueError('Independent report is not bound to this exact X_T file; revalidate it')
    surface=report.get('surface_correspondence')
    if surface is not None:
        if report.get('source_mesh_sha256')!=hashlib.sha256(Path(mesh_path).read_bytes()).hexdigest():
            raise ValueError('Full surface report is not bound to this source mesh')
        if not surface['valid'] or not surface['all_source_triangles_compared'] or not surface['all_readback_faces_compared']:
            raise ValueError('Whole surface correspondence is incomplete')
    for label,metrics,volume_key,area_key in [('source mesh',source['mesh'],'volume_mm3','surface_area_mm2'),('exact STEP',source['analytic'],'volume_mm3','surface_area_mm2'),('X_T read-back',report['metrics'],'volume','surface_area')]:
        for key in [volume_key,area_key]:
            value=metrics[key]
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<=0:
                raise ValueError(f'{label} {key} must be a finite positive number')
        bounds=metrics['bounding_box']
        if not isinstance(bounds,list) or len(bounds)!=6 or any(isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) for value in bounds):
            raise ValueError(f'{label} bounding box must have exactly six finite numbers')
        if any(bounds[i]>=bounds[i+3] for i in range(3)):
            raise ValueError(f'{label} bounding box must have positive extent on every axis')
    if not report['conversion_complete'] or not report['occt_valid'] or not report['source_complete']:
        raise ValueError('Independent X_T reader failed full valid conversion')
    if report['output_topology'].get('solids')!=1 or report['output_topology'].get('shells')!=1:
        raise ValueError('Independent X_T read-back must contain exactly one closed solid shell')
    if set(report['input_surface_kinds'])!={'plane'} or set(report['input_curve_kinds'])!={'line'}:
        raise ValueError('Expected only native planar surfaces and straight edges')
    if report['healing']['requested'] or report['healing']['performed']:
        raise ValueError('Healing must remain disabled')
    if report['preview']['missing_face_count'] or not report['mesh_validation']['valid']:
        raise ValueError('Read-back must tessellate all faces to a closed, consistently oriented mesh')
    original=source['mesh']; actual=report['metrics']; analytic=source['analytic']
    volume_error=abs(actual['volume']/original['volume_mm3']-1)
    area_error=abs(actual['surface_area']/original['surface_area_mm2']-1)
    bounds_error=max(abs(a-b) for a,b in zip(actual['bounding_box'],original['bounding_box']))
    if volume_error>1e-7 or area_error>1e-7 or bounds_error>1e-5:
        raise ValueError(f'X_T differs from complete source tessellation: volume={volume_error}, area={area_error}, bounds={bounds_error}')
    return {'name':source['name'],'file':f"parts/{source['name']}.faceted.x_t",'source_step_sha256':source['source_step_sha256'],
            'sha256':xt_sha256,'bytes':Path(xt_path).stat().st_size,
            'passed':True,'faceted':True,'occt_valid':True,'healing_performed':False,'native_siemens_import_verified':False,
            'input_triangles':len(source['triangles']),'input_vertices':len(source['vertices']),'output_faces':report['output_topology']['faces'],
            'raw_source_triangles':source.get('raw_triangle_count',len(source['triangles'])),
            'zero_area_primitives_removed':source.get('zero_area_primitives',[]),'step_faces_excluded':0,
            'surface_correspondence':surface,
            'exact_step':analytic,'source_tessellation':original,'xt_readback':actual,
            'readback_vs_source_mesh':{'volume_relative_error':volume_error,'area_relative_error':area_error,'bounds_max_absolute_error_mm':bounds_error},
            'faceted_vs_exact_step':{'volume_relative_change':actual['volume']/analytic['volume_mm3']-1,
            'surface_area_relative_change':actual['surface_area']/analytic['surface_area_mm2']-1,
            'bounds_max_absolute_change_mm':max(abs(a-b) for a,b in zip(actual['bounding_box'],analytic['bounding_box']))},
            'independent_report':f"reports/{source['name']}.json",'all_faces_tessellated':True,'closed_oriented_mesh':True}
