"""Package only successfully validated native faceted X_T component files."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('version',choices=['v1','v2'])
parser.add_argument('directory',type=Path)
parser.add_argument('--inputs',type=Path,required=True)
args=parser.parse_args()
root=args.directory
summary=json.loads((root/'validation.json').read_text())
binding=json.loads((root/'source_binding.json').read_text())
passed=summary['parts']
if len(passed)!=summary['passed_parts']: raise ValueError('Validation manifest count mismatch')
expected={part['name'] for part in passed}
available={path.name.removesuffix('.faceted.x_t') for path in (root/'parts').glob('*.x_t')}
if available!=expected: raise ValueError('Parts directory must contain exactly validated successful exports')
catalog_parts={}
for part in passed:
    step=args.inputs/(part['name']+'.step')
    if hashlib.sha256(step.read_bytes()).hexdigest()!=part['source_step_sha256']:
        raise ValueError('Source STEP changed before packaging')
    path=root/part['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=part['sha256']:
        raise ValueError('Native X_T changed before packaging')
    report=json.loads((root/part['independent_report']).read_text())
    if report.get('input_xt_sha256')!=part['sha256']:
        raise ValueError('Native X_T report hash binding mismatch')
    catalog_parts[part['name']]={'file':part['file'],'url':f"/faceted-parasolid/{args.version}/{part['file']}",
        'sha256':part['sha256'],'source_step_sha256':part['source_step_sha256'],'bytes':part['bytes'],'faceted':True}
unsupported={}
if (root/'unsupported.json').exists(): unsupported=json.loads((root/'unsupported.json').read_text())
for failure in summary['failures']:
    name=failure['name']; record=unsupported.setdefault(name,{'status':'unsupported','reason':failure['error']})
    record['source_step_sha256']=hashlib.sha256((args.inputs/(name+'.step')).read_bytes()).hexdigest()
if len(passed)+len(unsupported)!=48: raise ValueError('Every source component must be passed or explicitly unsupported')
(root/'unsupported.json').write_text(json.dumps(unsupported,indent=2)+'\n')
max_volume=max(abs(part['faceted_vs_exact_step']['volume_relative_change']) for part in passed)*100
max_area=max(abs(part['faceted_vs_exact_step']['surface_area_relative_change']) for part in passed)*100
max_bounds=max(part['faceted_vs_exact_step']['bounds_max_absolute_change_mm'] for part in passed)
readme=f'''# Optional faceted Parasolid reference files — {args.version}

{len(passed)} of the 48 components have independently validated native Parasolid text (`.faceted.x_t`) files. Exact analytic STEP files remain available separately for every component.

These X_T files contain closed solids with planar facets and straight edges. Cylinders, cones, circular holes, fillets, and gear curves are represented by facets. **Use the original STEP files for exact CAD geometry and manufacturing. Import into Siemens Parasolid or Shapr3D has not been verified.**

Each actual X_T file was read independently using parasolid-kit and reconstructed as one complete, valid OCCT solid, with healing disabled. Every reconstructed face is planar and is tessellated; the read-back mesh is closed and consistently oriented. Its volume, surface area, and bounds match the complete source tessellation. Each report is bound to the downloaded X_T SHA-256 and source STEP SHA-256. Files retain their original component placement and use native Parasolid metres.

The whole source STEP is tessellated at 0.025 mm linear and 0.1 radian angular deflection. At the probe cone's singular apex, OCCT emits one collapsed primitive with exactly duplicate vertex coordinates. Only this mathematically zero-area primitive is omitted; its coordinates and indices are recorded, and unchanged area, volume, bounds, and tip position are required. No STEP face or nonzero surface region is removed.

Maximum observed deviation from analytic STEP across these validated files: volume {max_volume:.6f}%, surface area {max_area:.6f}%, and axis-aligned bounds {max_bounds:.8f} mm. Per-component values appear in `validation.json`.

`catalog.json` lists only files that passed validation. `sha256_checksums.json` records the published bytes. `reports/` contains independent native read-back reports. Portable conversion and validation tools are supplied separately.

Source Python SHA-256: `{binding['source_sha256']}`.

## Unsupported components

'''
if unsupported:
    for name,record in sorted(unsupported.items()): readme+=f"- `{name}`: {record['reason']}\n"
else: readme+='None: all 48 components passed the native read-back checks.\n'
enhanced=sum(bool(part.get('surface_correspondence',{})) for part in passed)
if enhanced:
    readme+=f'''\n## Additional surface correspondence\n\n{enhanced} files also passed an independent comparison of every source triangle and every reconstructed planar face. For each supporting plane, the complete source and native surface regions agree in area and reciprocal full-region coverage within 0.00001 mm. Supporting-plane offset and normal agreement are checked separately. Floating point T-junctions can create numerical internal seams, so trim-boundary identity is not claimed; diagnostic boundary distance is not an acceptance criterion.\n'''
(root/'README.md').write_text(readme)
bundle_name=f'probe-stage-{args.version}-faceted-parasolid.zip'
with zipfile.ZipFile(root/bundle_name,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for relative in ['README.md','validation.json','source_binding.json','unsupported.json']:
        archive.write(root/relative,relative)
    for part in passed:
        archive.write(root/part['file'],part['file'])
        archive.write(root/part['independent_report'],part['independent_report'])
bundle={'file':bundle_name,'url':f'/faceted-parasolid/{args.version}/{bundle_name}','sha256':hashlib.sha256((root/bundle_name).read_bytes()).hexdigest(),'bytes':(root/bundle_name).stat().st_size}
catalog={'public_version':args.version,'source_sha256':binding['source_sha256'],'source_file':binding['source_file'],'format':'native faceted Parasolid X_T','faceted':True,'native_siemens_import_verified':False,'expected_parts':48,'passed_parts':len(passed),'unsupported_parts':unsupported,'parts':catalog_parts,'bundle':bundle,'validation':{'file':'validation.json','url':f'/faceted-parasolid/{args.version}/validation.json','sha256':hashlib.sha256((root/'validation.json').read_bytes()).hexdigest()},'readme':{'file':'README.md','url':f'/faceted-parasolid/{args.version}/README.md'}}
(root/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
checksums={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob('*')) if path.is_file() and path.name!='sha256_checksums.json'}
(root/'sha256_checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
print(json.dumps({'version':args.version,'validated_parts':len(passed),'unsupported':list(unsupported),'bundle':bundle,'source_sha256':binding['source_sha256']}))
