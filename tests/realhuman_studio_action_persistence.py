# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end .blend round-trip test for named RealHuman Studio action sets.

Run with the branch-matched Blender executable:
  blender --background --factory-startup --python tests/realhuman_studio_action_persistence.py

This launches a second Blender process to reopen the saved file and verify that
the named action, fake-user persistence flag, rig assignment, and keyed values
survive a real save/reopen cycle.
"""
import os
import subprocess
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


def main():
    temp_dir = tempfile.mkdtemp(prefix="rh_studio_action_roundtrip_")
    blend_path = os.path.join(temp_dir, "action_roundtrip.blend")
    checker_path = os.path.join(temp_dir, "verify_reopened_action.py")
    try:
        realhuman_studio.register()
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)

        arm_data = bpy.data.armatures.new("RH Persistence Test Rig")
        rig = bpy.data.objects.new("RH Persistence Test Rig", arm_data)
        bpy.context.scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bone = arm_data.edit_bones.new("forearm.R")
        bone.head = (0.0, 0.0, 0.0)
        bone.tail = (0.0, 0.0, 1.0)
        bpy.ops.object.mode_set(mode="POSE")

        bpy.context.scene.frame_set(1)
        rig.pose.bones["forearm.R"].scale = (1.0, 1.0, 1.0)
        rig.pose.bones["forearm.R"].keyframe_insert(data_path="scale", frame=1, group="forearm.R")
        bpy.context.scene.frame_set(13)
        rig.pose.bones["forearm.R"].scale = (1.2, 1.1, 0.9)
        rig.pose.bones["forearm.R"].keyframe_insert(data_path="scale", frame=13, group="forearm.R")
        bpy.ops.object.mode_set(mode="OBJECT")

        result = bpy.ops.rh_studio.save_action_set(action_set_name="Persistence CI")
        ensure("FINISHED" in result, "The action-set save operator did not finish.")
        action_name = "RH动作集 | Persistence CI"
        action = bpy.data.actions.get(action_name)
        ensure(action is not None and action.use_fake_user,
               "The named action set is missing or lacks its persistence user.")
        rig.animation_data.action = action
        bpy.context.scene.frame_set(13)
        bpy.context.view_layer.update()
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)

        checker = r'''import bpy

def ensure(condition, message):
    if not condition:
        raise AssertionError(message)

action_name = "RH动作集 | Persistence CI"
action = bpy.data.actions.get(action_name)
ensure(action is not None, "Named action set did not survive .blend reopen.")
ensure(action.use_fake_user, "Named action set lost its fake-user persistence flag.")
rig = bpy.data.objects.get("RH Persistence Test Rig")
ensure(rig is not None and rig.type == "ARMATURE", "Test rig did not survive .blend reopen.")
ensure(rig.animation_data is not None and rig.animation_data.action == action,
       "The reopened rig is not assigned to the saved named action set.")
ensure(action.frame_range[0] <= 1 and action.frame_range[1] >= 13,
       "Keyed frame range did not survive .blend reopen.")
bpy.context.scene.frame_set(13)
bpy.context.view_layer.update()
scale = rig.pose.bones["forearm.R"].scale
ensure(abs(scale.x - 1.2) < 1e-3 and abs(scale.y - 1.1) < 1e-3
       and abs(scale.z - 0.9) < 1e-3,
       "Keyed scale values did not evaluate after .blend reopen.")
print("REALHUMAN_STUDIO_ACTION_PERSISTENCE: PASS")
'''
        with open(checker_path, "w", encoding="utf-8") as stream:
            stream.write(checker)
        command = [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            blend_path,
            "--python",
            checker_path,
        ]
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=180, check=False,
        )
        print(completed.stdout)
        ensure(completed.returncode == 0,
               "Child Blender failed while reopening the .blend file (exit %d)." %
               completed.returncode)
        ensure("REALHUMAN_STUDIO_ACTION_PERSISTENCE: PASS" in completed.stdout,
               "Reopened-file verifier did not reach its PASS marker.")
        print("REALHUMAN_STUDIO_ACTION_PERSISTENCE: PASS")
    finally:
        # Blender can keep the just-saved file open in this process; remove the
        # temporary directory only after the child process has exited.
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
