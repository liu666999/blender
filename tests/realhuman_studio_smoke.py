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
    ensure(tuple(bpy.app.version) >= (4, 5, 0), "Expected Blender 4.5+ runtime.")
    realhuman_studio.register()
    ensure(hasattr(bpy.types.Scene, "rh_studio_target_height"),
           "Scene properties did not register.")

    clean_scene()

    # Exercise the same rig-generation operator the UI calls, but disable
    # automatic weights so this test is deterministic and mesh-topology agnostic.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.95))
    mesh = bpy.context.object
    mesh.name = "RH CI Human Mesh"
    mesh.scale = (0.28, 0.18, 0.95)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ensure(mesh.dimensions.z > 1.5, "Test mesh should be tall enough to rig.")
    activate(mesh)

    result = bpy.ops.rh_studio.generate_simple_rig(auto_bind=False)
    ensure("FINISHED" in result, "Simple rig generation operator failed.")
    rig = bpy.context.object
    ensure(rig and rig.type == "ARMATURE", "Rig was not made active.")
    for name in ("root", "spine", "chest", "neck", "head",
                 "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R",
                 "hand.L", "hand.R", "thigh.L", "thigh.R", "shin.L", "shin.R",
                 "foot.L", "foot.R"):
        ensure(rig.pose.bones.get(name) is not None, "Missing bone: " + name)

    ensure("FINISHED" in bpy.ops.rh_studio.apply_pose_preset(preset="ARMS_UP"),
           "Apply pose preset failed.")
    ensure("FINISHED" in bpy.ops.rh_studio.insert_pose_keyframe(),
           "Keyframe insertion failed.")
    ensure(rig.animation_data is not None, "Pose action was not created.")
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
