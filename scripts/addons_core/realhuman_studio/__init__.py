# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""RealHuman Studio tools shipped with the Blender source tree."""
bl_info = {
    "name": "RealHuman Studio", "author": "RealHuman Studio contributors",
    "version": (0, 1, 0), "blender": (5, 4, 0),
    "location": "View3D > Sidebar > RealHuman",
    "description": "Human asset import, anatomy layers, shape-key controls, and export workflow",
    "category": "3D View",
}
import bpy
from bpy.props import EnumProperty, FloatProperty, StringProperty

CATEGORY_ITEMS = (
    ("BASE_BODY", "基础人体", "Primary full-body mesh"),
    ("SKIN", "皮肤", "Skin and surface meshes"),
    ("FAT", "脂肪层", "Subcutaneous fat and adipose layers"),
    ("BONES", "骨骼", "Skeletal anatomy"),
    ("MUSCLES", "肌肉", "Muscle anatomy"),
    ("NERVES", "神经", "Nervous system"),
    ("VESSELS", "血管", "Vascular system"),
    ("ORGANS", "内脏器官", "Internal organs"),
    ("HAIR", "毛发", "Scalp hair, body hair, brows and lashes"),
    ("TISSUE", "筋膜与其他组织", "Fascia and other connective tissues"),
    ("CLOTHING", "服装", "Clothing and accessories"),
    ("RIG", "骨架绑定", "Armature and rigging objects"),
    ("OTHER", "其他", "Other imported assets"),
)

from . import operators, ui

def register():
    bpy.types.Scene.rh_studio_import_category = EnumProperty(
        name="导入分类", items=CATEGORY_ITEMS, default="BASE_BODY")
    bpy.types.Scene.rh_studio_target_height = FloatProperty(
        name="目标身高", description="Uniformly scale the active mesh to this world-space height",
        default=1.75, min=0.1, max=3.0, precision=3, unit="LENGTH")
    bpy.types.Scene.rh_studio_library_root = StringProperty(
        name="资源目录", description="Starting directory for model import dialogs",
        default="//", subtype="DIR_PATH")
    bpy.types.Scene.rh_studio_project_root = StringProperty(
        name="项目目录", description="Where project folders and manifest are stored",
        default="//", subtype="DIR_PATH")
    operators.register()
    ui.register()

def unregister():
    ui.unregister()
    operators.unregister()
    for name in ("rh_studio_import_category", "rh_studio_target_height",
                 "rh_studio_library_root", "rh_studio_project_root"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
