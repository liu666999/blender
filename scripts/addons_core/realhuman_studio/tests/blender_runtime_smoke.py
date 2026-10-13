# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless Blender smoke test for RealHuman Studio operators.

Run from the repository root:
  blender --background --factory-startup --python \
    scripts/addons_core/realhuman_studio/tests/blender_runtime_smoke.py
"""
import sys
from pathlib import Path

import bpy

ADDON_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADDON_PARENT))

# Start from a deterministic empty scene.
bpy.ops.wm.read_factory_settings(use_empty=True)

import realhuman_studio  # noqa: E402

registered = False
try:
    realhuman_studio.register()
    registered = True

    for operator_name in (
        "setup_project", "create_layers", "generate_simple_rig",
        "apply_pose_preset", "insert_pose_keyframe", "save_pose_preset",
        "load_pose_preset", "simple_2d_pose_pad",
    ):
        namespace = getattr(bpy.ops.rh_studio, operator_name, None)
        assert namespace is not None, "Operator did not register: " + operator_name

    scene = bpy.context.scene
    bpy.ops.rh_studio.create_layers()
    assert bpy.data.collections.get("RealHuman Studio") is not None

    # Make a simple body-shaped mesh for the bbox-based rig generator.
    vertices = [
        (-0.28, -0.12, 0.0), (0.28, -0.12, 0.0),
        (0.28, 0.12, 0.0), (-0.28, 0.12, 0.0),
        (-0.18, -0.10, 1.75), (0.18, -0.10, 1.75),
        (0.18, 0.10, 1.75), (-0.18, 0.10, 1.75),
    ]
    faces = [
        (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
        (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new("RH CI Smoke Body Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    body = bpy.data.objects.new("RH CI Smoke Body", mesh)
    scene.collection.objects.link(body)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.context.view_layer.update()

    result = bpy.ops.rh_studio.generate_simple_rig("EXEC_DEFAULT", auto_bind=False)
    assert "FINISHED" in result, "Rig generation failed: " + repr(result)
    rig = bpy.context.active_object
    assert rig and rig.type == "ARMATURE", "Rig was not made active"
    required_bones = (
        "root", "spine", "chest", "neck", "head",
        "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R",
        "hand.L", "hand.R", "thigh.L", "thigh.R",
        "shin.L", "shin.R", "foot.L", "foot.R",
    )
    missing = [name for name in required_bones if rig.pose.bones.get(name) is None]
    assert not missing, "Generated rig is missing bones: " + ", ".join(missing)

    result = bpy.ops.rh_studio.apply_pose_preset("EXEC_DEFAULT", preset="ARMS_UP")
    assert "FINISHED" in result, "Pose preset failed: " + repr(result)
    scene.frame_set(1)
    result = bpy.ops.rh_studio.insert_pose_keyframe("EXEC_DEFAULT")
    assert "FINISHED" in result, "Keyframe insertion failed: " + repr(result)
    assert rig.animation_data and rig.animation_data.action, "No Action created"

    result = bpy.ops.rh_studio.save_pose_preset("EXEC_DEFAULT", preset_name="CI Smoke")
    assert "FINISHED" in result, "Pose save failed: " + repr(result)
    scene["rh_ci_pose_test"] = True
    result = bpy.ops.rh_studio.apply_pose_preset("EXEC_DEFAULT", preset="RELAXED")
    assert "FINISHED" in result, "Second pose preset failed: " + repr(result)
    result = bpy.ops.rh_studio.load_pose_preset("EXEC_DEFAULT", preset_name="CI Smoke")
    assert "FINISHED" in result, "Pose load failed: " + repr(result)

    print("REALHUMAN_SMOKE_TEST_PASS version=%s" % bpy.app.version_string)
finally:
    if registered:
        realhuman_studio.unregister()
