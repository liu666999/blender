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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "addons_core"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import realhuman_studio


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

    clean_scene()

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

    ensure("FINISHED" in bpy.ops.rh_studio.apply_pose_preset(preset="ARMS_UP"),
           "Apply pose preset failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.insert_pose_keyframe(),
           "Keyframe insertion failed.")
    ensure(rig.animation_data is not None, "Pose action was not created.")

    # Give the clip a real span, then verify reusable action-set save/load and
    # that saving a duplicate name never removes an Action used by another rig.
    bpy.context.scene.frame_set(bpy.context.scene.frame_current + 12)
    ensure("FINISHED" in bpy.ops.rh_studio.insert_pose_keyframe(),
           "Second keyframe insertion failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.save_action_set(action_set_name="CI Motion"),
           "Saving a named action set failed.")
    saved_action = bpy.data.actions.get("RH动作集 | CI Motion")
    ensure(saved_action is not None and saved_action.use_fake_user,
           "Named action set was not preserved in the .blend data.")
    rig_copy = rig.copy()
    rig_copy.data = rig.data.copy()
    bpy.context.scene.collection.objects.link(rig_copy)
    rig_copy.animation_data_create()
    rig_copy.animation_data.action = saved_action
    ensure("FINISHED" in bpy.ops.rh_studio.save_action_set(action_set_name="CI Motion"),
           "Saving a duplicate action-set name should safely create a numbered copy.")
    ensure(rig_copy.animation_data.action == saved_action and saved_action.name in bpy.data.actions,
           "Saving a duplicate action set broke an Action used by another rig.")
    ensure("FINISHED" in bpy.ops.rh_studio.load_action_set(action_set="RH动作集 | CI Motion"),
           "Loading a named action set failed.")
    ensure(rig.animation_data.action == saved_action,
           "The selected named action set was not assigned to the rig.")
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

        # Verify the portable action JSON round-trip against a second rig.
        json_path = os.path.join(tmp, "ci_motion.json")
        activate(rig)
        ensure("FINISHED" in bpy.ops.rh_studio.export_action_json(filepath=json_path),
               "Action JSON export failed.")
        ensure(os.path.isfile(json_path), "Action JSON file was not created.")
        with open(json_path, "r", encoding="utf-8") as stream:
            action_payload = json.load(stream)
        ensure(action_payload.get("format") == "realhuman_studio_action_v1"
               and len(action_payload.get("frames", [])) >= 2,
               "Exported action JSON is missing its format marker or frame samples.")
        activate(rig_copy)
        ensure("FINISHED" in bpy.ops.rh_studio.import_action_json(filepath=json_path),
               "Action JSON import failed.")
        ensure(rig_copy.animation_data.action is not None
               and rig_copy.animation_data.action.name.startswith("RH导入动作 | "),
               "Imported JSON did not create and assign a named action.")
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
