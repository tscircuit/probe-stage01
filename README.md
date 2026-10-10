# Probe stage 01

A parametric build123d microscope probe lift with an interactive 3D inspector and component CAD downloads.

The current **v3** turns the NEMA17 rear face into open space for its back-mounted controller and heatsink while keeping the motor close to the microscope. All releases retain a Ø44 mm end clamp, 40 mm straight vertical travel, a probe at 60° to the specimen plate, 100 mm working distance, 625ZZ bearings, and M5 structural hardware. Compact v2 and v3 use a ribbed frame, perimeter rim, and two short struts.

[Open the interactive viewer](https://microscope-probe-inspector.seveibar.chatgpt.site/?version=v3), or inspect the preserved [v1](https://microscope-probe-inspector.seveibar.chatgpt.site/?version=v1) and [v2](https://microscope-probe-inspector.seveibar.chatgpt.site/?version=v2). The version selector changes the geometry and all component downloads. Git tags and release pages retain each version separately.

To run the current viewer locally from the repository root:

```sh
python -m http.server 8000
```

Open <http://localhost:8000/>. Everything required by the viewer is included locally.

## V3: open motor rear

The motor axis runs tangentially to the microscope. Its rear points away from the barrel into an unobstructed corridor. A **42 × 42 × 20 mm controller reservation**, plus **2 mm clearance**, sits behind the rear face. Continuous bounds verify that the entire 46 × 46 mm rear footprint remains open behind that reservation throughout travel. The viewer's **Motor rear** preset and controller annotation show the reserved space. This reservation represents clearance, not actual electronics or heatsink CAD.

The motor center stays **46.01 mm** from the microscope axis, compared with 44.24 mm in v2. Short upper braces connect the drive frame to the end clamp and clear the carriage throughout its stroke. The 96 mm crank wheel retains the internal teeth in its 180° slot, the 80/20 virtual ring and pinion combination, and the 4:1 reduction. Only the metal probe enters the projected optical corridor.

| Estimate | v1 | v2 | v3 |
| --- | ---: | ---: | ---: |
| Printed solid volume | 436.19 cm³ | 158.11 cm³ | 156.57 cm³ |
| Stage mass | 938.55 g | 583.11 g | 581.16 g |
| Peak gravity bending moment | 0.81722 N·m | 0.32335 N·m | 0.31669 N·m |

V3's estimated stage gravity moment is **61.25% below v1 and 2.06% below v2**. These estimates use PETG at 1.27 g/cm³ and 100% solid-equivalent printed volume, an assumed 280 g motor, modeled steel hardware, 5 g bearings, and the metal probe. **Controller, heatsink, and cable mass are unknown and excluded**; the microscope and specimen are excluded. The moment is the vector sum of mass first moments about the barrel axis over the full stroke. These estimates do not establish stiffness or load capacity.

Download the [v3 CAD bundle](versions/v3/site/downloads/probe_stage_v3.zip), [assembly STEP](versions/v3/site/downloads/probe_stage_v3_assembly.step), [build123d source](versions/v3/site/downloads/probe_stage_v3.py), or [individual parts](versions/v3/site/downloads/parts/). The separate [controller envelope](versions/v3/site/downloads/references/motor_controller_reserved_envelope.step) and [clearance envelope](versions/v3/site/downloads/references/motor_controller_clearance_keepout.step) are reference STEP solids, excluded from the 48-component assembly and mass estimates.

Validation includes **46,248 unrestricted component-pair checks at 41 poses**, with no positive-volume intersections, all 48 valid single solids, and clearance for an alternative full-length Ø6 mm probe. Continuous bounds verify the optical exclusion, controller reservation, and open rear corridor. Component and assembly STEP roundtrips pass. Physical assembly collision checks are sampled; strength, stiffness, backlash and print fit require physical validation. Read the [collision audit](versions/v3/site/downloads/all_pairs.json), [controller clearance certificate](versions/v3/site/downloads/controller_clearance.json), [optical bounds](versions/v3/site/downloads/optical_bounds.json), [STEP roundtrip report](versions/v3/site/downloads/step_roundtrip_checks.json), and [mass comparison](versions/v3/site/downloads/mass_moment_comparison.json).

The [actual browser validation reports](validation/v3/) bind the served source, model and viewer hashes to real component vertex buffers, transforms and controller-overlay bounds. They also cover all three preserved versions, motion, mobile layout, component STEP downloads, and all v3 faceted x_t downloads.

```sh
python tools/verify_release.py --release v3
python -m pip install -r versions/v3/site/downloads/requirements.txt
python versions/v3/site/downloads/probe_stage_v3.py --out regenerated/v3
```

## Compact v2

| Property | v1 | v2 |
| --- | ---: | ---: |
| Crank wheel outside diameter | 136 mm | 96 mm |
| Virtual internal ring / pinion | 120 / 20 teeth | 80 / 20 teeth |
| Actual teeth in 180° slot | 60 | 40 |
| Reduction ratio | 6:1 | 4:1 |
| Crank radius / rod pivot spacing | 25 / 110 mm | 22.5 / 88 mm |
| Gear face thickness | 8 mm | 6 mm |
| Printed solid volume | 436.19 cm³ | 158.11 cm³ |
| Estimated solid-equivalent assembly mass | 938.55 g | 583.11 g |
| Peak estimated gravity bending moment | 0.81722 N·m | 0.32335 N·m |
| Motor centre-of-mass radial distance | 60.71 mm | 44.24 mm |

This is **63.75% less printed volume, 37.87% less estimated mass, and 60.43% lower estimated gravity bending moment**. The estimates use PETG at 1.27 g/cm³ and 100% solid-equivalent volume, the same assumed 280 g motor, 5 g per bearing, and modeled steel hardware. They include the metal probe and exclude the microscope and specimen. The moment uses the vector sum of component mass first moments about the vertical barrel axis; its peak was found with 401 crank-angle samples and numerical refinement. A uniform 60% printed-material sensitivity gives 716.96 → 502.79 g and 0.59428 → 0.27012 N·m. These fractions describe assumed material volume, not slicer infill percentages.

The drive plane rotates 90° around the microscope axis so the motor sits beside the barrel. The same 6 mm external collet position and metal probe preserve the view and approach angle. The front frame and crank wheel each lose about 70% of their solid volume. Ribs, short struts and the second axle support retain a connected load path; stiffness and strength require physical validation.

Download the [v2 CAD bundle](versions/v2/site/downloads/probe_stage_v2.zip), [assembly STEP](versions/v2/site/downloads/probe_stage_v2_assembly.step), [build123d source](versions/v2/site/downloads/probe_stage_v2.py), or [individual parts](versions/v2/site/downloads/parts/). The [independent mass comparison](versions/v2/site/downloads/mass_moment_comparison.json) records the assumptions and sensitivity cases.

V2 validation covers all 48 valid single solids at 41 positions: 46,248 unrestricted assembly-pair checks with zero positive-volume intersections. The full-length Ø6 mm alternative probe clears every other component. Continuous world-space bounds keep all 47 nonprobe parts outside the projected optical corridor throughout travel, including a 2 mm radial margin. Component and assembly STEP roundtrips pass. The measured rear-clamp/frame closure gap is 0.8 mm. Physical collisions were sampled; these checks do not establish stiffness or load capacity. See the [collision audit](versions/v2/site/downloads/all_pairs.json), [optical bounds](versions/v2/site/downloads/optical_bounds.json), and [roundtrip report](versions/v2/site/downloads/step_roundtrip_checks.json).

```sh
python tools/verify_release.py --release v2
python -m pip install -r versions/v2/site/downloads/requirements.txt
python versions/v2/site/downloads/probe_stage_v2.py --out regenerated/v2
```

Exports use the lowered contact pose. V2's supported crank range is approximately ±62.734°. Changes to geometry, working distance or the drive-plane layout require renewed checks.

## Frozen baseline

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

Both helpers accept explicit source and output paths. The optical helper derives the world transform and supports both released layouts. Altering parameters or geometry requires renewed validation.

The independent gravity estimator can be rerun on either source:

```sh
python tools/gravity_moment.py --source versions/v1/site/downloads/slider_crank_v3.py --out regenerated/v1_gravity.json
python tools/gravity_moment.py --source versions/v2/site/downloads/probe_stage_v2.py --out regenerated/v2_gravity.json
```

## Optional faceted Parasolid downloads

All 48 v3 and v2 components and 47 of 48 v1 components have native text Parasolid files labeled **Faceted x_t** in the current viewer. Curves, cylindrical seats and holes are approximated with planar facets and straight edges. Use the exact STEP files for precision CAD and manufacturing. Import into Siemens Parasolid or Shapr3D has not been verified.

Download the [v3 faceted bundle](faceted-parasolid/v3/probe-stage-v3-faceted-parasolid.zip), [v2 faceted bundle](faceted-parasolid/v2/probe-stage-v2-faceted-parasolid.zip), or [v1 faceted bundle](faceted-parasolid/v1/probe-stage-v1-faceted-parasolid.zip). The [v3 validation report](faceted-parasolid/v3/validation.json), [v2 validation report](faceted-parasolid/v2/validation.json), and [v1 validation report](faceted-parasolid/v1/validation.json) bind every native file to its original STEP and downloaded-file hashes. An independent reader reconstructs each as a complete valid single solid with healing disabled; every face is tessellated, and its closed, oriented mesh agrees with the source tessellation. V3 also passes bidirectional whole-surface coverage checks for every component. The [v3 portable exporter and validation tools ZIP](faceted-parasolid/probe-stage-v3-faceted-tools.zip) and [earlier tools](faceted-parasolid/tools/README.md) include the converter's MIT license and source attribution.

The original v1 frame's complete tessellation has two nonmanifold junction edges that this exporter cannot represent. Its STEP remains available; its Faceted x_t button explains the limitation. The optional v1 exports are stored separately from the unchanged baseline snapshot and tag.

The vendored Three.js license remains with its files at `versions/v1/site/assets/vendor/LICENSE-three.txt`. No project license has been selected.
