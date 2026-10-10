"""Read one STEP solid and retain its full tessellation for faceted export."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from build123d import import_step


def mesh_metrics(vertices, triangles):
    # Work about the mesh center to avoid cancellation for translated parts.
    center = [sum(v[i] for v in vertices)/len(vertices) for i in range(3)]
    volume_terms, area_terms = [], []
    for triangle in triangles:
        a, b, c = [[vertices[j][i]-center[i] for i in range(3)] for j in triangle]
        u, w = [[b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]]
        cross = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]]
        area_terms.append(math.sqrt(sum(x*x for x in cross))/2)
        bc = [b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0]]
        volume_terms.append(sum(a[i]*bc[i] for i in range(3))/6)
    return {'volume_mm3':math.fsum(volume_terms), 'surface_area_mm2':math.fsum(area_terms),
            'bounding_box': [min(v[i] for v in vertices) for i in range(3)]+[max(v[i] for v in vertices) for i in range(3)]}


def extract(input_path, output_path):
    start=time.perf_counter()
    shape=import_step(input_path)
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError('Source STEP must be a valid, single solid')
    bounds=shape.bounding_box()
    vertices,triangles=shape.tessellate(0.025,0.1)
    vertices=[list(vertex) for vertex in vertices]
    triangles=[list(triangle) for triangle in triangles]
    raw_triangle_count=len(triangles)
    zero_area_primitives=[]
    faithful_triangles=[]
    for index,triangle in enumerate(triangles):
        coordinates=[tuple(vertices[vertex]) for vertex in triangle]
        if len(set(coordinates))<3:
            # OCCT emits one collapsed primitive at a cone's singular apex.
            # Coincident coordinates make its surface area identically zero;
            # this does not remove any geometric region or STEP face.
            zero_area_primitives.append({'raw_triangle_index':index,'vertex_indices':triangle,'coordinates':[list(value) for value in coordinates],'reason':'exactly coincident vertices; mathematically zero area'})
        else:
            faithful_triangles.append(triangle)
    before=mesh_metrics(vertices,triangles)
    triangles=faithful_triangles
    metrics=mesh_metrics(vertices,triangles)
    if before != metrics:
        raise ValueError('Zero-area primitive normalization changed geometric metrics')
    if metrics['volume_mm3'] <= 0:
        raise ValueError('Source triangulation must have positive signed volume')
    data={'name':input_path.stem,'source_step':str(input_path),'source_step_sha256':hashlib.sha256(input_path.read_bytes()).hexdigest(),
          'units':'mm','linear_deflection_mm':0.025,'angular_deflection_radians':0.1,'analytic':{'volume_mm3':shape.volume,
          'surface_area_mm2':shape.area,'bounding_box':list(bounds.min)+list(bounds.max)},'mesh':metrics,'vertices':vertices,'triangles':triangles,
          'raw_triangle_count':raw_triangle_count,'zero_area_primitives':zero_area_primitives,'step_faces_excluded':0}
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(json.dumps({'name':input_path.stem,'vertices':len(vertices),'triangles':len(triangles),'seconds':time.perf_counter()-start}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    extract(args.input,args.output)


if __name__=='__main__':
    main()
