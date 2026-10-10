# Optional faceted Parasolid reference files — v1

47 of the 48 components have independently validated native Parasolid text (`.faceted.x_t`) files. Exact analytic STEP files remain available separately for every component.

These X_T files contain closed solids with planar facets and straight edges. Cylinders, cones, circular holes, fillets, and gear curves are represented by facets. **Use the original STEP files for exact CAD geometry and manufacturing. Import into Siemens Parasolid or Shapr3D has not been verified.**

Each actual X_T file was read independently using parasolid-kit and reconstructed as one complete, valid OCCT solid, with healing disabled. Every reconstructed face is planar and is tessellated; the read-back mesh is closed and consistently oriented. Its volume, surface area, and bounds match the complete source tessellation. Each report is bound to the downloaded X_T SHA-256 and source STEP SHA-256. Files retain their original component placement and use native Parasolid metres.

The whole source STEP is tessellated at 0.025 mm linear and 0.1 radian angular deflection. At the probe cone's singular apex, OCCT emits one collapsed primitive with exactly duplicate vertex coordinates. Only this mathematically zero-area primitive is omitted; its coordinates and indices are recorded, and unchanged area, volume, bounds, and tip position are required. No STEP face or nonzero surface region is removed.

Maximum observed deviation from analytic STEP across these validated files: volume 0.055414%, surface area 0.040916%, and axis-aligned bounds 0.01383056 mm. Per-component values appear in `validation.json`.

`catalog.json` lists only files that passed validation. `sha256_checksums.json` records the published bytes. `reports/` contains independent native read-back reports. Portable conversion and validation tools are supplied separately.

Source Python SHA-256: `728df35c034453cf4d31f964c829f9c01d7d9ba7d5cd8efbed7b714e1e1e1d84`.

## Unsupported components

- `frame_front_clamp`: Complete source tessellation contains two coincident junction edges with four incident nonzero triangles; planar exporter requires a closed orientable two-face-per-edge mesh. Original STEP is preserved. No faces are omitted and no partial/cropped X_T is supplied.
