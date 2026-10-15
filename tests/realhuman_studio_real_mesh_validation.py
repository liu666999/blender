"""Manual real-human mesh validation helper for RealHuman Studio.

Usage:
1. Download the CC0 Human Base Meshes bundle documented in REALHUMAN_STUDIO_ASSET_SOURCES.md.
2. In Blender, append/drag a full-body human mesh into a scene and select that mesh.
3. Open this script in Blender's Text Editor and Run Script.
4. Inspect the JSON report beside the current .blend file and visually inspect the mesh.

This is a manual visual-validation aid, not a headless CI fixture or proof of anatomical quality.
"""
import json
import math
import os
from datetime import datetime, timezone

import bpy

CONTROL_NAMES = (
    "RH体型 | 肩宽",
    "RH体型 | 胸围",
    "RH体型 | 腰围",
    "RH体型 | 臀宽",
)


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def vector_is_finite(vector):
    return all(math.isfinite(float(value)) for value in vector)


obj = bpy.context.active_object
ensure(obj is not None and obj.type == "MESH",
       "Select the full-body human mesh as the active object before running this script.")
ensure(len(obj.data.vertices) >= 100,
       "The active mesh has fewer than 100 vertices; select a real human mesh, not a primitive test object.")

result = bpy.ops.rh_studio.generate_body_proportion_keys()
ensure("FINISHED" in result,
       "RealHuman Studio could not generate/update the body-proportion controls on this mesh.")

shape_keys = obj.data.shape_keys
ensure(shape_keys is not None, "No shape-key datablock was created.")
blocks = shape_keys.key_blocks
basis = blocks[0]
report = {
    "schema": "realhuman_studio_real_mesh_validation_v1",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "blender_version": bpy.app.version_string,
    "object": obj.name,
    "source_blend": bpy.data.filepath,
    "mesh": {
        "vertices": len(obj.data.vertices),
        "edges": len(obj.data.edges),
        "polygons": len(obj.data.polygons),
        "dimensions_local_object_units": [float(value) for value in obj.dimensions],
        "uv_layers": [layer.name for layer in obj.data.uv_layers],
        "materials": [slot.material.name if slot.material else None
                      for slot in obj.material_slots],
        "modifiers": [{"name": modifier.name, "type": modifier.type}
                      for modifier in obj.modifiers],
        "vertex_groups": [group.name for group in obj.vertex_groups],
        "shape_key_count": len(blocks),
    },
    "controls": [],
    "warnings": [
        "Automated coordinate metrics do not judge anatomy, silhouette, volume preservation, or visual quality.",
        "Inspect the mesh at positive and negative slider values and check clothing intersections in the GUI.",
    ],
}

for name in CONTROL_NAMES:
    key = blocks.get(name)
    ensure(key is not None, "Missing expected body-proportion control: " + name)
    deltas = [(key.data[index].co - basis.data[index].co).length
              for index in range(len(obj.data.vertices))]
    ensure(all(math.isfinite(float(delta)) for delta in deltas),
           "Non-finite deformation values found in " + name)
    changed = sum(1 for delta in deltas if delta > 1e-6)
    max_delta = max(deltas, default=0.0)
    ensure(changed > 0 and max_delta > 1e-6,
           "The control produced no measurable vertex change: " + name)
    report["controls"].append({
        "name": name,
        "slider_min": float(key.slider_min),
        "slider_max": float(key.slider_max),
        "changed_vertices": changed,
        "changed_vertex_ratio": changed / max(1, len(obj.data.vertices)),
        "max_displacement_object_units": max_delta,
        "mask_group": "RH遮罩 | " + name.split(" | ", 1)[-1]
                      if obj.vertex_groups.get("RH遮罩 | " + name.split(" | ", 1)[-1])
                      else None,
    })

output_path = bpy.path.abspath("//realhuman_studio_real_mesh_validation.json")
with open(output_path, "w", encoding="utf-8") as report_file:
    json.dump(report, report_file, ensure_ascii=False, indent=2)

print("REALHUMAN_STUDIO_REAL_MESH_VALIDATION: PASS")
print("Object: %s | vertices: %d | report: %s" %
      (obj.name, len(obj.data.vertices), output_path))
for item in report["controls"]:
    print("%s: changed %d/%d vertices; max delta %.6g" %
          (item["name"], item["changed_vertices"], len(obj.data.vertices),
           item["max_displacement_object_units"]))
