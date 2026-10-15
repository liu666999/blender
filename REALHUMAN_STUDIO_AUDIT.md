# RealHuman Studio — Implementation Audit

**Audit date:** 2026-10-14  
**Source branch:** `feature/realhuman-studio-phase1`  
**Scope:** Source-level review of `scripts/addons_core/realhuman_studio/`, the smoke-test script, and the workflow. This is not a claim that a full Blender GUI session or a Windows build has been tested.

## Project records

- [Project goals and task report](REALHUMAN_STUDIO_TASK_REPORT.md) — long-term vision, current phase, acceptance criteria and priorities.
- [Completed features](REALHUMAN_STUDIO_COMPLETED.md) — implemented capabilities and their verified boundaries.
- [Unfinished work](REALHUMAN_STUDIO_TODO.md) — missing features, manual validation and release tasks.

## Status legend

- **Implemented in source:** an operator or UI path exists in the checked-in code.
- **Headless smoke coverage:** the CI script exercises the path through Blender's Python API.
- **Needs visual/manual validation:** behavior depends on actual geometry, user interaction, GPU drawing, or deformation quality.
- **Not implemented:** no complete implementation was found in this phase.

## Implemented in source

| Area | Status | Notes |
|---|---|---|
| Project folders and JSON manifest | Implemented; smoke-tested | Creates models, anatomy, clothing, textures, exports, logs and `realhuman_project.json`. |
| Asset import and category collections | Implemented in source | Supports OBJ, FBX, GLB/GLTF, STL and PLY when the matching importer exists in the Blender build. |
| Asset import history and batch identity | Implemented; helper smoke-tested | Successful imports stamp each imported object with a batch ID and timestamp, and append source path, file size/mtime, category, object names/types and batch identity to an existing `realhuman_project.json` using an atomic replacement. If no project manifest exists, the import still keeps per-object metadata and reports that history was not written. |
| Selected asset audit report | Implemented; smoke-tested | Writes JSON diagnostics for selected objects: world bounds, dimensions in Blender units and estimated meters, source-file existence, import batch metadata, mesh counts, UV layers, materials, shape keys, armature links, loose geometry and non-manifold edges. Flags stale source paths, armature modifiers without targets, near-zero axes and heuristic size outliers (under 5 mm or over 20 m). Size flags are review prompts only because scene units and asset intent may be unknown; non-manifold edges can also be intentional on open garment borders. |
| Missing-source candidate scan | Implemented; smoke-tested | Recursively indexes supported source files under a chosen directory, finds same-filename/same-extension candidates for broken object paths, ranks file-size matches using project import history, and writes a JSON preview report. It never changes object paths or project history. |
| Batch repair from candidate report | Implemented; smoke-tested | Confirmation dialog revalidates unique same-name/same-extension/exact-size candidates against current object metadata and exactly one matching project-history batch. Only safe records are applied; ambiguous, changed, missing, conflicting, or inconsistent records are skipped. Updates object metadata and project history with atomic manifest replacement; does not reload geometry. Writes `logs/missing_source_repair_results.json` with per-object `repaired`/`skipped`/`failed` status, a reason code/message, candidate path, and expected/actual file sizes. Result writing is atomic and attempted for both successful repairs and rejected-only runs; manifest-write failure leaves object source paths untouched and records the failure where possible. |
| Repair result viewer | Implemented; automated helper/operator smoke tests added | Sidebar opens the result JSON, filters all/repaired/skipped/failed records, displays per-object reason and expected/actual sizes, and offers clipboard buttons for old and candidate paths. Shows up to 30 matching rows per dialog and reports when more remain in the full JSON. Tests cover filtering, malformed rows, valid/unsupported/missing report files, operator registration, and exact clipboard contents in Blender background mode. Graphical dialog rendering still needs manual Windows UI acceptance. |
| Source-file relinking | Implemented; smoke-tested | Relinks selected imported objects to an existing replacement source file, requires compatible extensions, rejects mixed import batches, and updates the matching `realhuman_project.json` batch with the new path, size, mtime and relink timestamp using an atomic file replacement. This only repairs source-path metadata; it does not reload or replace the current geometry. |
| Whole-project integrity audit | Implemented; smoke test added | Scans all objects in the current .blend, summarizes missing source files, missing armature targets, missing UVs/materials, suspicious dimensions and missing import-batch IDs, and cross-checks `realhuman_project.json` for missing source paths or object names absent from the current file. Writes `logs/project_integrity.json` by default when the configured project folder exists. Object-name history warnings are advisory because users may legitimately rename objects. |
| Selected asset manifest export | Implemented; smoke test added | Exports a portable `realhuman_studio_asset_manifest_v1` JSON document with Blender version, scene unit scale, source path/category, collections, world bounds and dimensions converted to meters, mesh/UV/material/shape-key statistics, armature references, and warnings when a linked armature is outside the selection. Metric conversion uses the scene unit scale and does not infer unknown source-file units. |
| Asset dimension and unit diagnosis | Implemented; smoke-tested | Writes world-space bounds, per-object dimensions/scales, scene unit settings, and heuristic meter/centimeter/millimeter interpretations to JSON. It never changes transforms; unit guesses are not authoritative because imported assets may have arbitrary coordinate conventions. |
| Selected asset position normalization | Implemented; smoke-tested | Non-destructively translates the selected object group so its X/Y bounds are centered and/or its lowest Z point sits at zero. Mesh coordinates and object scale are preserved; it does not infer real-world units or correct model orientation. |
| Category selection, visibility and reassignment | Implemented in source | Uses Blender collections and object metadata. |
| Height calibration | Implemented; unit conversion smoke-tested | Converts the target height in meters through the scene's `scale_length`, places the active mesh bottom at world Z=0, and rejects invalid unit scales. It changes only the active mesh object—not its armature, sibling meshes, or clothing—so use on a bound character requires care; it is not anatomy-aware proportion editing. |
| Selected-group height calibration | Implemented; multi-object and safety smoke tests added | Applies a uniform world-space scale to selected objects as a group, converts target meters through `scale_length`, and places the group's bottom at Z=0. It now cancels if a selected mesh references an armature modifier or armature parent that was not selected, avoiding a common partial-scale failure. Users must still select all clothing and other related assets; constraint-driven and complex rig setups require GUI validation. |
| Body proportion shape keys | Implemented; smoke test added | Generates reusable shoulder-width, chest-depth/width, waist, and hip-width shape keys with -1..+1 sliders. Uses smooth vertical weighting on a single upright Z-up mesh; it is a first-stage generic deformation, not anatomy-aware sculpting or a guarantee of realistic results on every topology. |
| Shape-key controls and reset | Implemented in source | Controls shape keys already present in the imported mesh. |
| GLB, FBX and OBJ export | Implemented in source | Depends on the exporter operator being available in the build. |
| Procedural fabric print | Implemented; shader construction smoke-tested | Dots, stripes or checker pattern with UV, object-local or generated coordinates; X/Y placement and scale controls; in Edit Mode, assigns the material only to selected faces. This is regional material assignment, not a full texture-painting or garment-pattern system. |
| Bounding-box-based simple humanoid rig | Implemented; rig-generation smoke-tested | Dialog exposes hip/knee/shoulder height ratios, shoulder half-width, and arm reach. These remain coarse initial estimates; final deformation quality is not certified by headless tests. |
| Starter poses and keyframe insertion | Implemented; smoke-tested | Keys local location, the active rotation representation, and scale for every pose bone. Existing Actions retain their names; only a newly created Action is named `RealHuman Motion`. |
| Selected-bone rotation editor | Implemented; headless smoke-tested | Sets local XYZ rotation on the active pose bone and can insert a rotation keyframe at the current frame; requires Pose Mode and an active bone selection. GUI discoverability and usability still need manual validation. |
| Named single-pose presets | Implemented; smoke-tested | Stored in the current scene as JSON custom data. |
| Named full-action sets | Implemented in source; smoke test added | Duplicates an animation Action in the current .blend file. When a same-named saved Action is still used by another object, the save path now creates a numbered copy rather than deleting that shared Action. |
| Basic action-sequence checks | Implemented in source; smoke test added | Checks Action existence, frame range, one-frame clips and current-frame range; it does not judge animation quality. |
| Action JSON import/export | Implemented in source; smoke-tested | Samples local bone transforms per integer frame; converts the active local rotation matrix so Euler-animated bones are not exported with stale quaternion values; rejects unsupported rotation encodings on import; validates optional source-FPS metadata and warns on a mismatch without silently changing scene FPS. Not a lossless serialization of constraints, drivers, or NLA. |
| Standard views and body-facing presets | Implemented in source; smoke-tested | GUI context and actual view orientation still need manual checks. |
| Simple limb-clearance warning | Implemented in source; smoke-tested | A small set of bone-point distance heuristics, not mesh collision detection. |
| Shape-key-based expression/body reactions | Implemented in source | Requires imported models to contain suitably named shape keys; it does not create facial anatomy or muscles. |
| Minimal 2D stick-pose overlay | Implemented in source | Circle head, simple body/limbs and four draggable endpoints; the interactive modal overlay requires GUI testing. |

## Not implemented or still incomplete

- No bundled production-ready human base mesh, realistic skin material/texture library, anatomy meshes, or complete asset catalog.
- No complete procedural human generator, muscle/fat controls, or anatomical retopology. The new shoulder/chest/waist/hip shape keys are only a first-stage proportion tool.
- No complete anatomy simulation: toggles organize imported assets but do not generate bones, muscles, nerves, vessels, or organs.
- No robust garment pattern drafting, brush-based region painting, decal placement with arbitrary surface projection, or clothing simulation system. Regional face selection and coordinate-based procedural print placement are now available as a limited first step.
- No true 2D-to-3D inverse kinematics, joint-length solving, motion retargeting, contact-aware animation, or reliable mesh-collision solving.
- No visual quality guarantee for automatic skin weights, facial expressions, anatomical alignment, or mesh deformation.
- No standalone application shell, installer, Windows executable/package, custom scripting console, or full Python-like project execution environment beyond Blender's existing facilities.
- No third-party anatomy asset import pipeline with automated license review, semantic anatomy naming, unit conversion, or coordinate-system alignment. The selected-asset JSON audit is diagnostic only. Position normalization only translates the selected group; it does not apply transforms, infer real-world units, or correct model orientation.

## Known risks and manual validation checklist

1. Run the latest GitHub Actions workflow and confirm the Blender runtime smoke test reaches its explicit PASS marker, including import-history recording, per-item missing-source repair result reports, selected-asset and whole-project missing-source/rig-link diagnostics, Action-name preservation, and scale-keyframe checks.
2. In the actual GUI, register the add-on, generate the new shoulder/chest/waist/hip controls on an upright human mesh, and inspect for unwanted deformation; then check that the RealHuman sidebar draws without errors; enter Pose Mode, select a bone, adjust local XYZ rotation, and test optional keyframing.
3. Generate a rig from a representative human mesh; inspect bone positions, parenting, roll, and any automatic-weight deformation.
4. Test the 2D pose overlay from the sidebar in front, side, and perspective views; drag every endpoint, navigate with middle mouse/wheel, record multiple frames, and play the result back.
5. Save, close, and reopen a .blend file; confirm named pose presets and action sets remain available.
6. Test action-set name collisions with two rigs, confirm the existing shared Action remains assigned, and check frame playback after loading.
7. Check shader appearance for UV, object and generated coordinates on real garments; verify selected-face material assignment and exports in a separate viewer.
8. Test asset importers/exporters individually in the exact Blender build intended for daily use.

## Test interpretation

The headless smoke script exercises Python API paths, not real mouse input, GPU overlay rendering, visual rig quality, or Windows packaging. A successful smoke test is necessary but not sufficient for release readiness. Items marked as source-implemented must not be interpreted as visually verified unless a GUI test has actually been performed.

## Current recommendation

Continue in small, testable increments: validate the first-stage body proportion controls on real human topology, then add region-aware proportion drivers, unit/orientation-aware asset normalization and repair tools, better rig deformation, and the missing clothing/anatomy workflows. Keep bundled third-party assets as a separate, license-reviewed milestone.
