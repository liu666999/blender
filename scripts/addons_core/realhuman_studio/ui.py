# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""3D View sidebar UI for RealHuman Studio."""
import bpy
from . import CATEGORY_ITEMS
from .operators import category_collection

def _active_shape_keys(context):
    obj = context.active_object
    if obj and obj.type == "MESH" and obj.data.shape_keys:
        return obj.data.shape_keys.key_blocks
    return None

class RH_PT_main(bpy.types.Panel):
    bl_label = "RealHuman Studio"
    bl_idname = "RH_PT_realhuman_studio_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RealHuman"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        project = layout.box()
        project.label(text="项目管理", icon="FILE_FOLDER")
        project.prop(scene, "rh_studio_project_root", text="项目目录")
        project.operator("rh_studio.setup_project", icon="NEWFOLDER", text="创建项目目录")

        assets = layout.box()
        assets.label(text="人体与资源", icon="OUTLINER_OB_MESH")
        assets.prop(scene, "rh_studio_library_root", text="资源目录")
        assets.prop(scene, "rh_studio_import_category", text="导入分类")
        op = assets.operator("rh_studio.import_asset", icon="IMPORT", text="选择模型并导入")
        op.category = scene.rh_studio_import_category
        row = assets.row(align=True)
        row.operator("rh_studio.create_layers", icon="OUTLINER_COLLECTION", text="初始化分类")
        assign = row.operator("rh_studio.assign_category", icon="FILE_PARENT", text="整理所选")
        assign.category = scene.rh_studio_import_category

        layers = layout.box()
        layers.label(text="解剖图层", icon="OUTLINER")
        for category, label, _description in CATEGORY_ITEMS:
            collection = category_collection(scene, category)
            row = layers.row(align=True)
            count = len(collection.objects) if collection else 0
            row.label(text=label, icon="OUTLINER_COLLECTION")
            row.label(text=str(count))
            toggle = row.operator(
                "rh_studio.toggle_category", text="",
                icon="HIDE_ON" if collection and collection.hide_viewport else "HIDE_OFF",
                emboss=False)
            toggle.category = category
            select = row.operator("rh_studio.select_category", text="", icon="RESTRICT_SELECT_OFF")
            select.category = category

        body = layout.box()
        body.label(text="比例与形态", icon="MOD_MESHDEFORM")
        body.prop(scene, "rh_studio_target_height")
        op = body.operator("rh_studio.fit_height", icon="FULLSCREEN_ENTER", text="校准当前网格")
        op.target_height = scene.rh_studio_target_height
        if context.active_object and context.active_object.type == "MESH":
            keys = _active_shape_keys(context)
            if keys and len(keys) > 1:
                body.separator()
                body.label(text="当前网格的形态键")
                for key in list(keys)[1:]:
                    body.prop(key, "value", text=key.name, slider=True)
                body.operator("rh_studio.reset_shape_keys", icon="LOOP_BACK", text="重置形态键")
            else:
                body.label(text="当前网格没有形态键。", icon="INFO")
                body.label(text="仅显示网格本身已有的形态键。")
        else:
            body.label(text="选择一个人体网格后显示形态键。", icon="INFO")

        view = layout.box()
        view.label(text="标准视图", icon="ORIENTATION_VIEW")
        for axes in (("FRONT", "BACK"), ("LEFT", "RIGHT"), ("TOP", "BOTTOM")):
            row = view.row(align=True)
            for axis in axes:
                op = row.operator("rh_studio.set_view", text={
                    "FRONT": "前", "BACK": "后", "LEFT": "左",
                    "RIGHT": "右", "TOP": "顶", "BOTTOM": "底"}[axis])
                op.axis = axis


        fabric = layout.box()
        fabric.label(text="服装印花", icon="MATERIAL")
        fabric.label(text="选择带 UV 的服装网格，可调图案、密度、稀疏度、旋转与颜色。")
        fabric.operator("rh_studio.create_fabric_print", icon="NODE_MATERIAL", text="创建 / 应用印花材质")

        export_box = layout.box()
        export_box.label(text="导出所选对象", icon="EXPORT")
        row = export_box.row(align=True)
        for export_format, label in (("GLB", "GLB"), ("FBX", "FBX"), ("OBJ", "OBJ")):
            op = row.operator("rh_studio.export_model", text=label)
            op.export_format = export_format

CLASSES = (RH_PT_main,)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
