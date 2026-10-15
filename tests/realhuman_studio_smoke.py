# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless API smoke tests for the RealHuman Studio add-on.

Run with:
  blender --background --factory-startup --python tests/realhuman_studio_smoke.py
"""
import json
import os
import sys
import tempfile
import traceback

import bpy
import bmesh
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "addons_core"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import realhuman_studio
from realhuman_studio import operators as rh_operators


def ensure(condition, message):
    if not condition:
        raise AssertionError(message)


def clean_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def run():
    expected_text = os.environ.get("RH_STUDIO_EXPECTED_BLENDER_VERSION", "").strip()
    if expected_text:
        expected = tuple(int(part) for part in expected_text.split("."))
        actual = tuple(bpy.app.version[:3])
        ensure(actual[:2] == expected[:2],
               "Runtime version %s does not match the source branch series %s." %
               (".".join(str(part) for part in actual),
                ".".join(str(part) for part in expected)))
    else:
        ensure(tuple(bpy.app.version) >= (5, 4, 0),
               "Smoke tests target the Blender version used by this source branch (5.4+).")
    realhuman_studio.register()
    ensure(hasattr(bpy.types.Scene, "rh_studio_target_height"),
           "Scene properties did not register.")
    # Result viewer filtering and validation are pure helpers, so exercise them in background CI.
    sample_results = [
        {"object_name": "A", "status": "repaired"},
        {"object_name": "B", "status": "skipped"},
        {"object_name": "C", "status": "failed"},
        "invalid-record",
    ]
    ensure([item["status"] for item in rh_operators.filter_repair_results(sample_results, "ALL")]
           == ["repaired", "skipped", "failed"],
           "Repair result viewer ALL filter did not exclude malformed rows.")
    ensure([item["object_name"] for item in rh_operators.filter_repair_results(sample_results, "skipped")]
           == ["B"],
           "Repair result viewer status filter did not isolate skipped records.")
    ensure(rh_operators.filter_repair_results(sample_results, "repaired")[0]["object_name"] == "A"
           and rh_operators.filter_repair_results(sample_results, "failed")[0]["object_name"] == "C"
           and rh_operators.filter_repair_results(sample_results, "unknown") == [],
           "Repair result viewer repaired/failed/empty filters are incorrect.")
    viewer_report_path = os.path.join(tempfile.gettempdir(), "rh_studio_viewer_report_test.json")
    with open(viewer_report_path, "w", encoding="utf-8") as stream:
        json.dump({
            "schema": "realhuman_studio_missing_source_repair_results_v1",
            "summary": {"total": 1, "repaired": 1, "skipped": 0, "failed": 0},
            "results": [{"object_name": "A", "status": "repaired"}],
        }, stream)
    ensure(rh_operators.load_repair_results_report(viewer_report_path)["results"][0]["object_name"] == "A",
           "Repair result viewer could not load a valid result report.")
    invalid_viewer_report_path = os.path.join(tempfile.gettempdir(), "rh_studio_viewer_invalid_report_test.json")
    with open(invalid_viewer_report_path, "w", encoding="utf-8") as stream:
        json.dump({"schema": "wrong", "results": []}, stream)
    try:
        rh_operators.load_repair_results_report(invalid_viewer_report_path)
    except ValueError:
        invalid_report_rejected = True
    else:
        invalid_report_rejected = False
    ensure(invalid_report_rejected, "Repair result viewer must reject an unsupported report schema.")
    try:
        rh_operators.load_repair_results_report(viewer_report_path + ".missing")
    except OSError:
        missing_report_rejected = True
    else:
        missing_report_rejected = False
    ensure(missing_report_rejected, "Repair result viewer should surface missing report files cleanly.")
    os.remove(viewer_report_path)
    os.remove(invalid_viewer_report_path)

    copy_test_path = os.path.join(tempfile.gettempdir(), "rh_studio_copy_path_test.obj")
    ensure("FINISHED" in bpy.ops.rh_studio.copy_repair_result_path(path=copy_test_path),
           "Copy repair result path operator did not finish.")
    # Headless Blender can report a successful clipboard operator while the
    # system clipboard remains unavailable. Verify dispatch here; validate the
    # actual clipboard contents in a GUI session instead.

    ensure(hasattr(bpy.ops.rh_studio, "view_missing_source_repair_results")
           and hasattr(bpy.ops.rh_studio, "copy_repair_result_path"),
           "Missing-source repair result viewer/copy operators did not register.")

    clean_scene()

    # Invalid geometry must be rejected without leaving a partial Basis key behind.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
    flat_mesh = bpy.context.object
    for vertex in flat_mesh.data.vertices:
        vertex.co.z = 0.0
    activate(flat_mesh)
    result = bpy.ops.rh_studio.generate_body_proportion_keys()
    ensure("CANCELLED" in result, "Flat mesh should be rejected by body-proportion generation.")
    ensure(flat_mesh.data.shape_keys is None,
           "Rejected geometry must not be mutated by creating a stray Basis shape key.")
    bpy.data.objects.remove(flat_mesh, do_unlink=True)

    # Build and update non-destructive body-proportion shape keys on an upright mesh.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(4.0, 0.0, 1.0))
    proportion_mesh = bpy.context.object
    proportion_mesh.name = "RH CI Proportion Mesh"
    proportion_mesh.scale = (0.35, 0.22, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shoulder_mask = proportion_mesh.vertex_groups.new(name="RH遮罩 | 肩宽")
    upper_vertices = [vertex.index for vertex in proportion_mesh.data.vertices
                      if vertex.co.z > 0.0]
    shoulder_mask.add(upper_vertices, 1.0, "REPLACE")
    activate(proportion_mesh)
    result = bpy.ops.rh_studio.generate_body_proportion_keys()
    ensure("FINISHED" in result, "Body proportion shape-key generation failed.")
    proportion_keys = proportion_mesh.data.shape_keys.key_blocks
    proportion_names = ("RH体型 | 肩宽", "RH体型 | 胸围", "RH体型 | 腰围", "RH体型 | 臀宽")
    ensure(all(proportion_keys.get(name) is not None for name in proportion_names),
           "One or more body proportion shape keys are missing.")
    shoulder_key = proportion_keys["RH体型 | 肩宽"]
    ensure(abs(shoulder_key.slider_min + 1.0) < 1e-6
           and abs(shoulder_key.slider_max - 1.0) < 1e-6,
           "Body proportion controls should support a -1 to +1 range.")
    ensure(any((shoulder_key.data[i].co - proportion_keys[0].data[i].co).length > 1e-5
               for i in upper_vertices),
           "Generated shoulder key does not deform vertices inside its authored mask.")
    ensure(all((shoulder_key.data[i].co - proportion_keys[0].data[i].co).length < 1e-6
               for i, vertex in enumerate(proportion_mesh.data.vertices)
               if vertex.index not in upper_vertices),
           "Generated shoulder key deformed vertices outside its authored mask.")

    # Evaluate the negative slider direction as well as the stored positive
    # shape-key coordinates, and verify the vertex-group mask still gates it.
    shoulder_key.value = -1.0
    bpy.context.view_layer.update()
    evaluated_object = proportion_mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated_object.to_mesh()
    try:
        ensure(any((evaluated_mesh.vertices[i].co - proportion_keys[0].data[i].co).length > 1e-5
                   for i in upper_vertices),
               "Negative shoulder slider value did not deform vertices inside the mask.")
        ensure(all((evaluated_mesh.vertices[i].co - proportion_keys[0].data[i].co).length < 1e-6
                   for i, vertex in enumerate(proportion_mesh.data.vertices)
                   if vertex.index not in upper_vertices),
               "Negative shoulder slider value deformed vertices outside its authored mask.")
    finally:
        evaluated_object.to_mesh_clear()
    shoulder_key.value = 0.0
    bpy.context.view_layer.update()
    custom_key = proportion_mesh.shape_key_add(name="User Custom", from_mix=False)
    custom_key.data[0].co.x += 0.125
    custom_key.value = 0.25
    custom_coord = custom_key.data[0].co.copy()
    result = bpy.ops.rh_studio.generate_body_proportion_keys()
    ensure("FINISHED" in result, "Updating body proportion shape keys failed.")
    ensure(sum(1 for key in proportion_keys if key.name.startswith("RH体型 | ")) == 4,
           "Updating body proportion keys created duplicate controls.")
    ensure((custom_key.data[0].co - custom_coord).length < 1e-6
           and abs(custom_key.value - 0.25) < 1e-6,
           "Updating body proportion keys modified an unrelated user shape key.")
    bpy.data.objects.remove(proportion_mesh, do_unlink=True)

    # Exercise the same rig-generation operator the UI calls, but disable
    # automatic weights so this test is deterministic and mesh-topology agnostic.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.95))
    mesh = bpy.context.object
    mesh.name = "RH CI Human Mesh"
    mesh.scale = (0.28, 0.18, 1.8)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    ensure(mesh.dimensions.z > 1.5, "Test mesh should be tall enough to rig.")
    activate(mesh)

    result = bpy.ops.rh_studio.generate_simple_rig(
        auto_bind=False, hip_height_ratio=0.54, knee_height_ratio=0.29,
        shoulder_height_ratio=0.82, shoulder_width_ratio=0.125,
        arm_reach_ratio=0.52,
    )
    ensure("FINISHED" in result, "Simple rig generation operator failed.")
    rig = bpy.context.object
    ensure(rig and rig.type == "ARMATURE", "Rig was not made active.")
    for name in ("root", "spine", "chest", "neck", "head",
                 "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R",
                 "hand.L", "hand.R", "thigh.L", "thigh.R", "shin.L", "shin.R",
                 "foot.L", "foot.R"):
        ensure(rig.pose.bones.get(name) is not None, "Missing bone: " + name)
    shoulder_head = rig.data.bones["upper_arm.R"].head_local
    hand_tail = rig.data.bones["hand.R"].tail_local
    ensure(abs(shoulder_head.z - (0.05 + 0.82 * 1.8)) < 0.02,
           "Custom shoulder-height ratio was not applied.")
    ensure(abs(hand_tail.x - 0.52 * 1.8) < 0.03,
           "Custom arm-reach ratio was not applied.")

    # Exercise direct selected-bone rotation editing and optional keyframing.
    activate(rig)
    bpy.ops.object.mode_set(mode="POSE")
    # Pass the target bone explicitly; Blender's bone-selection API differs
    # between releases, while the operator must remain testable headlessly.
    result = bpy.ops.rh_studio.adjust_active_bone(
        bone_name="forearm.R", rotation_x=0.2, rotation_y=0.1,
        rotation_z=-0.15, insert_keyframe=True)
    ensure("FINISHED" in result, "Direct selected-bone rotation adjustment failed.")
    edited_bone = rig.pose.bones["forearm.R"]
    ensure(edited_bone.rotation_mode == "XYZ"
           and abs(edited_bone.rotation_euler.x - 0.2) < 1e-4
           and abs(edited_bone.rotation_euler.y - 0.1) < 1e-4
           and abs(edited_bone.rotation_euler.z + 0.15) < 1e-4,
           "Direct bone rotation values were not applied.")
    ensure(rig.animation_data is not None and rig.animation_data.action is not None,
           "Selected-bone keyframe was not recorded.")
    bpy.ops.object.mode_set(mode="OBJECT")

    ensure("FINISHED" in bpy.ops.rh_studio.apply_pose_preset(preset="ARMS_UP"),
           "Apply pose preset failed.")
    existing_action = rig.animation_data.action
    existing_action.name = "Preserve Existing Action"
    bpy.context.scene.frame_set(1)
    rig.pose.bones["forearm.R"].scale = (1.0, 1.0, 1.0)
    ensure("FINISHED" in bpy.ops.rh_studio.insert_pose_keyframe(),
           "Keyframe insertion failed.")
    ensure(rig.animation_data is not None, "Pose action was not created.")
    ensure(rig.animation_data.action == existing_action
           and existing_action.name == "Preserve Existing Action",
           "Inserting pose keys renamed or replaced an existing Action.")

    # Give the clip a real span and animate scale as well as location/rotation.
    # Exact-frame evaluation verifies that the scale channel is actually keyed.
    bpy.context.scene.frame_set(13)
    rig.pose.bones["forearm.R"].scale = (1.2, 1.1, 0.9)
    ensure("FINISHED" in bpy.ops.rh_studio.insert_pose_keyframe(),
           "Second keyframe insertion failed.")
    bpy.context.scene.frame_set(13)
    bpy.context.view_layer.update()
    scaled_bone = rig.pose.bones["forearm.R"]
    ensure(abs(scaled_bone.scale.x - 1.2) < 1e-3
           and abs(scaled_bone.scale.y - 1.1) < 1e-3
           and abs(scaled_bone.scale.z - 0.9) < 1e-3,
           "Scale values did not persist at the keyed frame.")
    ensure("FINISHED" in bpy.ops.rh_studio.save_action_set(action_set_name="CI Motion"),
           "Saving a named action set failed.")
    saved_action = bpy.data.actions.get("RH动作集 | CI Motion")
    ensure(saved_action is not None and saved_action.use_fake_user,
           "Named action set was not preserved in the .blend data.")

    # A malformed layered source must not replace an already saved set. This
    # specifically protects the validation-before-replacement ordering.
    source_slots = getattr(rig.animation_data.action, "slots", None)
    source_slot = getattr(rig.animation_data, "action_slot", None)
    if source_slots is not None and len(source_slots) and source_slot is not None:
        rig.animation_data.action_slot = None
        rejected = bpy.ops.rh_studio.save_action_set(action_set_name="CI Motion")
        ensure("CANCELLED" in rejected,
               "Saving a layered Action without an active slot should be rejected.")
        ensure(bpy.data.actions.get("RH动作集 | CI Motion") == saved_action,
               "Rejected save removed or replaced the previously saved action set.")
        rig.animation_data.action_slot = source_slot

    rig_copy = rig.copy()
    rig_copy.data = rig.data.copy()
    bpy.context.scene.collection.objects.link(rig_copy)
    rig_copy.animation_data_create()
    rig_copy.animation_data.action = saved_action
    ensure("FINISHED" in bpy.ops.rh_studio.save_action_set(action_set_name="CI Motion"),
           "Saving a duplicate action-set name should safely create a numbered copy.")
    ensure(rig_copy.animation_data.action == saved_action and saved_action.name in bpy.data.actions,
           "Saving a duplicate action set broke an Action used by another rig.")
    numbered_copy = bpy.data.actions.get("RH动作集 | CI Motion (2)")
    ensure(numbered_copy is not None and numbered_copy.use_fake_user,
           "A duplicate action-set name did not create a persistent numbered copy.")
    ensure("FINISHED" in bpy.ops.rh_studio.load_action_set(action_set="RH动作集 | CI Motion"),
           "Loading a named action set failed.")
    ensure(rig.animation_data.action == saved_action,
           "The selected named action set was not assigned to the rig.")
    saved_slots = getattr(saved_action, "slots", None)
    if saved_slots is not None and len(saved_slots):
        preferred_identifier = saved_action.get("rh_studio_action_slot_identifier", "")
        expected_slot = next(
            (slot for slot in saved_slots
             if preferred_identifier and slot.identifier == preferred_identifier),
            None,
        )
        ensure(expected_slot is not None,
               "The saved action-set slot identifier does not resolve to a slot in the copied Action.")
        ensure(rig.animation_data.action_slot == expected_slot,
               "Loading a named action set did not bind the exact preserved Action Slot.")
    action_start = int(saved_action.frame_range[0])
    ensure(bpy.context.scene.frame_current == action_start,
           "Loading an action set did not move the timeline to its first keyed frame.")
    bpy.context.scene.frame_set(13)
    bpy.context.view_layer.update()
    loaded_scale = rig.pose.bones["forearm.R"].scale
    ensure(abs(loaded_scale.x - 1.2) < 1e-3
           and abs(loaded_scale.y - 1.1) < 1e-3
           and abs(loaded_scale.z - 0.9) < 1e-3,
           "Loaded action-set scale channels did not evaluate at their keyed frame.")
    # The pose-pad drawing center must keep its head and footer inside the
    # smallest viewport accepted by invoke(); GPU rendering itself needs GUI QA.
    small_cx, small_cy = rh_operators._simple_pose_pad_center(240, 224)
    ensure(abs(small_cx - 120.0) < 1e-6 and abs(small_cy - 124.0) < 1e-6,
           "Minimal pose-pad layout is outside the accepted small viewport.")
    ensure(small_cy + 84.0 + 15.0 <= 224.0
           and small_cy - 124.0 >= 0.0,
           "Pose-pad head/footer would be clipped in a 240x224 viewport.")

    # The minimal 2D pose pad must key scale as well as location/rotation.
    # Use the shared helper directly because a headless test cannot validate the modal GPU overlay.
    bpy.context.scene.frame_set(17)
    rig.pose.bones["forearm.R"].scale = (1.3, 1.15, 0.85)
    keyed_bones = rh_operators._insert_rig_pose_keyframes(rig, 17)
    ensure(keyed_bones == len(rig.pose.bones),
           "2D pose-pad keyframe helper did not process every pose bone.")
    action_for_2d = rig.animation_data.action
    ensure(any(curve.data_path.endswith(".scale")
               and 'pose.bones["forearm.R"]' in curve.data_path
               for curve in action_for_2d.fcurves),
           "2D pose-pad keyframe helper did not create a scale animation channel.")

    ensure("FINISHED" in bpy.ops.rh_studio.check_action_sequence(),
           "Basic action sequence check failed.")

    ensure("FINISHED" in bpy.ops.rh_studio.save_pose_preset(preset_name="CI Smoke"),
           "Saving a pose preset failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.load_pose_preset(preset_name="CI Smoke"),
           "Loading a pose preset failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.turn_body_preset(facing="THREE_QUARTER_L"),
           "Facing preset failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.check_pose_clearance(),
           "Clearance check failed.")

    # Verify the fabric shader graph can be built under the tested Blender API.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.5, 0.0, 1.0))
    garment = bpy.context.object
    garment.name = "RH CI Garment"
    activate(garment)
    result = bpy.ops.rh_studio.create_fabric_print(pattern="DOTS")
    ensure("FINISHED" in result, "Fabric print material operator failed.")
    ensure(garment.data.materials and garment.data.materials[0].use_nodes,
           "Fabric material wasn't assigned.")

    # Verify object-coordinate mapping and face-region-only material assignment.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.5, 0.0, 1.0))
    region_mesh = bpy.context.object
    region_mesh.name = "RH CI Regional Print Mesh"
    region_mesh.data.materials.append(bpy.data.materials.new("RH CI Base Fabric"))
    activate(region_mesh)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(region_mesh.data)
    for face in bm.faces:
        face.select_set(False)
    top_faces = [face for face in bm.faces if face.normal.z > 0.9]
    ensure(len(top_faces) == 1, "Test cube should have exactly one top face.")
    top_faces[0].select_set(True)
    bmesh.update_edit_mesh(region_mesh.data)
    result = bpy.ops.rh_studio.create_fabric_print(
        pattern="STRIPES", coordinate_source="OBJECT",
        offset_x=0.25, offset_y=-0.1, scale_x=1.5, scale_y=0.75)
    ensure("FINISHED" in result, "Regional fabric print assignment failed.")
    bpy.ops.object.mode_set(mode="OBJECT")
    region_material = region_mesh.data.materials[-1]
    ensure(region_material.get("rh_studio_coordinate_source") == "OBJECT",
           "Fabric coordinate source metadata was not stored.")
    ensure(abs(region_material.get("rh_studio_offset_x", 0.0) - 0.25) < 1e-6
           and abs(region_material.get("rh_studio_scale_y", 0.0) - 0.75) < 1e-6,
           "Fabric placement controls were not stored.")
    assigned_faces = [poly for poly in region_mesh.data.polygons
                      if poly.material_index == len(region_mesh.data.materials) - 1]
    ensure(len(assigned_faces) == 1 and assigned_faces[0].normal.z > 0.9,
           "Regional print should affect only the selected face.")
    bpy.data.objects.remove(region_mesh, do_unlink=True)

    # Selected asset audit should create a portable JSON report with real mesh statistics.
    activate(garment)
    with tempfile.TemporaryDirectory(prefix="rh_studio_asset_audit_") as audit_tmp:
        audit_path = os.path.join(audit_tmp, "asset_audit.json")
        result = bpy.ops.rh_studio.audit_selected_assets(filepath=audit_path)
        ensure("FINISHED" in result and os.path.isfile(audit_path),
               "Selected asset audit did not write its JSON report.")
        with open(audit_path, "r", encoding="utf-8") as stream:
            audit_payload = json.load(stream)
        ensure(audit_payload.get("schema") == "realhuman_studio_asset_audit_v1"
               and audit_payload.get("object_count") == 1,
               "Asset audit report schema or object count is incorrect.")
        audited = audit_payload["objects"][0]
        ensure(audited.get("name") == garment.name
               and audited.get("mesh", {}).get("vertices") == len(garment.data.vertices)
               and audited.get("mesh", {}).get("polygons") == len(garment.data.polygons),
               "Asset audit did not report accurate mesh statistics.")
        ensure("uv_layers" in audited["mesh"]
               and "non_manifold_edges" in audited["mesh"],
               "Asset audit omitted UV or topology diagnostics.")

    # Asset audit should flag a missing original source and a broken armature modifier.
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    broken_asset = bpy.context.object
    broken_asset.name = "RH CI Broken Asset Links"
    broken_asset["rh_studio_source_path"] = os.path.join(
        tempfile.gettempdir(), "rh_studio_source_that_does_not_exist.fbx")
    broken_asset["rh_studio_import_batch_id"] = "ci-broken-link-batch"
    broken_asset.modifiers.new(name="Missing Rig Target", type="ARMATURE")
    activate(broken_asset)
    with tempfile.TemporaryDirectory(prefix="rh_studio_broken_asset_audit_") as audit_tmp:
        broken_audit_path = os.path.join(audit_tmp, "broken_asset_audit.json")
        result = bpy.ops.rh_studio.audit_selected_assets(filepath=broken_audit_path)
        ensure("FINISHED" in result, "Broken asset link audit failed.")
        with open(broken_audit_path, "r", encoding="utf-8") as stream:
            broken_payload = json.load(stream)
        broken_record = broken_payload["objects"][0]
        ensure(broken_record.get("source_path_exists") is False
               and broken_record.get("import_batch_id") == "ci-broken-link-batch"
               and any("原始资源文件不存在" in warning
                       for warning in broken_record.get("warnings", []))
               and any("没有目标骨架" in warning
                       for warning in broken_record.get("warnings", [])),
               "Asset audit missed a stale source path or an unassigned armature modifier.")

        # The project-wide report should aggregate all objects and cross-check
        # the persistent import history, not only inspect the current selection.
        previous_project_root = bpy.context.scene.rh_studio_project_root
        bpy.context.scene.rh_studio_project_root = audit_tmp
        with open(os.path.join(audit_tmp, "realhuman_project.json"), "w",
                  encoding="utf-8") as stream:
            json.dump({
                "application": "RealHuman Studio",
                "asset_sources": [{
                    "batch_id": "ci-missing-source-history",
                    "source_path": os.path.join(audit_tmp, "deleted_original.fbx"),
                    "objects": [{"name": "RH CI Deleted Imported Object"}],
                }],
            }, stream)
        project_audit_path = os.path.join(audit_tmp, "project_integrity.json")
        result = bpy.ops.rh_studio.audit_project_assets(filepath=project_audit_path)
        ensure("FINISHED" in result and os.path.isfile(project_audit_path),
               "Project-wide asset audit failed.")
        with open(project_audit_path, "r", encoding="utf-8") as stream:
            project_audit = json.load(stream)
        ensure(project_audit.get("schema") == "realhuman_studio_project_integrity_v1"
               and project_audit.get("summary", {}).get("missing_source_files", 0) >= 1
               and project_audit.get("summary", {}).get("missing_armature_targets", 0) >= 1
               and any("源文件不存在" in warning
                       for warning in project_audit.get("project_history", {}).get("warnings", []))
               and project_audit.get("object_count", 0) >= 1,
               "Project audit missed broken links or project history inconsistencies.")
        # Candidate scan is preview-only and ranks exact filename/extension candidates by recorded size.
        scan_root = os.path.join(audit_tmp, "source_recovery")
        os.makedirs(scan_root, exist_ok=True)
        scan_candidate = os.path.join(scan_root, "lost_asset.fbx")
        with open(scan_candidate, "wb") as stream:
            stream.write(b"known-size-original")
        scan_manifest_path = os.path.join(audit_tmp, "realhuman_project.json")
        with open(scan_manifest_path, "r", encoding="utf-8") as stream:
            scan_manifest = json.load(stream)
        scan_manifest["asset_sources"].append({
            "batch_id": "ci-scan-batch",
            "source_path": os.path.join(audit_tmp, "gone", "lost_asset.fbx"),
            "source_size_bytes": os.path.getsize(scan_candidate),
            "objects": [{"name": "RH CI Scan Asset", "type": "MESH"}],
        })
        with open(scan_manifest_path, "w", encoding="utf-8") as stream:
            json.dump(scan_manifest, stream, ensure_ascii=False, indent=2)
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        scan_asset = bpy.context.object
        scan_asset.name = "RH CI Scan Asset"
        old_scan_path = os.path.join(audit_tmp, "gone", "lost_asset.fbx")
        scan_asset["rh_studio_source_path"] = old_scan_path
        scan_asset["rh_studio_import_batch_id"] = "ci-scan-batch"
        activate(scan_asset)
        scan_report_path = os.path.join(audit_tmp, "missing_source_candidates.json")
        result = bpy.ops.rh_studio.scan_missing_sources(directory=scan_root, filepath=scan_report_path)
        ensure("FINISHED" in result and os.path.isfile(scan_report_path),
               "Missing-source candidate scan did not write its report.")
        with open(scan_report_path, "r", encoding="utf-8") as stream:
            scan_report = json.load(stream)
        scan_records = [item for item in scan_report["objects"] if item["object_name"] == scan_asset.name]
        ensure(len(scan_records) == 1
               and scan_records[0]["candidate_status"] == "unique_exact_size_match"
               and scan_records[0]["candidates"][0]["path"] == os.path.normpath(scan_candidate)
               and scan_records[0]["candidates"][0]["size_match"],
               "Candidate scan failed to find the unique same-name, same-extension, same-size candidate.")
        ensure(scan_asset["rh_studio_source_path"] == old_scan_path,
               "Candidate scan must not mutate source-path metadata.")

        # A candidate changing after the scan must be rejected without mutation.
        with open(scan_candidate, "ab") as stream:
            stream.write(b"-changed")
        with open(scan_manifest_path, "rb") as stream:
            before_manifest_bytes = stream.read()
        try:
            result = bpy.ops.rh_studio.apply_missing_source_repairs(filepath=scan_report_path)
        except RuntimeError:
            result = {"CANCELLED"}
        with open(scan_manifest_path, "rb") as stream:
            after_manifest_bytes = stream.read()
        ensure("CANCELLED" in result
               and scan_asset["rh_studio_source_path"] == old_scan_path
               and after_manifest_bytes == before_manifest_bytes,
               "Batch repair must reject a candidate whose size changed after scanning without mutating data.")
        repair_results_path = os.path.join(audit_tmp, "logs", "missing_source_repair_results.json")
        ensure(os.path.isfile(repair_results_path),
               "Rejected batch repair should still write a per-item result report.")
        with open(repair_results_path, "r", encoding="utf-8") as stream:
            changed_candidate_results = json.load(stream)
        changed_result = next((item for item in changed_candidate_results.get("results", [])
                               if item.get("object_name") == scan_asset.name), {})
        ensure(changed_candidate_results.get("schema") == "realhuman_studio_missing_source_repair_results_v1"
               and changed_result.get("status") == "skipped"
               and changed_result.get("reason") == "candidate_size_changed_or_mismatched",
               "Repair results should explain why the changed candidate was skipped.")
        with open(scan_candidate, "wb") as stream:
            stream.write(b"known-size-original")
        result = bpy.ops.rh_studio.apply_missing_source_repairs(filepath=scan_report_path)
        ensure("FINISHED" in result
               and os.path.normpath(scan_asset["rh_studio_source_path"]) == os.path.normpath(scan_candidate)
               and scan_asset.get("rh_studio_relinked_at"),
               "Confirmed batch repair did not relink the unique exact-size candidate.")
        with open(scan_manifest_path, "r", encoding="utf-8") as stream:
            repaired_manifest = json.load(stream)
        repaired_entries = [entry for entry in repaired_manifest["asset_sources"]
                            if entry.get("batch_id") == "ci-scan-batch"]
        ensure(len(repaired_entries) == 1
               and os.path.normpath(repaired_entries[0]["source_path"]) == os.path.normpath(scan_candidate)
               and repaired_entries[0].get("recovery_method") == "candidate_report_unique_exact_size",
               "Batch repair did not synchronize project import history.")
        with open(repair_results_path, "r", encoding="utf-8") as stream:
            successful_repair_results = json.load(stream)
        successful_result = next((item for item in successful_repair_results.get("results", [])
                                  if item.get("object_name") == scan_asset.name), {})
        ensure(successful_result.get("status") == "repaired"
               and successful_result.get("reason") == "unique_exact_size_and_project_history_verified"
               and successful_repair_results.get("summary", {}).get("repaired") == 1,
               "Successful repair results should record the repaired object and summary.")
        # An ambiguous candidate report must not change object metadata or history.
        ambiguous_report_path = os.path.join(audit_tmp, "ambiguous_candidates.json")
        with open(scan_report_path, "r", encoding="utf-8") as stream:
            ambiguous_payload = json.load(stream)
        for item in ambiguous_payload["objects"]:
            if item.get("object_name") == scan_asset.name:
                item["candidate_status"] = "ambiguous_exact_size_matches"
        with open(ambiguous_report_path, "w", encoding="utf-8") as stream:
            json.dump(ambiguous_payload, stream, ensure_ascii=False, indent=2)
        repaired_source_path = scan_asset["rh_studio_source_path"]
        with open(scan_manifest_path, "rb") as stream:
            before_ambiguous_manifest = stream.read()
        try:
            result = bpy.ops.rh_studio.apply_missing_source_repairs(filepath=ambiguous_report_path)
        except RuntimeError:
            result = {"CANCELLED"}
        with open(scan_manifest_path, "rb") as stream:
            after_ambiguous_manifest = stream.read()
        ensure("CANCELLED" in result
               and scan_asset["rh_studio_source_path"] == repaired_source_path
               and after_ambiguous_manifest == before_ambiguous_manifest,
               "Ambiguous candidate records must be refused without mutating object or history.")
        with open(repair_results_path, "r", encoding="utf-8") as stream:
            ambiguous_repair_results = json.load(stream)
        ambiguous_result = next((item for item in ambiguous_repair_results.get("results", [])
                                 if item.get("object_name") == scan_asset.name), {})
        ensure(ambiguous_result.get("status") == "skipped"
               and ambiguous_result.get("reason") == "candidate_status_not_repairable"
               and ambiguous_repair_results.get("summary", {}).get("skipped", 0) >= 1,
               "Ambiguous repair report should record a skipped result with an explicit reason.")
        bpy.data.objects.remove(scan_asset, do_unlink=True)

        # Relinking repairs metadata only; it must also update the matching history batch atomically.
        relink_source = os.path.join(audit_tmp, "recovered_original.fbx")
        with open(relink_source, "wb") as stream:
            stream.write(b"recovered source file")
        project_manifest_path = os.path.join(audit_tmp, "realhuman_project.json")
        with open(project_manifest_path, "r", encoding="utf-8") as stream:
            relink_manifest = json.load(stream)
        relink_manifest["asset_sources"].append({
            "batch_id": "ci-broken-link-batch",
            "source_path": broken_asset["rh_studio_source_path"],
            "source_size_bytes": 10,
            "objects": [{"name": broken_asset.name, "type": "MESH"}],
        })
        with open(project_manifest_path, "w", encoding="utf-8") as stream:
            json.dump(relink_manifest, stream, ensure_ascii=False, indent=2)
        broken_asset["rh_studio_import_batch_id"] = "ci-broken-link-batch"
        activate(broken_asset)
        result = bpy.ops.rh_studio.relink_asset_source(filepath=relink_source)
        ensure("FINISHED" in result, "Source-path relink operator failed.")
        ensure(os.path.normpath(broken_asset["rh_studio_source_path"]) == os.path.normpath(relink_source)
               and os.path.isfile(broken_asset["rh_studio_source_path"])
               and broken_asset.get("rh_studio_relinked_at"),
               "Relink did not update the selected object's source metadata.")
        with open(project_manifest_path, "r", encoding="utf-8") as stream:
            relinked_manifest = json.load(stream)
        matching_batch = [entry for entry in relinked_manifest["asset_sources"]
                          if entry.get("batch_id") == "ci-broken-link-batch"]
        ensure(len(matching_batch) == 1
               and matching_batch[0].get("source_path") == os.path.normpath(relink_source)
               and matching_batch[0].get("source_size_bytes") == os.path.getsize(relink_source)
               and matching_batch[0].get("relinked_from")
               and matching_batch[0].get("relinked_at"),
               "Relink did not synchronize the import-history source metadata.")
        # Mixed batches must be rejected before any object's path is mutated.
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        second_asset = bpy.context.object
        second_asset.name = "RH CI Other Batch Asset"
        second_asset["rh_studio_source_path"] = broken_asset["rh_studio_source_path"]
        second_asset["rh_studio_import_batch_id"] = "different-batch"
        activate(broken_asset)
        second_asset.select_set(True)
        try:
            result = bpy.ops.rh_studio.relink_asset_source(filepath=relink_source)
        except RuntimeError:
            result = {"CANCELLED"}
        ensure("CANCELLED" in result
               and broken_asset["rh_studio_source_path"] == os.path.normpath(relink_source),
               "Relink should reject mixed batches without mutating source paths.")
        bpy.data.objects.remove(second_asset, do_unlink=True)
        bpy.context.scene.rh_studio_project_root = previous_project_root
    bpy.data.objects.remove(broken_asset, do_unlink=True)

    # Asset manifest export should include portable metadata and convert dimensions to meters.
    activate(garment)
    previous_manifest_scale = bpy.context.scene.unit_settings.scale_length
    bpy.context.scene.unit_settings.scale_length = 0.01
    with tempfile.TemporaryDirectory(prefix="rh_studio_asset_manifest_") as manifest_tmp:
        manifest_path = os.path.join(manifest_tmp, "asset_manifest.json")
        result = bpy.ops.rh_studio.export_asset_manifest(filepath=manifest_path)
        ensure("FINISHED" in result and os.path.isfile(manifest_path),
               "Asset manifest export did not write its JSON file.")
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest_payload = json.load(stream)
        ensure(manifest_payload.get("schema") == "realhuman_studio_asset_manifest_v1"
               and manifest_payload.get("object_count") == 1
               and abs(manifest_payload.get("meters_per_blender_unit", 0.0) - 0.01) < 1e-9,
               "Asset manifest schema, count, or unit scale is incorrect.")
        manifest_object = manifest_payload["objects"][0]
        ensure(manifest_object.get("name") == garment.name
               and manifest_object.get("mesh", {}).get("vertices") == len(garment.data.vertices)
               and manifest_object.get("world_bounds") is not None
               and len(manifest_object.get("dimensions_world_m", [])) == 3,
               "Asset manifest omitted mesh statistics or metric world bounds.")
    bpy.context.scene.unit_settings.scale_length = previous_manifest_scale

    # Scale diagnosis should report world dimensions and unit hypotheses without mutating transforms.
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.0, 2.0, 3.0))
    scale_cube = bpy.context.object
    scale_location_before = tuple(scale_cube.location)
    scale_scale_before = tuple(scale_cube.scale)
    activate(scale_cube)
    with tempfile.TemporaryDirectory(prefix="rh_studio_scale_diagnosis_") as scale_tmp:
        scale_report_path = os.path.join(scale_tmp, "scale_diagnosis.json")
        result = bpy.ops.rh_studio.diagnose_asset_scale(filepath=scale_report_path)
        ensure("FINISHED" in result and os.path.isfile(scale_report_path),
               "Scale diagnosis did not write its JSON report.")
        with open(scale_report_path, "r", encoding="utf-8") as stream:
            scale_payload = json.load(stream)
        ensure(scale_payload.get("schema") == "realhuman_studio_scale_diagnosis_v1"
               and scale_payload.get("object_count") == 1,
               "Scale diagnosis report schema or object count is incorrect.")
        ensure(scale_payload["world_bounds"]["dimensions"] == [2.0, 2.0, 2.0]
               and len(scale_payload["unit_hypotheses"]) == 3,
               "Scale diagnosis returned incorrect bounds or missing unit hypotheses.")
        ensure(tuple(scale_cube.location) == scale_location_before
               and tuple(scale_cube.scale) == scale_scale_before,
               "Scale diagnosis unexpectedly modified object transforms.")
    bpy.data.objects.remove(scale_cube, do_unlink=True)

    # Height calibration converts the meter target through scene scale_length.
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(1.0, 2.0, 3.0))
    calibration_cube = bpy.context.object
    activate(calibration_cube)
    previous_unit_system = bpy.context.scene.unit_settings.system
    previous_scale_length = bpy.context.scene.unit_settings.scale_length
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.01
    result = bpy.ops.rh_studio.fit_height(target_height=1.75)
    ensure("FINISHED" in result, "Height calibration failed for a centimeter-scaled scene.")
    bpy.context.view_layer.update()
    calibrated_height_m = float(calibration_cube.dimensions.z) * bpy.context.scene.unit_settings.scale_length
    calibrated_bottom_z = min((calibration_cube.matrix_world @ Vector(corner)).z
                              for corner in calibration_cube.bound_box) * bpy.context.scene.unit_settings.scale_length
    ensure(abs(calibrated_height_m - 1.75) < 1e-4,
           "Height calibration did not honor scene scale_length.")
    ensure(abs(calibrated_bottom_z) < 1e-4,
           "Height calibration did not place the mesh bottom at world Z=0.")
    bpy.data.objects.remove(calibration_cube, do_unlink=True)
    bpy.context.scene.unit_settings.system = previous_unit_system
    bpy.context.scene.unit_settings.scale_length = previous_scale_length

    # Group calibration scales multiple selected objects together in world space.
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.0))
    group_body = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 3.0))
    group_clothing = bpy.context.object
    group_body.select_set(True)
    group_clothing.select_set(True)
    bpy.context.view_layer.objects.active = group_body
    previous_unit_system = bpy.context.scene.unit_settings.system
    previous_scale_length = bpy.context.scene.unit_settings.scale_length
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.01
    result = bpy.ops.rh_studio.fit_selected_group_height(target_height=1.75)
    ensure("FINISHED" in result, "Selected-group height calibration failed.")
    bpy.context.view_layer.update()
    group_corners = [
        obj.matrix_world @ Vector(corner)
        for obj in (group_body, group_clothing) for corner in obj.bound_box
    ]
    group_height_m = (max(p.z for p in group_corners) - min(p.z for p in group_corners)) * 0.01
    group_bottom_m = min(p.z for p in group_corners) * 0.01
    ensure(abs(group_height_m - 1.75) < 1e-4,
           "Selected-group calibration did not achieve target height.")
    ensure(abs(group_bottom_m) < 1e-4,
           "Selected-group calibration did not place group bottom at world Z=0.")
    ensure(group_body.dimensions.z > 0.0 and group_clothing.dimensions.z > 0.0,
           "Selected-group calibration damaged object dimensions.")
    bpy.data.objects.remove(group_body, do_unlink=True)
    bpy.data.objects.remove(group_clothing, do_unlink=True)
    bpy.context.scene.unit_settings.system = previous_unit_system
    bpy.context.scene.unit_settings.scale_length = previous_scale_length

    # Refuse to scale a bound mesh without its armature, and preserve transforms.
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.object.armature_add(location=(0.0, 0.0, 0.0))
    bound_rig = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(2.0, 0.0, 1.0))
    bound_mesh = bpy.context.object
    armature_modifier = bound_mesh.modifiers.new(name="Armature", type="ARMATURE")
    armature_modifier.object = bound_rig
    mesh_matrix_before = bound_mesh.matrix_world.copy()
    rig_matrix_before = bound_rig.matrix_world.copy()
    activate(bound_mesh)
    # Blender's background operator runner raises RuntimeError when an operator
    # reports ERROR, even when the operator correctly returns CANCELLED.
    try:
        result = bpy.ops.rh_studio.fit_selected_group_height(target_height=1.75)
    except RuntimeError as exc:
        ensure("未选中的绑定骨架" in str(exc),
               "Group calibration failed for an unexpected reason: %s" % exc)
        result = {"CANCELLED"}
    ensure("CANCELLED" in result,
           "Group calibration should refuse a bound mesh when its armature is not selected.")
    ensure(all(abs(a - b) < 1e-6
                   for row_a, row_b in zip(mesh_matrix_before, bound_mesh.matrix_world)
                   for a, b in zip(row_a, row_b))
           and all(abs(a - b) < 1e-6
                   for row_a, row_b in zip(rig_matrix_before, bound_rig.matrix_world)
                   for a, b in zip(row_a, row_b)),
           "Rejected group calibration unexpectedly modified transforms.")
    bpy.data.objects.remove(bound_mesh, do_unlink=True)
    bpy.data.objects.remove(bound_rig, do_unlink=True)

    # Position normalization should center the selected group and place its bounds on Z=0
    # without applying transforms or mutating mesh coordinates.
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(3.0, 4.0, 2.0))
    normalize_cube = bpy.context.object
    mesh_coords_before = [tuple(vertex.co) for vertex in normalize_cube.data.vertices]
    scale_before = tuple(normalize_cube.scale)
    activate(normalize_cube)
    result = bpy.ops.rh_studio.normalize_selected_assets()
    ensure("FINISHED" in result, "Asset position normalization operator failed.")
    bpy.context.view_layer.update()
    world_corners = [normalize_cube.matrix_world @ Vector(corner)
                     for corner in normalize_cube.bound_box]
    bounds_min = [min(point[i] for point in world_corners) for i in range(3)]
    bounds_max = [max(point[i] for point in world_corners) for i in range(3)]
    ensure(abs((bounds_min[0] + bounds_max[0]) * 0.5) < 1e-5
           and abs((bounds_min[1] + bounds_max[1]) * 0.5) < 1e-5
           and abs(bounds_min[2]) < 1e-5,
           "Asset normalization did not center X/Y and align the bottom to Z=0.")
    ensure(tuple(normalize_cube.scale) == scale_before
           and [tuple(vertex.co) for vertex in normalize_cube.data.vertices] == mesh_coords_before,
           "Asset normalization unexpectedly changed scale or mesh coordinates.")
    ensure(normalize_cube.get("rh_studio_position_normalized") is True,
           "Asset normalization metadata was not recorded.")
    bpy.data.objects.remove(normalize_cube, do_unlink=True)

    # Validate the project folder scaffolding and manifest in a temporary folder.
    with tempfile.TemporaryDirectory(prefix="rh_studio_ci_") as tmp:
        result = bpy.ops.rh_studio.setup_project(project_name="SmokeTest", project_root=tmp)
        ensure("FINISHED" in result, "Project setup operator failed.")
        manifest_path = os.path.join(tmp, "SmokeTest", "realhuman_project.json")
        ensure(os.path.isfile(manifest_path), "Project manifest was not created.")
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        ensure(manifest.get("application") == "RealHuman Studio",
               "Project manifest content is unexpected.")

        # A successful asset import should append a traceable batch without
        # discarding the project's existing manifest fields.
        project_dir = os.path.join(tmp, "SmokeTest")
        source_path = os.path.join(tmp, "ci_source_asset.fbx")
        with open(source_path, "wb") as stream:
            stream.write(b"fake source bytes for history metadata test")
        batch_id = "ci-import-batch-001"
        imported_at = "2026-10-14T12:00:00+00:00"
        history_ok, history_result = realhuman_studio.operators.record_project_import(
            bpy.context.scene, source_path, "CLOTHING", [garment],
            batch_id, imported_at)
        ensure(history_ok, "Project import history append failed: %s" % history_result)
        with open(manifest_path, "r", encoding="utf-8") as stream:
            project_payload = json.load(stream)
        ensure(project_payload.get("application") == "RealHuman Studio"
               and len(project_payload.get("asset_sources", [])) == 1,
               "Import history append discarded project metadata or missed the batch.")
        imported_batch = project_payload["asset_sources"][0]
        ensure(imported_batch.get("batch_id") == batch_id
               and imported_batch.get("category") == "CLOTHING"
               and imported_batch.get("source_path") == os.path.normpath(os.path.abspath(source_path))
               and imported_batch.get("source_size_bytes") == os.path.getsize(source_path)
               and imported_batch.get("object_count") == 1
               and imported_batch.get("objects", [{}])[0].get("name") == garment.name,
               "Import history batch metadata is incomplete or inaccurate.")

        # Verify the portable action JSON round-trip against a second rig.
        # This bone uses Euler keys intentionally: export must serialize the
        # effective local rotation, not a stale rotation_quaternion property.
        activate(rig)
        euler_bone = rig.pose.bones["forearm.R"]
        euler_bone.rotation_mode = "XYZ"
        euler_bone.rotation_euler = (0.2, 0.4, 0.6)
        euler_bone.keyframe_insert(
            data_path="rotation_euler", frame=bpy.context.scene.frame_current)
        json_path = os.path.join(tmp, "ci_motion.json")
        ensure("FINISHED" in bpy.ops.rh_studio.export_action_json(filepath=json_path),
               "Action JSON export failed.")
        ensure(os.path.isfile(json_path), "Action JSON file was not created.")
        with open(json_path, "r", encoding="utf-8") as stream:
            action_payload = json.load(stream)
        ensure(action_payload.get("format") == "realhuman_studio_action_v1"
               and len(action_payload.get("frames", [])) >= 2,
               "Exported action JSON is missing its format marker or frame samples.")
        exported_quaternion = action_payload["frames"][-1]["bones"]["forearm.R"]["rotation_quaternion"]
        ensure(abs(exported_quaternion[0] - 1.0) > 0.01
               or any(abs(component) > 0.05 for component in exported_quaternion[1:]),
               "Euler-animated bone rotation was not converted to the exported quaternion.")
        activate(rig_copy)
        ensure("FINISHED" in bpy.ops.rh_studio.import_action_json(filepath=json_path),
               "Action JSON import failed.")
        ensure(rig_copy.animation_data.action is not None
               and rig_copy.animation_data.action.name.startswith("RH导入动作 | "),
               "Imported JSON did not create and assign a named action.")
        # A different source FPS must warn, not silently retime or mutate the scene.
        mismatched_json_path = os.path.join(tmp, "mismatched_fps_action.json")
        mismatched_payload = dict(action_payload)
        scene_fps_before = bpy.context.scene.render.fps / max(bpy.context.scene.render.fps_base, 1e-8)
        mismatched_payload["fps"] = scene_fps_before * 2.0
        with open(mismatched_json_path, "w", encoding="utf-8") as stream:
            json.dump(mismatched_payload, stream)
        ensure("FINISHED" in bpy.ops.rh_studio.import_action_json(filepath=mismatched_json_path),
               "Action JSON with a different source FPS should still import.")
        scene_fps_after = bpy.context.scene.render.fps / max(bpy.context.scene.render.fps_base, 1e-8)
        ensure(abs(scene_fps_after - scene_fps_before) < 1e-6,
               "Importing an action must not silently change the scene FPS.")
        imported_action = rig_copy.animation_data.action
        invalid_json_path = os.path.join(tmp, "invalid_action.json")
        with open(invalid_json_path, "w", encoding="utf-8") as stream:
            json.dump({"format": "not_an_action"}, stream)
        try:
            result = bpy.ops.rh_studio.import_action_json(filepath=invalid_json_path)
        except RuntimeError:
            # Blender may raise when an operator reports ERROR and returns CANCELLED.
            result = {"CANCELLED"}
        ensure("CANCELLED" in result and rig_copy.animation_data.action == imported_action,
               "Invalid JSON should be rejected without replacing the current action.")

        invalid_fps_path = os.path.join(tmp, "invalid_fps_action.json")
        invalid_fps_payload = dict(action_payload)
        invalid_fps_payload["fps"] = float("nan")
        with open(invalid_fps_path, "w", encoding="utf-8") as stream:
            json.dump(invalid_fps_payload, stream)
        try:
            result = bpy.ops.rh_studio.import_action_json(filepath=invalid_fps_path)
        except RuntimeError:
            result = {"CANCELLED"}
        ensure("CANCELLED" in result and rig_copy.animation_data.action == imported_action,
               "Non-finite FPS metadata should be rejected without replacing the current action.")

        invalid_rotation_path = os.path.join(tmp, "invalid_rotation_action.json")
        invalid_rotation_payload = dict(action_payload)
        invalid_rotation_payload["rotation_representation"] = "euler_degrees"
        with open(invalid_rotation_path, "w", encoding="utf-8") as stream:
            json.dump(invalid_rotation_payload, stream)
        try:
            result = bpy.ops.rh_studio.import_action_json(filepath=invalid_rotation_path)
        except RuntimeError:
            result = {"CANCELLED"}
        ensure("CANCELLED" in result and rig_copy.animation_data.action == imported_action,
               "Unsupported rotation representations should be rejected without replacing the current action.")

    realhuman_studio.unregister()
    ensure(not hasattr(bpy.types.Scene, "rh_studio_target_height"),
           "Scene properties were not unregistered.")
    print("REALHUMAN_STUDIO_SMOKE_TEST: PASS")
    print("Blender runtime:", bpy.app.version_string)


try:
    run()
except Exception:
    traceback.print_exc()
    raise
