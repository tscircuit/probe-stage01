# Native X_T validation and visual snapshots

These tests read the actual exported `.x_t` through the independent
[parasolid-kit](https://github.com/monozukuri-ai/parasolid-kit) parser, reconstruct
an OpenCascade B-Rep, check topology/volume/bounds without healing, and tessellate
that B-Rep to GLB. PoppyGL renders two PNG snapshots: an upper/front view and an
opposite lower/rear view. They do not render the source JSCAD mesh as a
substitute for testing the exported file.

OpenCascade does not read Parasolid directly; parasolid-kit supplies the X_T
reader and conversion. Its supported format subset is sufficient for the planar
solids this package writes. This is useful independent validation, but it does
not certify native Siemens Parasolid or Shapr3D compatibility.

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/validation/requirements.txt
bun test tests/visual
```

Set `PARASOLID_PYTHON` to use another Python environment containing the pinned
requirements. CI must install these requirements and run the visual tests; a
missing native dependency is a failure, not a skipped success.

```sh
# Deliberate snapshot updates; inspect every changed PNG before committing.
BUN_UPDATE_SNAPSHOTS=1 bun test tests/visual

# Convert an exported model for inspection outside the test runner.
.venv/bin/python scripts/validation/parasolid-to-glb.py model.x_t model.glb \
  --report report.json
```

The script assumes native X_T coordinates are meters, as written by
`parasolidts`, and reports OCCT measurements in millimeters (area in mm² and
volume in mm³). GLB coordinates follow glTF's meter convention.

Test artifacts (`model.x_t`, `model.glb`, `report.json`, `model.png`,
`model-opposite.png`, and a `diff*.png` on mismatch) are kept under
`tests/visual/.artifacts/`. Tracked PNG baselines are in
`tests/visual/__snapshots__/`. The 16-model suite compares source JSCAD surface
area, volume, and dimensions with independently reconstructed OCCT solids.
It covers reflected/translated boxes (including class-based canonical
reserialization), holes, assemblies, electronics, sheet metal, spur/helical/worm
gears, and NEMA8/NEMA17 motors. Exact catalog parameters and visible features
are listed in `tests/fixtures/catalog-models.ts`.

The indexed triangles in the actual GLB undergo a separate audit: every expected
body and face must be present, each body must have closed and consistently
oriented edges, normals must agree with winding, and triangles must have nonzero
area. Mesh surface area and signed volume must match the OCCT measurements
within float32 precision. Corruption regressions check that missing faces,
inverted winding/normals, and non-manifold edges fail validation.

The GLB artifact remains in meters. PoppyGL 0.0.30 clamps its camera near plane
to 0.01 world units, which cuts away small meter-unit electronics. For rendering
only, the scene is centered and uniformly scaled to a fixed extent; buffers and
the exported GLB stay unchanged. Both cameras fit the complete bounding box,
and every vertex must lie inside all six camera clipping planes before a
snapshot is accepted. Regression tests reproduce the old clipping and require
complete previews to be invariant across millimeter, meter, and micron scales.

Native body and face colors are decoded independently from standard
`SDL/TYSA_COLOUR_2` / `SDL/TYSA_COLOUR` attributes in the emitted `.x_t`. The
preview uses OCCT provenance to assign those colors to the corresponding GLB
faces, with face overrides taking precedence. It receives no source-color
sidecar. Native RGB values and the applied palette are recorded in
`report.json`; this exporter's JSCAD/CSS sRGB values are converted to glTF
linear material factors.
Colorless native files retain the default preview material.

The pinned PoppyGL dependency includes a small Bun patch for coplanar depth
ties. Float32 NDC interpolation and depth storage can disagree by round-off,
causing stripes where the legacy DFN housing and pads both end at Z=0. Within
a normalized-depth tolerance of `2^-22`, the later primitive supplies the color
while the nearest stored depth is retained, preventing cumulative drift.
Surfaces farther away by more than that budget remain occluded. This changes
rasterization only; the emitted
X_T, GLB vertices, topology, and native colors are unchanged. Colorless DFN pads
keep their fallback material.
