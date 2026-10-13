# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Functional operators for the RealHuman Studio workflow."""
import json
import math
import os
from pathlib import Path
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Quaternion, Vector
from . import CATEGORY_ITEMS

ROOT_COLLECTION = "RealHuman Studio"
CATEGORY_COLLECTIONS = {
    "BASE_BODY": "01 基础人体", "SKIN": "02 皮肤", "BONES": "03 骨骼",
    "MUSCLES": "04 肌肉", "ORGANS": "05 器官", "NERVES": "06 神经",
    "VESSELS": "07 血管", "CLOTHING": "08 服装",
    "RIG": "09 骨架绑定", "OTHER": "10 其他资源",
}
SUPPORTED_IMPORTS = {".obj", ".fbx", ".glb", ".gltf", ".stl", ".ply"}

def category_collection(scene, category, create=False):
    """Return a category collection, optionally creating the collection scaffold."""
    name = CATEGORY_COLLECTIONS.get(category)
    if not name:
        return None
    root = bpy.data.collections.get(ROOT_COLLECTION)
    if root is None:
        if not create:
            return None
        root = bpy.data.collections.new(ROOT_COLLECTION)
    if scene.collection.children.get(root.name) is None:
        scene.collection.children.link(root)
    collection = root.children.get(name)
    if collection is None and create:
        collection = bpy.data.collections.new(name)
        root.children.link(collection)
    return collection

def ensure_category_scaffold(scene):
    for category, _label, _description in CATEGORY_ITEMS:
        category_collection(scene, category, create=True)

def move_objects_to_category(objects, scene, category, source_path=""):
    target = category_collection(scene, category, create=True)
    for obj in objects:
        for old_collection in list(obj.users_collection):
            if old_collection != target:
                old_collection.objects.unlink(obj)
        if target.objects.get(obj.name) is None:
            target.objects.link(obj)
        obj["rh_studio_category"] = category
        if source_path:
            obj["rh_studio_source_path"] = os.path.normpath(source_path)
    return target

def _call_import_operator(filepath):
    extension = Path(filepath).suffix.lower()
    candidates = {
        ".obj": (("wm", "obj_import"), ("import_scene", "obj")),
        ".fbx": (("import_scene", "fbx"),),
        ".glb": (("import_scene", "gltf"),), ".gltf": (("import_scene", "gltf"),),
        ".stl": (("wm", "stl_import"), ("import_mesh", "stl")),
        ".ply": (("wm", "ply_import"), ("import_mesh", "ply")),
    }.get(extension, ())
    if not candidates:
        raise RuntimeError("不支持的文件格式：" + extension)
    errors = []
    for namespace, operator_name in candidates:
        try:
            operator = getattr(getattr(bpy.ops, namespace), operator_name)
            result = operator(filepath=filepath)
            if "FINISHED" in result:
                return result
            errors.append(namespace + "." + operator_name + " 未完成")
        except Exception as exc:
            errors.append(namespace + "." + operator_name + ": " + str(exc))
    raise RuntimeError("没有可用的导入器。 " + " | ".join(errors[-2:]))

class RH_OT_setup_project(bpy.types.Operator):
    bl_idname = "rh_studio.setup_project"
    bl_label = "创建项目目录"
    bl_description = "Create the project folder layout and a JSON project manifest"
    bl_options = {"REGISTER", "UNDO"}
    project_name: StringProperty(name="项目名称", default="RealHumanProject")
    project_root: StringProperty(name="保存位置", subtype="DIR_PATH", default="//")

    def invoke(self, context, event):
        self.project_root = context.scene.rh_studio_project_root or "//"
        if bpy.data.filepath and self.project_name == "RealHumanProject":
            self.project_name = Path(bpy.data.filepath).stem
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, context):
        self.layout.prop(self, "project_name")
        self.layout.prop(self, "project_root")

    def execute(self, context):
        name = self.project_name.strip()
        if not name or name in {".", ".."} or any(ch in name for ch in ("/", "\\", "\0")):
            self.report({"ERROR"}, "项目名称无效。")
            return {"CANCELLED"}
        base = os.path.abspath(bpy.path.abspath(self.project_root or "//"))
        project_dir = os.path.join(base, name)
        folders = ("models", "anatomy", "clothing", "textures", "exports", "logs")
        try:
            os.makedirs(project_dir, exist_ok=True)
            for folder in folders:
                os.makedirs(os.path.join(project_dir, folder), exist_ok=True)
            manifest = {
                "schema_version": 1, "application": "RealHuman Studio",
                "project_name": name, "blender_version": bpy.app.version_string,
                "created_folders": list(folders), "asset_sources": [],
            }
            with open(os.path.join(project_dir, "realhuman_project.json"), "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except OSError as exc:
            self.report({"ERROR"}, "无法创建项目目录：" + str(exc))
            return {"CANCELLED"}
        context.scene.rh_studio_project_root = project_dir + os.sep
        self.report({"INFO"}, "项目已创建：" + project_dir)
        return {"FINISHED"}

class RH_OT_create_layers(bpy.types.Operator):
    bl_idname = "rh_studio.create_layers"
    bl_label = "创建解剖图层"
    bl_description = "Create the standard RealHuman Studio collection hierarchy"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        ensure_category_scaffold(context.scene)
        self.report({"INFO"}, "已创建 10 个分类图层。")
        return {"FINISHED"}

class RH_OT_import_asset(bpy.types.Operator, ImportHelper):
    bl_idname = "rh_studio.import_asset"
    bl_label = "导入模型到当前分类"
    bl_description = "Import a mesh/rig file and place its objects into the selected category"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ""
    filter_glob: StringProperty(default="*.obj;*.fbx;*.glb;*.gltf;*.stl;*.ply", options={"HIDDEN"})
    category: EnumProperty(name="分类", items=CATEGORY_ITEMS, default="BASE_BODY")

    def invoke(self, context, event):
        root = bpy.path.abspath(context.scene.rh_studio_library_root)
        if os.path.isdir(root):
            self.filepath = root + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        if not os.path.isfile(filepath):
            self.report({"ERROR"}, "请先选择一个真实存在的模型文件。")
            return {"CANCELLED"}
        if Path(filepath).suffix.lower() not in SUPPORTED_IMPORTS:
            self.report({"ERROR"}, "格式不支持。支持 OBJ、FBX、GLB、GLTF、STL、PLY。")
            return {"CANCELLED"}
        before = {obj.as_pointer() for obj in bpy.data.objects}
        try:
            _call_import_operator(filepath)
            imported = [obj for obj in bpy.data.objects if obj.as_pointer() not in before]
            if not imported:
                self.report({"WARNING"}, "导入器完成了操作，但没有产生新对象。")
                return {"CANCELLED"}
            move_objects_to_category(imported, context.scene, self.category, filepath)
            for obj in list(context.selected_objects):
                obj.select_set(False)
            for obj in imported:
                try:
                    obj.select_set(True)
                except RuntimeError:
                    pass
            try:
                context.view_layer.objects.active = next(
                    (obj for obj in imported if obj.type == "MESH"), imported[0])
            except (RuntimeError, StopIteration):
                pass
        except Exception as exc:
            self.report({"ERROR"}, "导入失败：" + str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "已导入 %d 个对象到「%s」。" %
                    (len(imported), CATEGORY_COLLECTIONS[self.category]))
        return {"FINISHED"}

class RH_OT_assign_category(bpy.types.Operator):
    bl_idname = "rh_studio.assign_category"
    bl_label = "归入分类"
    bl_description = "Move selected objects into a RealHuman Studio category collection"
    bl_options = {"REGISTER", "UNDO"}
    category: EnumProperty(name="目标分类", items=CATEGORY_ITEMS, default="BASE_BODY")
    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({"WARNING"}, "请先选择一个或多个对象。")
            return {"CANCELLED"}
        move_objects_to_category(selected, context.scene, self.category)
        self.report({"INFO"}, "已整理 %d 个对象。" % len(selected))
        return {"FINISHED"}

class RH_OT_toggle_category(bpy.types.Operator):
    bl_idname = "rh_studio.toggle_category"
    bl_label = "切换图层可见性"
    bl_options = {"REGISTER", "UNDO"}
    category: EnumProperty(name="分类", items=CATEGORY_ITEMS)
    def execute(self, context):
        collection = category_collection(context.scene, self.category)
        if collection is None:
            self.report({"INFO"}, "该图层尚不存在，请先创建解剖图层。")
            return {"CANCELLED"}
        collection.hide_viewport = not collection.hide_viewport
        return {"FINISHED"}

class RH_OT_select_category(bpy.types.Operator):
    bl_idname = "rh_studio.select_category"
    bl_label = "选择图层对象"
    bl_options = {"REGISTER", "UNDO"}
    category: EnumProperty(name="分类", items=CATEGORY_ITEMS)
    def execute(self, context):
        collection = category_collection(context.scene, self.category)
        if collection is None:
            self.report({"INFO"}, "该图层尚不存在。")
            return {"CANCELLED"}
        collection.hide_viewport = False
        objects = [obj for obj in collection.objects if obj.name in context.view_layer.objects]
        for obj in list(context.selected_objects):
            obj.select_set(False)
        for obj in objects:
            obj.select_set(True)
        if objects:
            context.view_layer.objects.active = objects[0]
            self.report({"INFO"}, "已选择 %d 个对象。" % len(objects))
            return {"FINISHED"}
        self.report({"INFO"}, "此分类目前没有对象。")
        return {"CANCELLED"}

class RH_OT_fit_height(bpy.types.Operator):
    bl_idname = "rh_studio.fit_height"
    bl_label = "校准人体身高"
    bl_description = "Uniformly scale the active mesh to the target height and place its bottom on Z=0"
    bl_options = {"REGISTER", "UNDO"}
    target_height: FloatProperty(name="目标身高（米）", default=1.75, min=0.1, max=3.0)
    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"
    def execute(self, context):
        obj = context.active_object
        current_height = float(obj.dimensions.z)
        if current_height <= 1e-8:
            self.report({"ERROR"}, "当前对象高度为零，无法校准。")
            return {"CANCELLED"}
        factor = self.target_height / current_height
        obj.scale = tuple(component * factor for component in obj.scale)
        context.view_layer.update()
        world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        if world_corners:
            obj.location.z -= min(point.z for point in world_corners)
        context.view_layer.update()
        self.report({"INFO"}, "身高已校准；请检查模型朝向和场景单位。")
        return {"FINISHED"}

class RH_OT_reset_shape_keys(bpy.types.Operator):
    bl_idname = "rh_studio.reset_shape_keys"
    bl_label = "重置形态键"
    bl_description = "Set every non-Basis shape key on the active mesh to zero"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.data.shape_keys)
    def execute(self, context):
        keys = context.active_object.data.shape_keys.key_blocks
        count = 0
        for index, key in enumerate(keys):
            if index == 0 and key.name.lower() == "basis":
                continue
            key.value = 0.0
            count += 1
        self.report({"INFO"}, "已重置 %d 个形态键。" % count)
        return {"FINISHED"}

class RH_OT_set_view(bpy.types.Operator):
    bl_idname = "rh_studio.set_view"
    bl_label = "切换标准视图"
    axis: EnumProperty(name="视图", items=(
        ("FRONT", "前视图", ""), ("BACK", "后视图", ""),
        ("LEFT", "左视图", ""), ("RIGHT", "右视图", ""),
        ("TOP", "顶视图", ""), ("BOTTOM", "底视图", "")))
    def execute(self, context):
        try:
            bpy.ops.view3d.view_axis(type=self.axis)
        except Exception as exc:
            self.report({"ERROR"}, "无法切换视图：" + str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}

class RH_OT_export_model(bpy.types.Operator, ExportHelper):
    bl_idname = "rh_studio.export_model"
    bl_label = "导出所选模型"
    bl_description = "Export selected objects to GLB, FBX, or OBJ"
    bl_options = {"REGISTER"}
    filename_ext = ".glb"
    filter_glob: StringProperty(default="*.glb;*.fbx;*.obj", options={"HIDDEN"})
    export_format: EnumProperty(name="格式", items=(
        ("GLB", "glTF 二进制（GLB）", "Portable single-file glTF export"),
        ("FBX", "FBX", "Export selected objects to FBX"),
        ("OBJ", "OBJ", "Export selected objects to OBJ")), default="GLB")
    def execute(self, context):
        if not context.selected_objects:
            self.report({"ERROR"}, "请先选择要导出的对象。")
            return {"CANCELLED"}
        extensions = {"GLB": ".glb", "FBX": ".fbx", "OBJ": ".obj"}
        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        extension = extensions[self.export_format]
        if Path(filepath).suffix.lower() != extension:
            filepath = str(Path(filepath).with_suffix(extension))
        try:
            if self.export_format == "GLB":
                bpy.ops.export_scene.gltf(filepath=filepath, export_format="GLB", use_selection=True)
            elif self.export_format == "FBX":
                bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True, add_leaf_bones=False)
            elif hasattr(bpy.ops.wm, "obj_export"):
                bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True)
            else:
                bpy.ops.export_scene.obj(filepath=filepath, use_selection=True)
        except Exception as exc:
            self.report({"ERROR"}, "导出失败：" + str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "已导出：" + filepath)
        return {"FINISHED"}


class RH_OT_create_fabric_print(bpy.types.Operator):
    bl_idname = "rh_studio.create_fabric_print"
    bl_label = "生成布料印花材质"
    bl_description = "Create a UV-mapped procedural fabric print and assign it to selected garment meshes"
    bl_options = {"REGISTER", "UNDO"}

    pattern: EnumProperty(name="图案", items=(
        ("DOTS", "圆点", "Voronoi-based dotted print"),
        ("STRIPES", "条纹", "Wave-based stripe print"),
        ("CHECKER", "格纹", "Checkerboard print")), default="DOTS")
    density: FloatProperty(name="图案密度", description="Higher values create more repeats per UV tile", default=12.0, min=1.0, max=100.0)
    sparsity: FloatProperty(name="稀疏度", description="Higher values leave more base fabric visible", default=0.35, min=0.0, max=0.95, subtype="FACTOR")
    rotation: FloatProperty(name="旋转（度）", default=0.0, min=-180.0, max=180.0, subtype="ANGLE")
    base_color: bpy.props.FloatVectorProperty(name="底布颜色", subtype="COLOR", size=4, min=0.0, max=1.0, default=(0.12, 0.16, 0.22, 1.0))
    print_color: bpy.props.FloatVectorProperty(name="印花颜色", subtype="COLOR", size=4, min=0.0, max=1.0, default=(0.9, 0.72, 0.38, 1.0))

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "pattern")
        layout.prop(self, "density")
        layout.prop(self, "sparsity", slider=True)
        layout.prop(self, "rotation")
        layout.prop(self, "base_color")
        layout.prop(self, "print_color")

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not meshes:
            self.report({"ERROR"}, "请先选择服装网格。")
            return {"CANCELLED"}
        material = bpy.data.materials.new(name="RH Fabric Print")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (700, 80)
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        shader.location = (440, 80)
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.location = (-800, 80)
        mapping = nodes.new("ShaderNodeMapping")
        mapping.location = (-600, 80)
        mapping.inputs["Rotation"].default_value[2] = self.rotation
        mapping.inputs["Scale"].default_value = (self.density, self.density, self.density)
        links.new(texcoord.outputs["UV"], mapping.inputs["Vector"])

        if self.pattern == "DOTS":
            texture = nodes.new("ShaderNodeTexVoronoi")
            texture.inputs["Scale"].default_value = 1.0
            value_socket = texture.outputs["Distance"]
        elif self.pattern == "STRIPES":
            texture = nodes.new("ShaderNodeTexWave")
            texture.wave_type = "BANDS"
            texture.bands_direction = "X"
            texture.inputs["Scale"].default_value = 2.0
            texture.inputs["Distortion"].default_value = 0.0
            value_socket = texture.outputs["Fac"]
        else:
            texture = nodes.new("ShaderNodeTexChecker")
            texture.inputs["Scale"].default_value = 2.0
            value_socket = texture.outputs["Fac"]
        texture.location = (-350, 80)
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])

        threshold = nodes.new("ShaderNodeMath")
        threshold.operation = "LESS_THAN"
        threshold.location = (-100, 80)
        threshold.inputs[1].default_value = max(0.02, 1.0 - self.sparsity)
        links.new(value_socket, threshold.inputs[0])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.location = (150, 80)
        mix.blend_type = "MIX"
        # RGBA Mix sockets are typed and exposed by Blender 4.x/5.x.
        links.new(threshold.outputs[0], mix.inputs[0])
        mix.inputs[1].default_value = self.base_color
        mix.inputs[2].default_value = self.print_color
        links.new(mix.outputs[0], shader.inputs["Base Color"])
        for obj in meshes:
            if not obj.data.materials:
                obj.data.materials.append(material)
            else:
                obj.data.materials[obj.active_material_index] = material
        material["rh_studio_material_type"] = "procedural_fabric_print"
        material["rh_studio_pattern"] = self.pattern
        material["rh_studio_density"] = self.density
        material["rh_studio_sparsity"] = self.sparsity
        material["rh_studio_rotation_degrees"] = self.rotation * 57.295779513
        self.report({"INFO"}, "已为 %d 个网格生成布料印花材质。请确保服装有可用 UV。" % len(meshes))
        return {"FINISHED"}



# ---------------------------------------------------------------------------
# Simple stick-figure rig, pose presets, keyframing, and expression shortcuts
# ---------------------------------------------------------------------------
def _bone_roll_axis(name):
    if name.startswith(("upper_arm", "forearm", "hand", "clavicle")):
        return Vector((0.0, 0.0, 1.0))
    if name.startswith(("thigh", "shin", "foot", "root", "spine", "chest", "neck", "head")):
        return Vector((1.0, 0.0, 0.0))
    return Vector((0.0, 0.0, 1.0))


class RH_OT_generate_simple_rig(bpy.types.Operator):
    bl_idname = "rh_studio.generate_simple_rig"
    bl_label = "生成火柴人骨架"
    bl_description = "Create a lightweight humanoid stick rig proportioned to the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    auto_bind: BoolProperty(
        name="尝试自动权重绑定",
        description="After creating the rig, ask Blender to bind the selected mesh with automatic weights",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        self.layout.label(text="按当前人体网格包围盒估算关节位置。")
        self.layout.label(text="生成后仍需检查肩、肘、膝和衣物的变形。")
        self.layout.prop(self, "auto_bind")

    def execute(self, context):
        mesh = context.active_object
        if not mesh or mesh.type != "MESH":
            self.report({"ERROR"}, "请先选择人体网格。")
            return {"CANCELLED"}

        world_corners = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
        if not world_corners:
            self.report({"ERROR"}, "无法读取人体网格边界。")
            return {"CANCELLED"}
        min_x = min(p.x for p in world_corners)
        max_x = max(p.x for p in world_corners)
        min_y = min(p.y for p in world_corners)
        max_y = max(p.y for p in world_corners)
        min_z = min(p.z for p in world_corners)
        max_z = max(p.z for p in world_corners)
        height = max_z - min_z
        if height < 0.1:
            self.report({"ERROR"}, "网格高度异常，无法估算人体关节。")
            return {"CANCELLED"}

        cx = (min_x + max_x) * 0.5
        cy = (min_y + max_y) * 0.5
        h = height
        hip_z = min_z + 0.535 * h
        chest_z = min_z + 0.765 * h
        shoulder_z = min_z + 0.805 * h
        neck_z = min_z + 0.865 * h
        head_z = min_z + 0.895 * h
        head_top = min_z + 0.985 * h
        knee_z = min_z + 0.285 * h
        ankle_z = min_z + 0.055 * h
        hip_half = max(0.055 * h, min(0.085 * h, (max_x - min_x) * 0.09))
        shoulder_half = 0.12 * h
        elbow_dist = 0.29 * h
        wrist_dist = 0.465 * h
        hand_dist = 0.50 * h
        foot_len = max(0.07 * h, (max_y - min_y) * 0.30)

        # Each tuple: head, tail, parent name, connected flag.
        bones = {
            "root": ((cx, cy, hip_z - 0.045*h), (cx, cy, hip_z), None, False),
            "spine": ((cx, cy, hip_z), (cx, cy, chest_z), "root", True),
            "chest": ((cx, cy, chest_z), (cx, cy, neck_z), "spine", True),
            "neck": ((cx, cy, neck_z), (cx, cy, head_z), "chest", True),
            "head": ((cx, cy, head_z), (cx, cy, head_top), "neck", True),
        }
        for side, sign in (("L", -1.0), ("R", 1.0)):
            hip = (cx + sign*hip_half, cy, hip_z)
            knee = (cx + sign*hip_half*1.08, cy, knee_z)
            ankle = (cx + sign*hip_half*1.08, cy, ankle_z)
            toe = (ankle[0], cy - foot_len, ankle_z + 0.005*h)
            shoulder = (cx + sign*shoulder_half, cy, shoulder_z)
            elbow = (cx + sign*elbow_dist, cy, shoulder_z - 0.01*h)
            wrist = (cx + sign*wrist_dist, cy, shoulder_z - 0.025*h)
            hand_tip = (cx + sign*hand_dist, cy - 0.015*h, shoulder_z - 0.025*h)
            bones["thigh." + side] = (hip, knee, "root", False)
            bones["shin." + side] = (knee, ankle, "thigh." + side, True)
            bones["foot." + side] = (ankle, toe, "shin." + side, True)
            bones["upper_arm." + side] = (shoulder, elbow, "chest", False)
            bones["forearm." + side] = (elbow, wrist, "upper_arm." + side, True)
            bones["hand." + side] = (wrist, hand_tip, "forearm." + side, True)

        arm_data = bpy.data.armatures.new("RH Simple Human Rig")
        rig = bpy.data.objects.new("RH Stick Rig", arm_data)
        context.scene.collection.objects.link(rig)
        rig.show_in_front = True
        arm_data.display_type = "STICK"

        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
        for obj in list(context.selected_objects):
            obj.select_set(False)
        rig.select_set(True)
        context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = {}
        for name, (head, tail, parent_name, connected) in bones.items():
            bone = arm_data.edit_bones.new(name)
            bone.head = head
            bone.tail = tail
            bone.use_connect = False
            try:
                bone.align_roll(_bone_roll_axis(name))
            except (RuntimeError, ValueError):
                pass
            edit_bones[name] = bone
        for name, (_head, _tail, parent_name, connected) in bones.items():
            bone = edit_bones[name]
            if parent_name:
                bone.parent = edit_bones[parent_name]
                bone.use_connect = connected
        bpy.ops.object.mode_set(mode="OBJECT")

        move_objects_to_category([rig], context.scene, "RIG")
        rig["rh_studio_rig_type"] = "simple_stick_humanoid"
        rig["rh_studio_source_mesh"] = mesh.name

        bound = False
        if self.auto_bind:
            try:
                for obj in list(context.selected_objects):
                    obj.select_set(False)
                mesh.select_set(True)
                rig.select_set(True)
                context.view_layer.objects.active = rig
                bpy.ops.object.parent_set(type="ARMATURE_AUTO")
                bound = bool(mesh.parent == rig and any(mod.type == "ARMATURE" and mod.object == rig
                                                        for mod in mesh.modifiers))
            except Exception as exc:
                self.report({"WARNING"}, "骨架已生成，但自动权重绑定失败；可先手动绑定后继续。原因：" + str(exc))
        # Select the rig so the user can immediately inspect/edit the stick bones.
        for obj in list(context.selected_objects):
            obj.select_set(False)
        rig.select_set(True)
        context.view_layer.objects.active = rig
        if bound:
            self.report({"INFO"}, "火柴人骨架已生成，且已尝试自动权重绑定。请检查关节变形。")
        elif self.auto_bind:
            self.report({"WARNING"}, "火柴人骨架已生成，但未确认绑定成功；请检查人体的 Armature 修改器和权重。")
        else:
            self.report({"INFO"}, "火柴人骨架已生成。可切换姿势预设并记录关键帧。")
        return {"FINISHED"}


def _rotate_pose_bone_about_world_axis(armature, bone_name, axis, degrees):
    pose_bone = armature.pose.bones.get(bone_name)
    data_bone = armature.data.bones.get(bone_name)
    if pose_bone is None or data_bone is None:
        return False
    pose_bone.rotation_mode = "QUATERNION"
    bone_world_orientation = (
        armature.matrix_world.to_quaternion() @ data_bone.matrix_local.to_quaternion()
    )
    world_delta = Quaternion(Vector(axis), math.radians(degrees))
    local_delta = bone_world_orientation.inverted() @ world_delta @ bone_world_orientation
    pose_bone.rotation_quaternion = local_delta @ pose_bone.rotation_quaternion
    return True


class RH_OT_apply_pose_preset(bpy.types.Operator):
    bl_idname = "rh_studio.apply_pose_preset"
    bl_label = "应用动作姿势预设"
    bl_description = "Apply a simple pose to a compatible humanoid armature"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(name="姿势预设", items=(
        ("REST", "复位 / T 字站姿", "Reset pose bones to their rest pose"),
        ("RELAXED", "自然放松站姿", "Lower arms to a relaxed angle"),
        ("ARMS_UP", "双手举起", "Raise both arms"),
        ("SITTING", "坐姿", "Rotate thighs forward and bend the knees"),
        ("WAVE", "挥手", "Raise the right arm and bend the elbow"),
    ), default="RELAXED")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE")

    def execute(self, context):
        rig = context.active_object
        for pose_bone in rig.pose.bones:
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pose_bone.location = (0.0, 0.0, 0.0)
        recognized = 0

        def rotate(name, axis, angle):
            nonlocal recognized
            if _rotate_pose_bone_about_world_axis(rig, name, axis, angle):
                recognized += 1

        if self.preset == "RELAXED":
            for side, sign in (("L", -1.0), ("R", 1.0)):
                rotate("upper_arm." + side, (0, 1, 0), sign * 48.0)
                rotate("forearm." + side, (1, 0, 0), sign * 8.0)
        elif self.preset == "ARMS_UP":
            for side, sign in (("L", -1.0), ("R", 1.0)):
                rotate("upper_arm." + side, (0, 1, 0), -sign * 72.0)
        elif self.preset == "SITTING":
            for side in ("L", "R"):
                rotate("thigh." + side, (1, 0, 0), -65.0)
                rotate("shin." + side, (1, 0, 0), 78.0)
        elif self.preset == "WAVE":
            rotate("upper_arm.R", (0, 1, 0), -108.0)
            rotate("forearm.R", (1, 0, 0), 68.0)
            rotate("hand.R", (0, 1, 0), 18.0)
        if self.preset != "REST" and recognized == 0:
            self.report({"WARNING"}, "当前骨架未找到 RealHuman 简易人形骨骼命名；已重置姿势。")
            return {"CANCELLED"}
        context.view_layer.update()
        self.report({"INFO"}, "已应用姿势预设「%s」。可继续手动旋转单根骨骼。" % self.preset)
        return {"FINISHED"}




class RH_OT_toggle_pose_mode(bpy.types.Operator):
    bl_idname = "rh_studio.toggle_pose_mode"
    bl_label = "切换姿势编辑模式"
    bl_description = "Switch the active armature between Object Mode and Pose Mode"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE")

    def execute(self, context):
        rig = context.active_object
        target_mode = "OBJECT" if rig.mode == "POSE" else "POSE"
        try:
            bpy.ops.object.mode_set(mode=target_mode)
        except Exception as exc:
            self.report({"ERROR"}, "无法切换骨架编辑模式：" + str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "已切换到%s。" % ("对象模式" if target_mode == "OBJECT" else "姿势模式"))
        return {"FINISHED"}


class RH_OT_insert_pose_keyframe(bpy.types.Operator):
    bl_idname = "rh_studio.insert_pose_keyframe"
    bl_label = "记录当前姿势关键帧"
    bl_description = "Insert rotation/location keyframes for all pose bones at the current timeline frame"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE" and len(obj.pose.bones) > 0)

    def execute(self, context):
        rig = context.active_object
        frame = context.scene.frame_current
        inserted = 0
        for pose_bone in rig.pose.bones:
            rotation_path = "rotation_quaternion" if pose_bone.rotation_mode == "QUATERNION" else "rotation_euler"
            pose_bone.keyframe_insert(data_path=rotation_path, frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
            inserted += 1
        if rig.animation_data and rig.animation_data.action:
            rig.animation_data.action.name = rig.animation_data.action.name or "RH Pose Action"
        self.report({"INFO"}, "已在第 %d 帧为 %d 根骨骼记录关键帧。" % (frame, inserted))
        return {"FINISHED"}


EXPRESSION_TOKENS = {
    "SMILE": ("smile", "happy", "joy", "grin", "微笑", "嘴角上扬", "笑"),
    "SAD": ("sad", "frown", "sadness", "悲伤", "难过", "沮丧"),
    "ANGRY": ("angry", "anger", "browdown", "brow_down", "愤怒", "生气"),
    "SURPRISE": ("surprise", "jawopen", "jaw_open", "mouthopen", "wideeye", "惊讶", "张嘴", "瞪眼"),
    "BLINK": ("blink", "eyeclose", "eye_close", "closeeye", "眨眼", "闭眼"),
}
EXPRESSION_HINTS = tuple(token for group in EXPRESSION_TOKENS.values() for token in group)


class RH_OT_expression_preset(bpy.types.Operator):
    bl_idname = "rh_studio.expression_preset"
    bl_label = "表情预设"
    bl_description = "Drive facial shape keys already present on the active mesh using common name matching"
    bl_options = {"REGISTER", "UNDO"}

    preset: EnumProperty(name="表情", items=(
        ("SMILE", "微笑", "Set recognized smile-related shape keys"),
        ("SAD", "悲伤", "Set recognized sadness-related shape keys"),
        ("ANGRY", "愤怒", "Set recognized anger/brow-related shape keys"),
        ("SURPRISE", "惊讶", "Set recognized surprise/eye/mouth shape keys"),
        ("BLINK", "眨眼", "Set recognized eye-blink shape keys"),
        ("RESET", "表情复位", "Reset recognized expression shape keys"),
    ), default="SMILE")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.data.shape_keys
                    and len(obj.data.shape_keys.key_blocks) > 1)

    def execute(self, context):
        obj = context.active_object
        keys = list(obj.data.shape_keys.key_blocks)[1:]
        expression_keys = [key for key in keys
                           if any(token in key.name.lower() for token in EXPRESSION_HINTS)]
        if self.preset == "RESET":
            for key in expression_keys:
                key.value = 0.0
            self.report({"INFO"}, "已复位 %d 个可识别的表情形态键。" % len(expression_keys))
            return {"FINISHED"} if expression_keys else {"CANCELLED"}

        tokens = EXPRESSION_TOKENS[self.preset]
        matched = [key for key in expression_keys
                   if any(token in key.name.lower() for token in tokens)]
        if not matched:
            self.report({"WARNING"}, "没有找到名称可识别的表情形态键；请确认模型已有表情 Shape Keys。")
            return {"CANCELLED"}
        for key in expression_keys:
            key.value = 0.0
        for key in matched:
            key.value = 1.0
        self.report({"INFO"}, "已触发 %d 个匹配的表情形态键。" % len(matched))
        return {"FINISHED"}


CLASSES = (
    RH_OT_setup_project, RH_OT_create_layers, RH_OT_import_asset,
    RH_OT_assign_category, RH_OT_toggle_category, RH_OT_select_category,
    RH_OT_fit_height, RH_OT_reset_shape_keys, RH_OT_set_view, RH_OT_export_model,
    RH_OT_create_fabric_print, RH_OT_generate_simple_rig,
    RH_OT_apply_pose_preset, RH_OT_toggle_pose_mode,
    RH_OT_insert_pose_keyframe, RH_OT_expression_preset,
)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
