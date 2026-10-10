# Optional faceted Parasolid reference files — v3

48 of the 48 components have independently validated native Parasolid text (`.faceted.x_t`) files. Exact analytic STEP files remain available separately for every component.

These X_T files contain closed solids with planar facets and straight edges. Cylinders, cones, circular holes, fillets, and gear curves are represented by facets. **Use the original STEP files for exact CAD geometry and manufacturing. Import into Siemens Parasolid or Shapr3D has not been verified.**

Each actual X_T file was read independently using parasolid-kit and reconstructed as one complete, valid OCCT solid, with healing disabled. Every reconstructed face is planar and is tessellated; the read-back mesh is closed and consistently oriented. Its volume, surface area, and bounds match the complete source tessellation. Each report is bound to the downloaded X_T SHA-256 and source STEP SHA-256. Files retain their original component placement and use native Parasolid metres.

The whole source STEP is tessellated at 0.025 mm linear and 0.1 radian angular deflection. At the probe cone's singular apex, OCCT emits one collapsed primitive with exactly duplicate vertex coordinates. Only this mathematically zero-area primitive is omitted; its coordinates and indices are recorded, and unchanged area, volume, bounds, and tip position are required. No STEP face or nonzero surface region is removed.

Maximum observed deviation from analytic STEP across these validated files: volume 0.069590%, surface area 0.043090%, and axis-aligned bounds 0.01245720 mm. Per-component values appear in `validation.json`.

`catalog.json` lists only files that passed validation. `sha256_checksums.json` records the published bytes. `reports/` contains independent native read-back reports. Portable conversion and validation tools are supplied separately.

Source Python SHA-256: `50220ccf93c48d7941de36998c6a1734a7201ec2bed9ff2e1670b82bd65be8b6`.

## Unsupported components

None: all 48 components passed the native read-back checks.

## Additional surface correspondence

48 files also passed an independent comparison of every source triangle and every reconstructed planar face. For each supporting plane, the complete source and native surface regions agree in area and reciprocal full-region coverage within 0.00001 mm. Supporting-plane offset and normal agreement are checked separately. Floating point T-junctions can create numerical internal seams, so trim-boundary identity is not claimed; diagnostic boundary distance is not an acceptance criterion.
