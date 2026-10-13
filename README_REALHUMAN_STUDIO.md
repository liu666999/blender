# RealHuman Studio — Phase 1

RealHuman Studio is being developed inside this Blender source fork as a focused human-modeling workspace. The initial implementation deliberately builds on Blender's existing viewport, mesh, material, shape-key, rigging, and import/export systems rather than replacing them.

## Implemented in this phase

The add-on source lives in scripts/addons_core/realhuman_studio.

- Create a project folder layout (models, anatomy, clothing, textures, exports, logs) and a realhuman_project.json manifest.
- Import OBJ, FBX, GLB/GLTF, STL, and PLY assets into a chosen category, if the corresponding importer is available in the build.
- Create a collection hierarchy for base body, skin, bones, muscles, organs, nerves, vessels, clothing, rig, and other resources.
- Toggle category visibility and select all objects in a category.
- Move selected objects to a category.
- Uniformly scale the active mesh to a target world-space height and shift the bottom to Z=0.
- Expose existing shape-key sliders and reset non-Basis shape keys.
- Export selected objects to GLB, FBX, or OBJ, subject to exporter availability.
- Switch between front, back, left, right, top, and bottom views.
- Generate and assign a UV-based procedural fabric-print material with dot, stripe, or checker motifs; adjustable density, sparsity, rotation, base color, and print color.
- Generate a simple stick-display humanoid armature proportioned from a selected mesh's bounding box, with optional Blender automatic weights.
- Apply starter poses (reset/T-pose, relaxed, arms-up, sitting, wave) and insert animation keyframes at the current timeline frame.
- Apply basic expression presets by matching common English/Chinese names of shape keys already present on the active mesh.

## Use

1. Build Blender from this fork using the official build instructions for your operating system.
2. Open Blender Preferences and enable RealHuman Studio from the add-on list if it is available in that build.
3. In the 3D View, press N and open the RealHuman tab.
4. Create the category scaffold, import a real human mesh, and assign anatomy meshes to the corresponding categories.

This repository commit is source code, not a prebuilt Windows installer or EXE. A Windows build has not been produced or tested by this commit. CI performs Python syntax checks only; it does not compile Blender or exercise its UI.

## Not yet implemented

- No human mesh, skeleton, anatomy mesh collection, or skin textures are bundled in this phase. The fabric-print operator generates a procedural material; it is not a bundled library of textile assets.
- Shape controls reveal morphs already present in a model; the tool does not yet generate a parameterized human body from scratch.
- Height calibration is a scale operation, not anatomical retopology or proportion-aware reshaping.
- The app still runs on the Blender host UI; a finished standalone RealHuman Studio startup template and Windows packaging are future work.
- The asset repositories need a separate license-aware download, coordinate alignment, naming, and integration pass. Do not treat Git LFS pointer text as model data.
- The procedural fabric-print material and simple rig/pose helpers have been added to source but still need in-Blender runtime tests, including weight deformation, bone orientation, pose quality, shape-key name matching, node-socket compatibility, and different UV layouts.
- The Blender C/C++ core is untouched in this phase.

## License

New RealHuman Studio source files in this folder are licensed under GPL-3.0-or-later, as suitable for modifications distributed alongside Blender. Licenses for any later third-party assets must be reviewed separately and retained.
