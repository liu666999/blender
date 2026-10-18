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
import bmesh

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


def evaluated_mesh_metrics(obj, reference_coords=None):
    """Return evaluated geometry metrics and coordinates, cleaning up temporary mesh data."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = obj.evaluated_get(depsgraph)
    evaluated_mesh = evaluated_obj.to_mesh()
    try:
        coords = [vertex.co.copy() for vertex in evaluated_mesh.vertices]
        ensure(all(finite_vector(co) for co in coords),
               "Evaluated mesh contains non-finite vertex coordinates.")
        if not coords:
            metrics = {"vertex_count": 0, "changed_vertices_from_reference": 0,
                       "max_displacement_from_reference": 0.0, "dimensions": [0.0, 0.0, 0.0]}
            return metrics, coords
        deltas = []
        if reference_coords is not None:
            ensure(len(coords) == len(reference_coords),
                   "Evaluated modifier topology changed between shape-key states; cannot compare safely.")
            deltas = [(coords[i] - reference_coords[i]).length for i in range(len(coords))]
        min_v = [min(float(co[axis]) for co in coords) for axis in range(3)]
        max_v = [max(float(co[axis]) for co in coords) for axis in range(3)]
        metrics = {
            "vertex_count": len(coords),
            "changed_vertices_from_reference": sum(1 for delta in deltas if delta > 1e-6),
            "max_displacement_from_reference": max(deltas, default=0.0),
            "dimensions": [max_v[axis] - min_v[axis] for axis in range(3)],
        }
        return metrics, coords
    finally:
        evaluated_obj.to_mesh_clear()


obj = bpy.context.active_object
ensure(obj is not None and obj.type == "MESH",
       "Select the full-body human mesh as the active object before running this script.")
ensure(len(obj.data.vertices) >= 100,
       "The active mesh has fewer than 100 vertices; select a real human mesh, not a primitive test object.")
ensure(obj.data.shape_keys is None or len(obj.data.shape_keys.key_blocks) >= 1,
       "The mesh has an invalid shape-key datablock.")

def topology_diagnostics(mesh):
    """Measure mesh integrity without pretending to certify anatomical quality."""
    vertex_count = len(mesh.vertices)
    edge_count = len(mesh.edges)
    polygon_count = len(mesh.polygons)
    used_vertices = set()
    parent = list(range(vertex_count))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for edge in mesh.edges:
        left, right = edge.vertices
        used_vertices.add(left)
        used_vertices.add(right)
        union(left, right)

    component_roots = {find(index) for index in used_vertices}
    zero_area_faces = [poly.index for poly in mesh.polygons if poly.area <= 1e-12]
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        boundary_edges = sum(1 for edge in bm.edges if edge.is_boundary)
        non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
    finally:
        bm.free()
    polygons_without_material = []
    used_material_indices = set()
    for poly in mesh.polygons:
        if poly.material_index < 0 or poly.material_index >= len(mesh.materials):
            polygons_without_material.append(poly.index)
        else:
            used_material_indices.add(poly.material_index)

    uv_layers = list(mesh.uv_layers)
    uv_face_coverage = {}
    for layer in uv_layers:
        covered_faces = 0
        for poly in mesh.polygons:
            if poly.loop_total >= 3 and all(
                    layer.data[loop_index].uv is not None for loop_index in poly.loop_indices):
                covered_faces += 1
        uv_face_coverage[layer.name] = {
            "faces_with_uvs": covered_faces,
            "faces_total": polygon_count,
            "coverage_ratio": covered_faces / polygon_count if polygon_count else 0.0,
        }

    shape_key_ranges = []
    if mesh.shape_keys:
        for key in mesh.shape_keys.key_blocks:
            shape_key_ranges.append({
                "name": key.name,
                "slider_min": float(key.slider_min),
                "slider_max": float(key.slider_max),
                "value": float(key.value),
            })

    warnings = []
    if vertex_count == 0 or polygon_count == 0:
        warnings.append("Mesh has no usable surface geometry.")
    if zero_area_faces:
        warnings.append("Mesh contains zero-area polygons.")
    if not uv_layers:
        warnings.append("Mesh has no UV layer.")
    if polygon_count and not used_material_indices:
        warnings.append("No polygon references a valid material slot.")
    if len(component_roots) > 1:
        warnings.append("Mesh contains multiple disconnected vertex components; review whether intentional.")
    return {
        "vertices": vertex_count,
        "edges": edge_count,
        "polygons": polygon_count,
        "connected_components": len(component_roots),
        "loose_vertices": vertex_count - len(used_vertices),
        "boundary_edges": boundary_edges,
        "non_manifold_edges": non_manifold_edges,
        "zero_area_polygon_count": len(zero_area_faces),
        "zero_area_polygon_indices_sample": zero_area_faces[:100],
        "uv_layer_count": len(uv_layers),
        "uv_face_coverage": uv_face_coverage,
        "material_slots": len(mesh.materials),
        "material_slots_used_by_polygons": sorted(used_material_indices),
        "polygons_with_invalid_material_index": len(polygons_without_material),
        "shape_keys": shape_key_ranges,
        "warnings": warnings,
    }


obj = bpy.context.active_object
ensure(obj is not None and obj.type == "MESH",
       "Select the full-body human mesh as the active object before running this script.")
ensure(len(obj.data.vertices) >= 100,
       "The active mesh has fewer than 100 vertices; select a real human mesh, not a primitive test object.")
ensure(len(obj.data.polygons) > 0,
       "The selected mesh has no polygons; select a surface mesh rather than an empty mesh object.")
ensure(obj.data.shape_keys is None or len(obj.data.shape_keys.key_blocks) >= 1,
       "The mesh has an invalid shape-key datablock.")

result = bpy.ops.rh_studio.generate_body_proportion_keys()
ensure("FINISHED" in result,
       "RealHuman Studio could not generate/update the body-proportion controls on this mesh.")

shape_keys = obj.data.shape_keys
ensure(shape_keys is not None, "No shape-key datablock was created.")
blocks = shape_keys.key_blocks
original_values = {key.name: float(key.value) for key in blocks}
original_active_index = obj.active_shape_key_index
report = {
    "schema": "realhuman_studio_real_mesh_validation_v2",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "blender_version": bpy.app.version_string,
    "object": obj.name,
    "source_blend": bpy.data.filepath,
    "mesh": {
        "topology": topology_diagnostics(obj.data),
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
        "Connected components and material/UV coverage are diagnostics only; multiple components may be intentional.",
        "Topology warnings must be reviewed manually; they do not automatically mean the asset is unusable.",
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
        basis_metrics, baseline_coords = evaluated_mesh_metrics(obj)

        key.value = -1.0
        bpy.context.view_layer.update()
        negative_metrics, _ = evaluated_mesh_metrics(obj, baseline_coords)

        key.value = 1.0
        bpy.context.view_layer.update()
        positive_metrics, _ = evaluated_mesh_metrics(obj, baseline_coords)

        ensure(negative_metrics["max_displacement_from_reference"] > 1e-6,
               "Negative slider extreme produced no measurable change: " + name)
        ensure(positive_metrics["max_displacement_from_reference"] > 1e-6,
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
    obj.active_shape_key_index = original_active_index
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
           item["negative_extreme"]["max_displacement_from_reference"],
           item["positive_extreme"]["max_displacement_from_reference"]))
