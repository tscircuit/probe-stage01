# Reproduce the optional faceted Parasolid exports

These tools read each original STEP file and export the **complete tessellation** as a native Parasolid text (`.faceted.x_t`) boundary representation. Every curved surface and edge becomes planar facets and straight segments. Exact analytic STEP files remain the source CAD files.

The native X_T is read independently by `parasolid-kit`, reconstructed as an OCCT B-Rep with healing disabled, and checked for complete conversion, one valid closed solid shell, positive volume, only planar surfaces and straight edges, and tessellation of every face. The generated read-back mesh is audited for closed, consistently oriented edges. Its volume, area, and bounds are compared against the entire source tessellation. The report also measures deviation from analytic STEP. The current converter additionally checks every source triangle against every reconstructed native planar face, grouped by supporting plane: source and native surface regions must agree in area and reciprocal whole-region coverage within 0.00001 mm. Supporting-plane offsets and normals are checked separately. Numerical T-junction seams make trim-boundary identity unsuitable as an acceptance test; reported boundary distance is diagnostic only.

**Import into Siemens Parasolid or Shapr3D has not been verified.** This is independent structural and geometric validation of native text files, not native-kernel certification.

## Dependencies

Use Bun 1.4.0 or a compatible release. The JavaScript runtime dependencies are pinned in `package.json`. The vendored converter is MIT-licensed `jscad-to-parasolid` 0.0.4 at commit `fb38ea65d925781a750b8f631f313da4ffd0b3b5`; its original license and README are preserved. It uses npm `parasolidts` 0.0.2. The independent validator is pinned in `validation/requirements.txt`.

Use separate Python environments for source geometry and independent validation because they use different OCCT versions:

```sh
bun install
python -m venv .venv-geometry
.venv-geometry/bin/python -m pip install build123d==0.10.0 cadquery-ocp==7.8.1.1.post1
python -m venv .venv-validation
.venv-validation/bin/python -m pip install -r validation/requirements.txt
```

## Run

Run from this tools directory. Set `PARTS_DIR` to the version's directory of 48 exact STEP component files. `MESH_DIR` and `EXPORT_DIR` must be fresh output directories.

```sh
PARTS_DIR=/path/to/exact-step-parts
MESH_DIR=/path/to/intermediate-meshes
EXPORT_DIR=/path/to/faceted-parasolid-output
.venv-geometry/bin/python tessellate_all.py "$PARTS_DIR" "$MESH_DIR"
.venv-geometry/bin/python run_exports.py --inputs "$PARTS_DIR" --mesh-dir "$MESH_DIR" --output "$EXPORT_DIR" --bun bun --validation-python "$PWD/.venv-validation/bin/python" --workers 2
```

The tessellator uses 0.025 mm linear deflection and 0.1 radian angular deflection. Coordinates remain in each STEP component's original assembly placement; X_T stores metres. Source hashes prevent validation against a different STEP file. All geometric source triangles are passed to the writer. OCCT emits one collapsed, exactly zero-area primitive at the probe's conical apex; only primitives with exactly coincident vertex coordinates are omitted. Each is recorded with its original indices and coordinates, and unchanged area, volume, and bounds are required. No STEP face or nonzero surface region is removed.

The script writes one X_T and independent report per component plus `validation.json`. It returns a nonzero status if any component fails. Files from failed or incomplete jobs must not be published. Use the original STEP for exact dimensions, cylindrical mating surfaces, and manufacturing workflows.
