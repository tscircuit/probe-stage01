"""Emit and independently validate each full faceted component X_T."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import time
from compare_validation import compare

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inputs',type=Path,required=True)
parser.add_argument('--mesh-dir',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--bun',default='bun')
parser.add_argument('--validation-python',required=True)
parser.add_argument('--workers',type=int,default=3)
args=parser.parse_args()
tools=Path(__file__).resolve().parent
steps=sorted(args.inputs.glob('*.step'))
if len(steps)!=48: raise ValueError(f'Expected 48 component STEP files, found {len(steps)}')
args.output.joinpath('parts').mkdir(parents=True,exist_ok=True)
args.output.joinpath('reports').mkdir(parents=True,exist_ok=True)

def run(command):
    result=subprocess.run(command,text=True,capture_output=True,timeout=1800)
    if result.returncode: raise RuntimeError(result.stderr[-8000:] or result.stdout[-8000:])
    return result.stdout.strip()

def job(step):
    start=time.perf_counter(); name=step.stem
    mesh=args.mesh_dir/(name+'.mesh.json')
    source=json.loads(mesh.read_text())
    if source['source_step_sha256']!=hashlib.sha256(step.read_bytes()).hexdigest():
        raise ValueError('Source STEP changed since mesh extraction')
    xt=args.output/'parts'/(name+'.faceted.x_t')
    report=args.output/'reports'/(name+'.json')
    preview=args.mesh_dir/(name+'.readback.glb')
    if not xt.exists(): run([args.bun,'run',str(tools/'export_mesh.ts'),str(mesh),str(xt)])
    xt_sha256=hashlib.sha256(xt.read_bytes()).hexdigest()
    cached_report=json.loads(report.read_text()) if report.exists() else {}
    source_mesh_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest()
    if cached_report.get('input_xt_sha256')!=xt_sha256 or cached_report.get('source_mesh_sha256')!=source_mesh_sha256 or not cached_report.get('surface_correspondence',{}).get('valid'):
        run([args.validation_python,str(tools/'validation'/'parasolid-to-glb.py'),str(xt),str(preview),'--report',str(report),'--source-mesh',str(mesh)])
    result=compare(mesh,report,xt)
    result['seconds']=time.perf_counter()-start
    print(json.dumps({'name':name,'passed':True,'seconds':result['seconds'],'bytes':result['bytes'],'triangles':result['input_triangles']}),flush=True)
    return result

results=[]; failures=[]
with ThreadPoolExecutor(max_workers=args.workers) as executor:
    jobs={executor.submit(job,step):step for step in steps}
    for future in as_completed(jobs):
        step=jobs[future]
        try: results.append(future.result())
        except Exception as error:
            failures.append({'name':step.stem,'error':str(error)})
            print(json.dumps({'name':step.stem,'passed':False,'error':str(error)}),flush=True)
summary={'format':'native Parasolid X_T with planar facets','faceted':True,'exact_analytic_step_retained_separately':True,
         'native_siemens_or_shapr3d_import_verified':False,'expected_parts':48,'passed_parts':len(results),'failed_parts':len(failures),
         'tessellation':{'linear_deflection_mm':0.025,'angular_deflection_radians':0.1},'validation':'Each actual X_T read with parasolid-kit 0.3.5; complete OCCT solid; healing disabled; all faces tessellated; closed oriented mesh; volume/area/bounds compared with whole source tessellation',
         'parts':sorted(results,key=lambda item:item['name']),'failures':failures}
args.output.joinpath('validation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'finished':True,'passed':len(results),'failed':len(failures)}),flush=True)
if failures: raise SystemExit(1)
