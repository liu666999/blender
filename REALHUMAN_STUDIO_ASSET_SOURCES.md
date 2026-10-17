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


## Supplementary anatomy asset candidate: Écorché (bones + muscles)

- **Source:** https://github.com/Charleeh/ecorche
- **Model/download:** repository file `model/ecorche.glb` (README states about 13.7 MB); use the standard GLB, not the meshopt-compressed variant, for Blender import.
- **License:** model assets are stated in the source repository to be CC BY-SA 4.0. Required credit: “Écorché (github.com/Charleeh/ecorche), CC BY-SA 4.0. Based on BodyParts3D, © The Database Center for Life Science, CC BY 4.0, and Z-Anatomy by Gauthier Kervyn, CC BY-SA 4.0.” Distribute any modified model data under the required compatible ShareAlike terms and include the upstream notices.
- **Content claimed by upstream:** 634 named meshes; skeleton structures including 198 bones, 42 cartilages, teeth and eyes; deep and superficial muscles; a fascia sheet. Each structure has a separate named mesh, layer and side/source metadata.
- **Known gaps:** one adult male anatomical pose only; no female/child variant, no rig/poses, and it excludes organs, blood vessels, nerves, ligaments, joint capsules and skin. It complements the Human Base Meshes but cannot alone satisfy the full-character requirement.
- **Transform caution:** upstream README documents metre units, Y-up, figure facing +Z, soles on y=0, and a root scale of 0.0001. Validate the imported orientation and dimensions before any automatic transform; do not apply a blind scale to individual pieces.
- **Integration status:** research candidate only. The GLB has not been imported into the project or checked in Blender on this branch. Do not redistribute it inside the GPL source tree without retaining distinct third-party licensing and attribution.

## Resource combination strategy

Use Blender Studio Human Base Meshes v1.4.1 as the CC0 base-body candidate and Écorché as an optional CC BY-SA 4.0 skeleton/muscle source. Build each into clearly separated, named anatomy collections; store source URL, license, attribution and transforms in the project manifest. Do not assume the two assets share topology, coordinates, body proportions or compatible rigging. Organ/vessel/nerve/skin/fat/hair sources remain separate acquisition and per-asset license-review tasks. A visually aligned model is not proof that every included structure is anatomically or legally validated.
