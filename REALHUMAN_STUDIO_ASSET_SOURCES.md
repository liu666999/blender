# RealHuman Studio — Real Human Mesh Validation Asset

## Primary validation asset

- **Asset:** Blender Studio / community Human Base Meshes, version **v1.4.1**
- **Official listing:** https://www.blender.org/download/demo-files/
- **Direct download:** https://mirror.blender.org/demo/asset-bundles/human-base-meshes/human-base-meshes-bundle-v1.4.1.zip
- **License shown by the official listing:** CC0
- **Bundle size listed by Blender:** approximately 49 MB
- **Minimum Blender version listed:** Blender 4.2 or newer
- **Why selected:** includes realistic and stylized human base meshes intended for sculpting, modeling, texturing, rigging, and simulation; avoids adding a large binary asset to this source repository.

Do not treat the bundle's CC0 label as applying to unrelated third-party assets downloaded elsewhere. Re-check the official listing and the bundle's own asset descriptions when selecting a specific mesh.

## Manual validation procedure

1. Download and unpack the official bundle from the source above.
2. Add one full-body realistic human mesh to a new Blender scene using the asset library workflow described by the bundle.
3. Enable the RealHuman Studio add-on and select the full-body mesh as the active object.
4. Run `tests/realhuman_studio_real_mesh_validation.py` from Blender's Text Editor.
5. Review `realhuman_studio_real_mesh_validation.json` beside the current `.blend` file.
6. In the GUI, set each shoulder/chest/waist/hip control to -1, 0, and +1. Inspect silhouette, mesh pinching, volume loss, intersections, UV/material stability, and whether the selected mesh's local axes match the tool's upright Z-up assumption.
7. If clothing and a rig are present, test them separately; this script does not certify clothing collision, skinning, or rig quality.

## Status and limitations

The validation helper records mesh topology counts, dimensions, UV layers, materials, modifiers, vertex groups, and evaluated mesh metrics at each control's negative and positive slider extremes. It restores all shape-key values that were present before the measurements. It is a diagnostic report, not a visual-quality score. Running it creates or updates the four RealHuman Studio shape keys on the selected mesh. Save a copy of the scene first.

**Current status:** source and license candidate identified; automated helper added. The asset has not been downloaded into this environment, and no real-human Blender GUI run has yet been performed. Do not mark real-human deformation quality as passed until the report and screenshots from an actual run are reviewed.
