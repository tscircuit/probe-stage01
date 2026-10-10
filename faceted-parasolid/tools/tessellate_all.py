"""Generate all component meshes without changing any source CAD artifact."""
import argparse
from pathlib import Path
from tessellate_step import extract

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('input',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
paths=sorted(args.input.glob('*.step'))
if len(paths)!=48:
    raise ValueError(f'Expected 48 STEP parts, found {len(paths)}')
for path in paths:
    output=args.output/(path.stem+'.mesh.json')
    if output.exists():
        continue
    extract(path,output)
