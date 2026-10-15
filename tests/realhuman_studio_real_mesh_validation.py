"""Manual real-human mesh validation helper for RealHuman Studio.

Usage:
1. Download the CC0 Human Base Meshes bundle documented in REALHUMAN_STUDIO_ASSET_SOURCES.md.
2. In Blender, append/drag a full-body human mesh into a scene and select that mesh.
3. Open this script in Blender's Text Editor and Run Script.
4. Inspect the JSON report beside the current .blend file and visually inspect the mesh.

The script records evaluated geometry at negative and positive slider extremes, then
restores all shape-key values. This is a diagnostic aid, not a proof of anatomical
quality; silhouette, volume preservation, and garment intersections still need GUI review.
"""
import json
import math
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


def finite_vector(vector):
    return all(math.isfinite(float(value)) for value in vector)


def evaluated_mesh_metrics(obj):
    """Return evaluated local-space vertex metrics and clean up the temporary mesh."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = obj.evaluated_get(depsgraph)
    evaluated_mesh = evaluated_obj.to_mesh()
    try:
        coords = [vertex.co.copy() for vertex in evaluated_mesh.vertices]
        ensure(all(finite_vector(co) for co in coords),
               "Evaluated mesh contains non-finite vertex coordinates.")
        if not coords:
            return {"vertex_count": 0, "changed_vertices_from_basis": 0,
                    "max_displacement_from_basis": 0.0, "dimensions": [0.0, 0.0, 0.0]}
        basis_coords = [vertex.co.copy() for vertex in obj.data.shape_keys.key_blocks[0].data]
        ensure(len(coords) == len(basis_coords),
               "Evaluated topology changed; cannot compare per-vertex shape-key deltas safely.")
        deltas = [(coords[i] - basis_coords[i]).length for i in range(len(coords))]
        min_v = [min(float(co[axis]) for co in coords) for axis in range(3)]
        max_v = [max(float(co[axis]) for co in coords) for axis in range(3)]
        return {
            "vertex_count": len(coords),
            "changed_vertices_from_basis": sum(1 for delta in deltas if delta > 1e-6),
            "max_displacement_from_basis": max(deltas, default=0.0),
            "dimensions": [max_v[axis] - min_v[axis] for axis in range(3)],
        }
    finally:
        evaluated_obj.to_mesh_clear()


obj = bpy.context.active_object
ensure(obj is not None and obj.type == "MESH",
       "Select the full-body human mesh as the active object before running this script.")
ensure(len(obj.data.vertices) >= 100,
       "The active mesh has fewer than 100 vertices; select a real human mesh, not a primitive test object.")
ensure(obj.data.shape_keys is None or len(obj.data.shape_keys.key_blocks) >= 1,
       "The mesh has an invalid shape-key datablock.")

result = bpy.ops.rh_studio.generate_body_proportion_keys()
ensure("FINISHED" in result,
       "RealHuman Studio could not generate/update the body-proportion controls on this mesh.")

shape_keys = obj.data.shape_keys
ensure(shape_keys is not None, "No shape-key datablock was created.")
blocks = shape_keys.key_blocks
original_values = {key.name: float(key.value) for key in blocks}
original_active_index = shape_keys.key_blocks.active_index
report = {
    "schema": "realhuman_studio_real_mesh_validation_v2",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "blender_version": bpy.app.version_string,
    "object": obj.name,
    "source_blend": bpy.data.filepath,
    "mesh": {
        "vertices": len(obj.data.vertices),
        "edges": len(obj.data.edges),
        "polygons": len(obj.data.polygons),
        "dimensions_object_units": [float(value) for value in obj.dimensions],
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
        "If modifiers change evaluated topology, per-vertex comparison is rejected rather than guessed.",
    ],
}

try:
    # Compare each control independently so unrelated controls' existing values
    # cannot hide or exaggerate the effect being measured.
    for name in CONTROL_NAMES:
        key = blocks.get(name)
        ensure(key is not None, "Missing expected body-proportion control: " + name)
        for other in blocks:
            other.value = 0.0

        key.value = 0.0
        bpy.context.view_layer.update()
        basis_metrics = evaluated_mesh_metrics(obj)

        key.value = -1.0
        bpy.context.view_layer.update()
        negative_metrics = evaluated_mesh_metrics(obj)

        key.value = 1.0
        bpy.context.view_layer.update()
        positive_metrics = evaluated_mesh_metrics(obj)

        ensure(negative_metrics["max_displacement_from_basis"] > 1e-6,
               "Negative slider extreme produced no measurable change: " + name)
        ensure(positive_metrics["max_displacement_from_basis"] > 1e-6,
               "Positive slider extreme produced no measurable change: " + name)
        ensure(all(math.isfinite(float(value))
                   for metrics in (basis_metrics, negative_metrics, positive_metrics)
                   for value in metrics["dimensions"]),
               "Non-finite dimensions found while evaluating " + name)

        mask_name = "RH遮罩 | " + name.split(" | ", 1)[-1]
        report["controls"].append({
            "name": name,
            "slider_min": float(key.slider_min),
            "slider_max": float(key.slider_max),
            "negative_extreme": negative_metrics,
            "positive_extreme": positive_metrics,
            "mask_group": mask_name if obj.vertex_groups.get(mask_name) else None,
            "positive_and_negative_both_change_mesh": True,
        })
finally:
    for key in blocks:
        key.value = original_values.get(key.name, 0.0)
    shape_keys.key_blocks.active_index = original_active_index
    bpy.context.view_layer.update()

output_path = bpy.path.abspath("//realhuman_studio_real_mesh_validation.json")
with open(output_path, "w", encoding="utf-8") as report_file:
    json.dump(report, report_file, ensure_ascii=False, indent=2, allow_nan=False)

print("REALHUMAN_STUDIO_REAL_MESH_VALIDATION: PASS")
print("Object: %s | vertices: %d | report: %s" %
      (obj.name, len(obj.data.vertices), output_path))
for item in report["controls"]:
    print("%s: negative max delta %.6g; positive max delta %.6g" %
          (item["name"],
           item["negative_extreme"]["max_displacement_from_basis"],
           item["positive_extreme"]["max_displacement_from_basis"]))
