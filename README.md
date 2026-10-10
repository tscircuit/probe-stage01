# Probe stage 01

A parametric build123d microscope probe lift with an interactive 3D inspector and component CAD downloads.

Release **v1** preserves the current inspected design and every exported file unchanged before the compact redesign. The archived CAD files retain their original `v3` filenames: that is the design's internal revision, while `v1` is this repository's first release. Future versions belong in separate directories so the baseline remains accessible.

## Open the preserved model

From the repository root:

```sh
python -m http.server 8000 --directory versions/v1/site
```

Open <http://localhost:8000/>. The viewer supports motion, camera presets, component selection, visibility, isolation, exploded view, optical projection, and individual STEP downloads. Its JavaScript dependencies are included locally.

The complete [CAD bundle](versions/v1/site/downloads/microscope_probe_lift_v3.zip), [assembly STEP](versions/v1/site/downloads/slider_crank_v3_assembly.step), [build123d source](versions/v1/site/downloads/slider_crank_v3.py), and [individual parts](versions/v1/site/downloads/parts/) are preserved under `versions/v1/site/downloads/`.

## Release v1 geometry

| Property | Preserved value |
| --- | --- |
| Microscope cylinder | Ø44 mm; nominal split-clamp bore 44.4 mm |
| Working distance | 100 mm from barrel end to specimen |
| Probe motion | 40 mm straight vertical travel |
| Probe angle | 60° above the specimen plate |
| Drive | NEMA17, 20-tooth module 1 pinion, 6:1 ratio |
| Internal gear | 60 teeth in a 180° slot on a virtual 120-tooth ring |
| Wheel / crank / rod | 136 mm OD / 25 mm radius / 110 mm pivot spacing |
| Bearings | Four 625ZZ, 5 × 16 × 5 mm |
| Fasteners | M5 structure and pivots; four M3 motor screws |
| Exports | 48 component STEP files, 7 printable-part STLs, assembly STEP and GLB |

The external collet holds a 6 mm shank at world X=45 mm. The custom 104 mm metal probe reference has a pointed tip, a 1 mm stem through the first 60 mm, a taper from 60–70 mm, and a 6 mm shank from 70–104 mm. Only the probe enters the Ø44 mm projected barrel corridor; printed parts remain outside it. This projected footprint is a clearance assumption, not a measured microscope field of view.

Use a smooth precision Ø5 mm running section through the bearing inner races, with M5 threads outside the races. Standard Ø6 mm shoulder bolts do not fit these bearings. Verify actual fastener heads, stack lengths, motor dimensions, and manufacturing tolerances before building.

## Verification and limits

The preserved reports record 48 valid single solids, successful STEP roundtrips, and no positive-volume intersections at 41 checked poses. Every component pair was included: 1,128 pairs per pose and 46,248 pair checks overall. The audit also checks an alternative full-length Ø6 mm probe envelope against every other component. Its sampled minimum gap to the front clamp is approximately 1.885 mm.

Separate conservative bounds keep all seven printed parts outside the projected optical corridor throughout the prescribed vertical motion; those bounds were checked against a 24 mm radius corridor. The all-pairs physical collision audit is sampled and does not prove clearance at every intermediate pose. Geometry validation does not establish strength, stiffness, load capacity, backlash, or practical print fit.

The [verification summary](versions/v1/site/downloads/geometry_verification.json), [all-pairs report](versions/v1/site/downloads/v3_all_pairs.json), [optical bounds](versions/v1/site/downloads/optical_bounds.json), and [STEP roundtrip report](versions/v1/site/downloads/step_roundtrip_checks.json) retain their original contents. Historical absolute paths inside reports record their generation location.

Run the repository's read-only integrity and report checks with Python's standard library:

```sh
python tools/verify_release.py --release v1
```

This verifies every archived Site file against `versions/v1/SNAPSHOT.json`, download checksums, the CAD source hash, component counts, STEP headers, ZIP integrity, and the saved audit results. It does not regenerate CAD or rerun the geometric audit.

## Regenerate without changing the archive

Use Python 3.11 or newer and install the preserved build123d version in a virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r versions/v1/site/downloads/requirements.txt
python versions/v1/site/downloads/slider_crank_v3.py --out regenerated/v1
```

The default export pose is lowered specimen contact. `--angle` selects the crank angle in degrees within approximately ±53.130102354°. `--working-distance` changes the specimen offset and requires a new clearance audit. Exported STEP and STL files retain assembly placement; orient STLs for manufacture in the slicer.

Portable audit helpers write new reports outside the immutable archive:

```sh
python tools/audit_all_pairs.py --source versions/v1/site/downloads/slider_crank_v3.py --output regenerated/v1_all_pairs.json --frames 41 --workers 3
python tools/optical_bounds.py --source versions/v1/site/downloads/slider_crank_v3.py --output regenerated/v1_optical_bounds.json
```

Both helpers accept explicit source and output paths. Their defaults resolve the v1 source relative to the scripts and write reports under `regenerated/` in the current working directory. Altering parameters or geometry requires renewed validation.

Genuine Parasolid `x_t` files are not included because the prototype environment had no licensed writer. Import the STEP files into a CAD tool with a Parasolid exporter to create them.

The vendored Three.js license remains with its files at `versions/v1/site/assets/vendor/LICENSE-three.txt`. No project license has been selected.
