Probe stage — compact release v3

Compact end mount for a Ø44 mm microscope, 100 mm working distance, 40 mm straight vertical probe travel and a 60° probe approach. The external collet holds a 6 mm shank; only the probe enters the projected barrel corridor. The projected footprint is a clearance assumption, not a measured lens field of view. The motor rear faces tangentially away from the barrel into open space. A 42 × 42 × 20 mm controller volume plus 2 mm clearance is reserved behind it. The rear-facing footprint remains unobstructed throughout travel; actual controller, heatsink and cable geometry and mass are not modeled.

Drive: module 1; 20° pressure angle; 20-tooth pinion engaging 40 internal teeth in a 180° slot on a virtual 80-tooth ring. Ratio 4:1; wheel OD 96 mm; crank radius 22.5 mm; rod pivot spacing 88 mm.

Hardware: 625ZZ bearings (5 × 16 × 5 mm), M5 structural and pivot hardware, and M3 motor mounting screws. Use smooth precision Ø5 mm bearing running sections with M5 threads outside the races. Standard Ø6 mm shoulder bolts do not fit. Verify actual heads, axle stack, motor dimensions and manufacturing allowances.

All 48 components are valid single solids and passed STEP roundtrip checks. No intersections at 41 checked poses; Ø44 projected barrel corridor clear of non-probe parts. Each pose includes all 1128 component pairs, with no excluded parts or regions. The alternative full-length Ø6 mm probe was checked against every other component. The independent continuous optical report validates the final world-space transform. Physical collision checks are sampled; strength, stiffness, backlash and print fit need physical validation. Independent continuous bounds verify the controller allowance and rear access against all 48 modeled components throughout the stroke.

The bundle includes 48 component STEP files, 7 printable-part STLs, assembly STEP/GLB, source, requirements, viewer geometry, manifest, checksums and all verification and mass/moment comparison reports. Mass and static moment values are estimates under the report assumptions. Optional faceted x_t addons are supplied separately; exact STEP preserves precision geometry. STEP/STL files share assembly placement; arrange STL orientations for manufacture.

Collision report threshold: positive volume >1e-5 mm³. Tangent contact is allowed, including the lowered probe tip on the plate. No material or load test is represented.

Regenerate: install requirements.txt and run python probe_stage_v3.py --out ./regenerated. Changing parameters or geometry requires renewed clearance and structural validation.

The mass/moment comparison report preserves its assumptions and both source hashes. It estimates gravity loading and does not establish clamp capacity or deflection.
