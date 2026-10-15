# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Functional operators for the RealHuman Studio workflow."""
import json
import math
import os
from datetime import datetime
from pathlib import Path
import uuid
import bpy
import bmesh
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix, Quaternion, Vector
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

def _insert_action_json_keyframe(bone, data_path, frame, group):
    """Small seam for testing rollback after a partial action write."""
    return bone.keyframe_insert(data_path=data_path, frame=frame, group=group)


def record_project_import(scene, filepath, category, objects, batch_id, imported_at):
    """Append one successful import batch to an existing project manifest.

    A missing project manifest is not an error: per-object metadata is still
    stored in the .blend file by the caller. Existing malformed manifests are
    left untouched rather than overwritten.
    """
    project_root = bpy.path.abspath(scene.rh_studio_project_root or "//")
    manifest_path = os.path.join(project_root, "realhuman_project.json")
    if not os.path.isfile(manifest_path):
        return False, "项目清单不存在，已只保存到当前 .blend 文件"

    try:
        with open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        if not isinstance(manifest, dict):
            raise ValueError("项目清单根节点必须是 JSON 对象")
        asset_sources = manifest.setdefault("asset_sources", [])
        if not isinstance(asset_sources, list):
            raise ValueError("asset_sources 必须是 JSON 数组")

        source = os.path.normpath(os.path.abspath(filepath))
        source_stat = os.stat(source)
        entry = {
            "batch_id": batch_id,
            "imported_at": imported_at,
            "source_path": source,
            "source_size_bytes": source_stat.st_size,
            "source_mtime": datetime.fromtimestamp(
                source_stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "category": category,
            "object_count": len(objects),
            "objects": [{"name": obj.name, "type": obj.type} for obj in objects],
        }
        asset_sources.append(entry)
        temp_path = manifest_path + "." + batch_id + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temp_path, manifest_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return False, "项目导入历史写入失败：" + str(exc)
    return True, manifest_path

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
        manifest_path = os.path.join(project_dir, "realhuman_project.json")
        folders = ("models", "anatomy", "clothing", "textures", "exports", "logs")

        # Never overwrite a project's existing manifest: it may contain import
        # history or user-defined metadata. Validate it before creating folders.
        existing_manifest = None
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as stream:
                    existing_manifest = json.load(stream)
                if not isinstance(existing_manifest, dict):
                    raise ValueError("项目清单根节点必须是 JSON 对象")
                if existing_manifest.get("application") != "RealHuman Studio":
                    raise ValueError("现有清单不属于 RealHuman Studio，拒绝覆盖")
                if not isinstance(existing_manifest.get("asset_sources", []), list):
                    raise ValueError("asset_sources 必须是 JSON 数组")
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.report({"ERROR"}, "现有项目清单无效，未覆盖任何数据：" + str(exc))
                return {"CANCELLED"}

        try:
            os.makedirs(project_dir, exist_ok=True)
            for folder in folders:
                os.makedirs(os.path.join(project_dir, folder), exist_ok=True)
            if existing_manifest is None:
                manifest = {
                    "schema_version": 1, "application": "RealHuman Studio",
                    "project_name": name, "blender_version": bpy.app.version_string,
                    "created_folders": list(folders), "asset_sources": [],
                }
                temp_path = manifest_path + "." + uuid.uuid4().hex + ".tmp"
                try:
                    with open(temp_path, "w", encoding="utf-8") as stream:
                        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                        stream.write("\n")
                    os.replace(temp_path, manifest_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
        except (OSError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, "无法创建项目目录或清单：" + str(exc))
            return {"CANCELLED"}
        context.scene.rh_studio_project_root = project_dir + os.sep
        message = "项目已创建：" if existing_manifest is None else "已复用现有项目并保留清单："
        self.report({"INFO"}, message + project_dir)
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
            batch_id = uuid.uuid4().hex
            imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
            for obj in imported:
                obj["rh_studio_import_batch_id"] = batch_id
                obj["rh_studio_imported_at"] = imported_at
            history_saved, history_message = record_project_import(
                context.scene, filepath, self.category, imported, batch_id, imported_at)
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
        self.report({"INFO"}, "已导入 %d 个对象到「%s」。批次：%s" %
                    (len(imported), CATEGORY_COLLECTIONS[self.category], batch_id[:8]))
        if not history_saved:
            self.report({"WARNING"}, history_message)
        return {"FINISHED"}

class RH_OT_export_asset_manifest(bpy.types.Operator):
    bl_idname = "rh_studio.export_asset_manifest"
    bl_label = "导出所选资源清单"
    bl_description = "Export selected asset metadata, dimensions in meters, geometry statistics and rig links to JSON"
    bl_options = {"REGISTER"}

    filepath: StringProperty(
        name="资源清单", subtype="FILE_PATH",
        default="//rh_studio_asset_manifest.json")

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        root = bpy.path.abspath(context.scene.rh_studio_project_root or "//")
        logs_dir = os.path.join(root, "logs") if root else ""
        if logs_dir and os.path.isdir(logs_dir):
            self.filepath = os.path.join(logs_dir, "asset_manifest.json")
        else:
            self.filepath = bpy.path.abspath("//rh_studio_asset_manifest.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        objects = list(context.selected_objects)
        if not objects:
            self.report({"WARNING"}, "请先选择要导出的资源。")
            return {"CANCELLED"}

        scene = context.scene
        unit_scale = float(scene.unit_settings.scale_length or 1.0)
        if not math.isfinite(unit_scale) or unit_scale <= 0.0:
            self.report({"ERROR"}, "场景单位比例无效，无法生成米制清单。")
            return {"CANCELLED"}

        records = []
        for obj in objects:
            corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            bounds = None
            if corners:
                bounds = {
                    "min_m": [round(min(point[i] for point in corners) * unit_scale, 6)
                              for i in range(3)],
                    "max_m": [round(max(point[i] for point in corners) * unit_scale, 6)
                              for i in range(3)],
                    "size_m": [round((max(point[i] for point in corners) -
                                      min(point[i] for point in corners)) * unit_scale, 6)
                               for i in range(3)],
                }

            armature_targets = []
            warnings = []
            for modifier in obj.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    armature_targets.append(modifier.object.name)
                    if modifier.object not in objects:
                        warnings.append("绑定骨架未包含在本次选择中")
            if obj.parent is not None and obj.parent.type == "ARMATURE":
                if obj.parent.name not in armature_targets:
                    armature_targets.append(obj.parent.name)
                if obj.parent not in objects:
                    warnings.append("父级骨架未包含在本次选择中")

            mesh_data = None
            if obj.type == "MESH":
                mesh_data = {
                    "vertices": len(obj.data.vertices),
                    "edges": len(obj.data.edges),
                    "polygons": len(obj.data.polygons),
                    "uv_layers": [layer.name for layer in obj.data.uv_layers],
                    "materials": [slot.material.name if slot.material else None
                                  for slot in obj.material_slots],
                    "shape_keys": [key.name for key in obj.data.shape_keys.key_blocks]
                                  if obj.data.shape_keys else [],
                }
                if not obj.data.uv_layers:
                    warnings.append("网格没有 UV 图层")
                if not obj.data.materials:
                    warnings.append("网格没有材质槽")

            records.append({
                "name": obj.name,
                "type": obj.type,
                "category": obj.get("rh_studio_category", "UNASSIGNED"),
                "source_path": obj.get("rh_studio_source_path", ""),
                "collections": sorted(collection.name for collection in obj.users_collection),
                "dimensions_world_m": [round(float(value) * unit_scale, 6)
                                        for value in obj.dimensions],
                "world_bounds": bounds,
                "location_world_m": [round(float(value) * unit_scale, 6)
                                     for value in obj.matrix_world.translation],
                "rotation_world_quaternion": [round(float(value), 8)
                                              for value in obj.matrix_world.to_quaternion()],
                "scale": [round(float(value), 8) for value in obj.scale],
                "armature_targets": sorted(set(armature_targets)),
                "mesh": mesh_data,
                "warnings": sorted(set(warnings)),
            })

        manifest = {
            "schema": "realhuman_studio_asset_manifest_v1",
            "application": "RealHuman Studio",
            "blender_version": bpy.app.version_string,
            "scene_unit_system": scene.unit_settings.system,
            "meters_per_blender_unit": unit_scale,
            "object_count": len(records),
            "objects": records,
        }
        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        except (OSError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, "写入资源清单失败：" + str(exc))
            return {"CANCELLED"}

        warning_count = sum(len(record["warnings"]) for record in records)
        self.report({"INFO"}, "已导出 %d 个对象的资源清单（%d 条提示）：%s" %
                    (len(records), warning_count, filepath))
        return {"FINISHED"}


class RH_OT_scan_missing_sources(bpy.types.Operator):
    bl_idname = "rh_studio.scan_missing_sources"
    bl_label = "扫描缺失资源并预览候选"
    bl_description = "Find same-name source files under a chosen folder and write a candidate report without changing assets"
    bl_options = {"REGISTER"}

    directory: StringProperty(name="搜索目录", subtype="DIR_PATH")
    filepath: StringProperty(name="候选报告", subtype="FILE_PATH", default="//logs/missing_source_candidates.json")
    filter_glob: StringProperty(default="*.obj;*.fbx;*.glb;*.gltf;*.stl;*.ply", options={"HIDDEN"})

    def invoke(self, context, event):
        root = bpy.path.abspath(context.scene.rh_studio_project_root or "//")
        self.directory = root if os.path.isdir(root) else bpy.path.abspath("//")
        self.filepath = os.path.join(root, "logs", "missing_source_candidates.json") if os.path.isdir(root) else bpy.path.abspath("//missing_source_candidates.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        search_root = os.path.abspath(bpy.path.abspath(self.directory))
        if not os.path.isdir(search_root):
            self.report({"ERROR"}, "搜索目录不存在。")
            return {"CANCELLED"}

        history_by_batch = {}
        project_root = os.path.abspath(bpy.path.abspath(context.scene.rh_studio_project_root or "//"))
        manifest_path = os.path.join(project_root, "realhuman_project.json")
        manifest_warning = None
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as stream:
                    manifest = json.load(stream)
                if not isinstance(manifest, dict) or not isinstance(manifest.get("asset_sources", []), list):
                    raise ValueError("项目清单结构不正确")
                history_by_batch = {
                    str(entry.get("batch_id", "")): entry
                    for entry in manifest.get("asset_sources", [])
                    if isinstance(entry, dict) and entry.get("batch_id")
                }
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                manifest_warning = "项目导入历史读取失败：" + str(exc)
        else:
            manifest_warning = "未找到 realhuman_project.json；候选匹配无法使用历史文件大小校验"

        index = {}
        scan_errors = []
        for current_root, dirs, files in os.walk(search_root):
            dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__", ".svn"})
            for filename in files:
                extension = Path(filename).suffix.lower()
                if extension not in SUPPORTED_IMPORTS:
                    continue
                full_path = os.path.normpath(os.path.abspath(os.path.join(current_root, filename)))
                try:
                    stat = os.stat(full_path)
                except OSError as exc:
                    scan_errors.append({"path": full_path, "error": str(exc)})
                    continue
                key = (filename.casefold(), extension)
                index.setdefault(key, []).append({
                    "path": full_path, "size_bytes": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                })

        missing_objects = []
        for obj in list(bpy.data.objects):
            old_path = str(obj.get("rh_studio_source_path", ""))
            if not old_path:
                continue
            resolved_old = os.path.abspath(bpy.path.abspath(old_path))
            if os.path.isfile(resolved_old):
                continue
            filename = os.path.basename(old_path)
            extension = Path(filename).suffix.lower()
            candidates = index.get((filename.casefold(), extension), [])
            batch_id = str(obj.get("rh_studio_import_batch_id", ""))
            history = history_by_batch.get(batch_id, {})
            expected_size = history.get("source_size_bytes")
            if expected_size is None:
                matching_sizes = []
                for entry in history_by_batch.values():
                    if os.path.normcase(os.path.abspath(str(entry.get("source_path", "")))) == os.path.normcase(resolved_old):
                        if isinstance(entry.get("source_size_bytes"), int):
                            matching_sizes.append(entry["source_size_bytes"])
                expected_size = matching_sizes[0] if matching_sizes else None
            ranked = [
                dict(candidate, size_match=(
                    isinstance(expected_size, int) and candidate["size_bytes"] == expected_size
                ))
                for candidate in candidates
            ]
            ranked.sort(key=lambda candidate: (
                not candidate["size_match"], candidate["path"].casefold()
            ))
            exact = [candidate for candidate in ranked if candidate["size_match"]]
            status = "unique_exact_size_match" if len(exact) == 1 else (
                "ambiguous_exact_size_matches" if len(exact) > 1 else (
                    "filename_match_needs_review" if ranked else "no_candidate"
                )
            )
            missing_objects.append({
                "object_name": obj.name, "object_type": obj.type,
                "category": str(obj.get("rh_studio_category", "")),
                "batch_id": batch_id, "missing_source_path": old_path,
                "filename": filename, "extension": extension,
                "expected_size_bytes": expected_size,
                "candidate_status": status, "candidate_count": len(ranked),
                "candidates": ranked[:20],
                "warning": "候选仅供人工核对；本次扫描不会修改对象或项目清单"
            })

        report = {
            "schema": "realhuman_studio_missing_source_candidates_v1",
            "search_root": search_root,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": {
                "missing_source_objects": len(missing_objects),
                "unique_exact_size_matches": sum(1 for item in missing_objects if item["candidate_status"] == "unique_exact_size_match"),
                "ambiguous_exact_size_matches": sum(1 for item in missing_objects if item["candidate_status"] == "ambiguous_exact_size_matches"),
                "filename_matches_needing_review": sum(1 for item in missing_objects if item["candidate_status"] == "filename_match_needs_review"),
                "no_candidates": sum(1 for item in missing_objects if item["candidate_status"] == "no_candidate"),
                "scan_errors": len(scan_errors),
            },
            "manifest_warning": manifest_warning,
            "objects": missing_objects,
            "scan_errors": scan_errors[:200],
            "safety_note": "This is a preview only. Same filename is not proof of identical content; even size-matched candidates require user verification before relinking."
        }
        report_path = os.path.abspath(bpy.path.abspath(self.filepath))
        temp_path = report_path + "." + uuid.uuid4().hex + ".tmp"
        try:
            os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temp_path, report_path)
        except (OSError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, "候选报告写入失败：" + str(exc))
            return {"CANCELLED"}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        self.report({"INFO"}, "扫描完成：%d 个缺失路径，%d 个唯一同名且大小匹配候选。未修改任何资源。报告：%s" % (
            len(missing_objects), report["summary"]["unique_exact_size_matches"], report_path))
        return {"FINISHED"}


class RH_OT_apply_missing_source_repairs(bpy.types.Operator):
    bl_idname = "rh_studio.apply_missing_source_repairs"
    bl_label = "应用安全候选修复"
    bl_description = "Apply only unique same-name, same-extension, exact-size matches after a confirmation dialog"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(name="候选报告", subtype="FILE_PATH", default="//logs/missing_source_candidates.json")

    def invoke(self, context, event):
        root = os.path.abspath(bpy.path.abspath(context.scene.rh_studio_project_root or "//"))
        self.filepath = os.path.join(root, "logs", "missing_source_candidates.json")
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "filepath")
        layout.label(text="只处理唯一同名、扩展名一致且文件大小精确匹配的候选。", icon="INFO")
        layout.label(text="以下是候选报告预览；执行时仍会重新核验对象、文件和项目历史。")
        layout.label(text="有歧义或批次不一致的记录会跳过，不会强行修复。")
        try:
            report_path = os.path.abspath(bpy.path.abspath(self.filepath))
            with open(report_path, "r", encoding="utf-8") as stream:
                preview = json.load(stream)
            records = preview.get("objects", []) if isinstance(preview, dict) else []
            if not isinstance(records, list):
                raise ValueError("objects 不是数组")
            counts = {}
            for record in records:
                status = str(record.get("candidate_status", "invalid_record")) if isinstance(record, dict) else "invalid_record"
                counts[status] = counts.get(status, 0) + 1
            box = layout.box()
            box.label(text="报告统计：%d 条记录" % len(records), icon="PREVIEW_RANGE")
            box.label(text="可进一步核验：%d    歧义：%d    需人工复核：%d    无候选：%d" % (
                counts.get("unique_exact_size_match", 0),
                counts.get("ambiguous_exact_size_matches", 0),
                counts.get("filename_match_needs_review", 0),
                counts.get("no_candidate", 0)))
            if records:
                listing = box.column(align=True)
                listing.label(text="对象 / 状态 / 候选")
                for record in records[:12]:
                    if not isinstance(record, dict):
                        listing.label(text="无效记录（将跳过）", icon="ERROR")
                        continue
                    name = str(record.get("object_name", "(未知对象)"))
                    status = str(record.get("candidate_status", "invalid_record"))
                    candidates = record.get("candidates", [])
                    candidate_path = ""
                    if isinstance(candidates, list) and len(candidates) == 1 and isinstance(candidates[0], dict):
                        candidate_path = str(candidates[0].get("path", ""))
                    label = "%s | %s" % (name[:28], status)
                    if candidate_path:
                        label += " | " + os.path.basename(candidate_path)[:24]
                    listing.label(text=label, icon="CHECKMARK" if status == "unique_exact_size_match" else "INFO")
                if len(records) > 12:
                    listing.label(text="另有 %d 条记录，完整列表见 JSON 报告。" % (len(records) - 12))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            layout.label(text="暂时无法预览报告：" + str(exc)[:100], icon="ERROR")

    def execute(self, context):
        report_path = os.path.abspath(bpy.path.abspath(self.filepath))
        try:
            with open(report_path, "r", encoding="utf-8") as stream:
                report = json.load(stream)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.report({"ERROR"}, "无法读取候选报告，未修改任何数据：" + str(exc))
            return {"CANCELLED"}
        if not isinstance(report, dict) or report.get("schema") != "realhuman_studio_missing_source_candidates_v1" or not isinstance(report.get("objects"), list):
            self.report({"ERROR"}, "候选报告格式或版本不受支持，未修改任何数据。")
            return {"CANCELLED"}

        project_root = os.path.abspath(bpy.path.abspath(context.scene.rh_studio_project_root or "//"))
        manifest_path = os.path.join(project_root, "realhuman_project.json")
        results_path = os.path.join(project_root, "logs", "missing_source_repair_results.json")
        try:
            os.makedirs(os.path.dirname(results_path), exist_ok=True)
        except OSError as exc:
            self.report({"ERROR"}, "无法创建修复结果目录，未修改任何数据：" + str(exc))
            return {"CANCELLED"}

        results = []
        grouped = {}
        blocked_batches = set()

        def add_result(source, status, reason, candidate_path="", actual_size=None):
            source = source if isinstance(source, dict) else {}
            results.append({
                "object_name": str(source.get("object_name", "")),
                "batch_id": str(source.get("batch_id", "")),
                "old_source_path": str(source.get("missing_source_path", "")),
                "candidate_path": candidate_path or "",
                "candidate_status": str(source.get("candidate_status", "invalid_record")),
                "status": status,
                "reason": reason,
                "expected_size_bytes": source.get("expected_size_bytes"),
                "actual_size_bytes": actual_size,
            })
            return results[-1]

        def write_results():
            payload = {
                "schema": "realhuman_studio_missing_source_repair_results_v1",
                "application": "RealHuman Studio",
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "candidate_report": report_path,
                "manifest_path": manifest_path,
                "summary": {
                    "total": len(results),
                    "repaired": sum(item["status"] == "repaired" for item in results),
                    "skipped": sum(item["status"] == "skipped" for item in results),
                    "failed": sum(item["status"] == "failed" for item in results),
                },
                "results": results,
            }
            temp_result_path = results_path + "." + uuid.uuid4().hex + ".tmp"
            try:
                with open(temp_result_path, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.write("\n")
                os.replace(temp_result_path, results_path)
                return True
            except (OSError, TypeError, ValueError) as exc:
                self.report({"WARNING"}, "修复结果报告写入失败：" + str(exc))
                return False
            finally:
                if os.path.exists(temp_result_path):
                    os.remove(temp_result_path)

        if not os.path.isfile(manifest_path):
            for source in report["objects"]:
                add_result(source, "skipped", "project_manifest_missing")
            write_results()
            self.report({"ERROR"}, "缺少 realhuman_project.json；无法校验导入批次，未修改任何数据。")
            return {"CANCELLED"}
        try:
            with open(manifest_path, "r", encoding="utf-8") as stream:
                manifest = json.load(stream)
            if not isinstance(manifest, dict) or not isinstance(manifest.get("asset_sources"), list):
                raise ValueError("asset_sources 必须是 JSON 数组")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            for source in report["objects"]:
                add_result(source, "failed", "project_manifest_invalid")
            write_results()
            self.report({"ERROR"}, "项目清单无效，未修改任何数据：" + str(exc))
            return {"CANCELLED"}

        entries = manifest["asset_sources"]
        for source in report["objects"]:
            if not isinstance(source, dict):
                add_result(source, "skipped", "invalid_record")
                continue
            if source.get("candidate_status") != "unique_exact_size_match":
                add_result(source, "skipped", "candidate_status_not_repairable")
                if source.get("batch_id"):
                    blocked_batches.add(str(source.get("batch_id")))
                continue
            batch_id = str(source.get("batch_id", ""))
            object_name = str(source.get("object_name", ""))
            old_path = str(source.get("missing_source_path", ""))
            filename = str(source.get("filename", ""))
            extension = str(source.get("extension", "")).lower()
            expected_size = source.get("expected_size_bytes")
            candidates = source.get("candidates", [])
            exact_candidates = [item for item in candidates if isinstance(item, dict) and item.get("size_match") is True] if isinstance(candidates, list) else []
            if (not batch_id or not object_name or not old_path or not filename
                    or not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size < 0
                    or len(exact_candidates) != 1):
                add_result(source, "skipped", "record_fields_or_candidate_invalid")
                if batch_id:
                    blocked_batches.add(batch_id)
                continue
            candidate = exact_candidates[0]
            target = os.path.normpath(os.path.abspath(str(candidate.get("path", ""))))
            old_abs = os.path.normpath(os.path.abspath(bpy.path.abspath(old_path)))
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                add_result(source, "skipped", "object_not_found", target)
                blocked_batches.add(batch_id)
                continue
            if str(obj.get("rh_studio_import_batch_id", "")) != batch_id:
                add_result(source, "skipped", "object_batch_id_mismatch", target)
                blocked_batches.add(batch_id)
                continue
            current_source = str(obj.get("rh_studio_source_path", ""))
            current_abs = os.path.normpath(os.path.abspath(bpy.path.abspath(current_source))) if current_source else ""
            if current_abs != old_abs:
                add_result(source, "skipped", "object_source_path_changed_since_scan", target)
                blocked_batches.add(batch_id)
                continue
            if os.path.isfile(current_abs):
                add_result(source, "skipped", "original_source_is_no_longer_missing", target)
                blocked_batches.add(batch_id)
                continue
            if (os.path.basename(target).casefold() != filename.casefold()
                    or Path(target).suffix.lower() != extension
                    or Path(filename).suffix.lower() != extension):
                add_result(source, "skipped", "candidate_filename_or_extension_mismatch", target)
                blocked_batches.add(batch_id)
                continue
            if not os.path.isfile(target):
                add_result(source, "skipped", "candidate_file_missing", target)
                blocked_batches.add(batch_id)
                continue
            try:
                target_size = os.path.getsize(target)
            except OSError:
                add_result(source, "skipped", "candidate_file_stat_failed", target)
                blocked_batches.add(batch_id)
                continue
            if target_size != expected_size or candidate.get("size_bytes") != expected_size or candidate.get("size_match") is not True:
                add_result(source, "skipped", "candidate_size_changed_or_mismatched", target, target_size)
                blocked_batches.add(batch_id)
                continue
            grouped.setdefault(batch_id, []).append({
                "source": source, "object": obj, "old_path": current_source,
                "old_abs": old_abs, "target": target, "expected_size": expected_size,
                "result": results[-1] if results else None,
            })
            # This source is pending validation; its final status is assigned below.
            results.append({
                "object_name": object_name, "batch_id": batch_id,
                "old_source_path": old_path, "candidate_path": target,
                "candidate_status": str(source.get("candidate_status", "")),
                "status": "pending", "reason": "awaiting_batch_history_validation",
                "expected_size_bytes": expected_size, "actual_size_bytes": target_size,
            })
            grouped[batch_id][-1]["result"] = results[-1]

        batch_entry_by_id = {}
        approved = []
        for batch_id, records in grouped.items():
            if batch_id in blocked_batches:
                for item in records:
                    item["result"].update(status="skipped", reason="another_record_in_batch_was_rejected")
                continue
            matching = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("batch_id", "")) == batch_id]
            targets = {record["target"] for record in records}
            old_paths = {os.path.normcase(record["old_abs"]) for record in records}
            sizes = {record["expected_size"] for record in records}
            names = {record["object"].name for record in records}
            if len(matching) != 1:
                for item in records:
                    item["result"].update(status="skipped", reason="project_history_batch_not_unique")
                continue
            if len(targets) != 1 or len(old_paths) != 1 or len(sizes) != 1:
                for item in records:
                    item["result"].update(status="skipped", reason="batch_records_disagree_on_paths_or_size")
                continue
            entry = matching[0]
            entry_source = str(entry.get("source_path", ""))
            entry_abs = os.path.normpath(os.path.abspath(entry_source)) if entry_source else ""
            if (os.path.normcase(entry_abs) not in old_paths
                    or entry.get("source_size_bytes") != next(iter(sizes))
                    or not isinstance(entry.get("objects"), list)):
                for item in records:
                    item["result"].update(status="skipped", reason="project_history_source_or_size_mismatch")
                continue
            history_names = {item.get("name") for item in entry["objects"] if isinstance(item, dict)}
            if not names.issubset(history_names):
                for item in records:
                    item["result"].update(status="skipped", reason="object_missing_from_project_history")
                continue
            approved.extend(records)
            batch_entry_by_id[batch_id] = entry

        target_to_batches = {}
        for batch_id, records in grouped.items():
            for item in records:
                target_to_batches.setdefault(os.path.normcase(item["target"]), set()).add(batch_id)
        conflicting_targets = {path for path, batches in target_to_batches.items() if len(batches) > 1}
        if conflicting_targets:
            conflicted_batches = set()
            for batch_id, records in grouped.items():
                if any(os.path.normcase(item["target"]) in conflicting_targets for item in records):
                    conflicted_batches.add(batch_id)
                    for item in records:
                        item["result"].update(status="skipped", reason="candidate_claimed_by_multiple_batches")
            approved = [item for item in approved
                        if str(item["object"].get("rh_studio_import_batch_id", "")) not in conflicted_batches]
            for batch_id in conflicted_batches:
                batch_entry_by_id.pop(batch_id, None)

        # Re-stat every approved candidate immediately before preparing the manifest.
        # If a file changed during validation, reject the entire import batch.
        unstable_batches = set()
        for item in approved:
            try:
                final_size = os.path.getsize(item["target"])
            except OSError:
                final_size = None
            if final_size != item["expected_size"]:
                unstable_batches.add(str(item["object"].get("rh_studio_import_batch_id", "")))
                item["result"].update(
                    status="skipped", reason="candidate_changed_before_manifest_commit",
                    actual_size_bytes=final_size)
        if unstable_batches:
            for batch_id in unstable_batches:
                for item in grouped.get(batch_id, []):
                    if item["result"].get("status") == "pending":
                        item["result"].update(
                            status="skipped", reason="another_candidate_in_batch_changed_before_commit")
                batch_entry_by_id.pop(batch_id, None)
            approved = [item for item in approved
                        if str(item["object"].get("rh_studio_import_batch_id", "")) not in unstable_batches]

        if not approved:
            write_results()
            skipped = sum(item["status"] == "skipped" for item in results)
            self.report({"WARNING"}, "没有可安全应用的修复。跳过 %d 条记录；详情已写入 logs/missing_source_repair_results.json。" % skipped)
            return {"CANCELLED"}

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        updates_by_batch = {}
        for item in approved:
            batch_id = str(item["object"].get("rh_studio_import_batch_id", ""))
            updates_by_batch.setdefault(batch_id, item)
        for batch_id, item in updates_by_batch.items():
            entry = batch_entry_by_id[batch_id]
            stat = os.stat(item["target"])
            entry["relinked_from"] = entry.get("source_path", "")
            entry["source_path"] = item["target"]
            entry["source_size_bytes"] = stat.st_size
            entry["source_mtime"] = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
            entry["relinked_at"] = now
            entry["recovery_method"] = "candidate_report_unique_exact_size"

        temp_path = manifest_path + "." + uuid.uuid4().hex + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            os.replace(temp_path, manifest_path)
        except (OSError, TypeError, ValueError) as exc:
            for item in approved:
                item["result"].update(status="failed", reason="manifest_write_failed: " + str(exc))
            write_results()
            self.report({"ERROR"}, "项目清单更新失败，未修改对象路径；详情已尝试写入修复结果报告：" + str(exc))
            return {"CANCELLED"}
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        for item in approved:
            item["object"]["rh_studio_source_path"] = item["target"]
            item["object"]["rh_studio_relinked_at"] = now
            item["result"].update(status="repaired", reason="unique_exact_size_and_project_history_verified")
        report_written = write_results()
        repaired_count = len(approved)
        skipped_count = sum(item["status"] == "skipped" for item in results)
        message = "已修复 %d 个对象、同步 %d 个导入批次；跳过 %d 条。结果报告：%s" % (
            repaired_count, len(updates_by_batch), skipped_count, results_path)
        if not report_written:
            message += "（但结果报告写入失败）"
        self.report({"INFO"}, message)
        return {"FINISHED"}


def load_repair_results_report(filepath):
    """Load and validate a repair-results JSON report, raising a useful exception on errors."""
    with open(filepath, "r", encoding="utf-8") as stream:
        report = json.load(stream)
    if not isinstance(report, dict) or report.get("schema") != "realhuman_studio_missing_source_repair_results_v1":
        raise ValueError("结果报告格式不受支持。")
    if not isinstance(report.get("results"), list):
        raise ValueError("结果列表格式错误。")
    if not isinstance(report.get("summary", {}), dict):
        raise ValueError("统计摘要格式错误。")
    return report


def filter_repair_results(records, filter_status="ALL"):
    """Pure helper shared by the viewer and smoke tests."""
    if not isinstance(records, list):
        return []
    return [
        item for item in records
        if isinstance(item, dict)
        and (filter_status == "ALL" or item.get("status") == filter_status)
    ]


class RH_OT_copy_repair_result_path(bpy.types.Operator):
    bl_idname = "rh_studio.copy_repair_result_path"
    bl_label = "复制资源路径"
    bl_description = "Copy a source or candidate path to the system clipboard"

    path: StringProperty(name="路径", default="")

    def execute(self, context):
        if not self.path:
            self.report({"WARNING"}, "路径为空，无法复制。")
            return {"CANCELLED"}
        context.window_manager.clipboard = self.path
        self.report({"INFO"}, "路径已复制到剪贴板。")
        return {"FINISHED"}


class RH_OT_view_missing_source_repair_results(bpy.types.Operator):
    bl_idname = "rh_studio.view_missing_source_repair_results"
    bl_label = "查看缺失资源修复结果"
    bl_description = "Review per-item repair results and copy source/candidate paths"

    filepath: StringProperty(name="结果报告", subtype="FILE_PATH", default="//logs/missing_source_repair_results.json")
    filter_status: EnumProperty(
        name="筛选状态",
        items=(
            ("ALL", "全部", "显示所有结果"),
            ("repaired", "已修复", "只显示成功修复的记录"),
            ("skipped", "已跳过", "只显示被安全规则跳过的记录"),
            ("failed", "失败", "只显示执行失败的记录"),
        ),
        default="ALL",
    )

    def invoke(self, context, event):
        root = os.path.abspath(bpy.path.abspath(context.scene.rh_studio_project_root or "//"))
        self.filepath = os.path.join(root, "logs", "missing_source_repair_results.json")
        return context.window_manager.invoke_props_dialog(self, width=760)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "filepath")
        layout.prop(self, "filter_status", text="筛选")
        try:
            report = load_repair_results_report(os.path.abspath(bpy.path.abspath(self.filepath)))
            summary = report.get("summary", {})
            row = layout.row(align=True)
            row.label(text="总计：%s" % summary.get("total", 0), icon="PREVIEW_RANGE")
            row.label(text="已修复：%s" % summary.get("repaired", 0), icon="CHECKMARK")
            row.label(text="已跳过：%s" % summary.get("skipped", 0), icon="INFO")
            row.label(text="失败：%s" % summary.get("failed", 0), icon="ERROR")
            records = report.get("results", [])
            filtered = filter_repair_results(records, self.filter_status)
            layout.label(text="当前显示 %d 条记录（最多展示前 30 条）。" % min(len(filtered), 30))
            if not filtered:
                layout.label(text="没有符合筛选条件的记录。", icon="INFO")
                return
            listing = layout.column(align=True)
            for item in filtered[:30]:
                status = item.get("status", "unknown")
                icon = {"repaired": "CHECKMARK", "skipped": "INFO", "failed": "ERROR"}.get(status, "QUESTION")
                box = listing.box()
                header = box.row(align=True)
                header.label(text=str(item.get("object_name") or "(未知对象)")[:48], icon=icon)
                header.label(text=str(status))
                reason = str(item.get("reason") or "未提供原因")
                box.label(text="原因：" + reason[:180])
                old_path = str(item.get("old_source_path") or "")
                candidate_path = str(item.get("candidate_path") or "")
                if old_path:
                    row = box.row(align=True)
                    row.label(text="原路径：" + old_path[:82])
                    copy_old = row.operator("rh_studio.copy_repair_result_path", text="复制原路径", icon="COPYDOWN")
                    copy_old.path = old_path
                if candidate_path:
                    row = box.row(align=True)
                    row.label(text="候选：" + candidate_path[:82])
                    copy_candidate = row.operator("rh_studio.copy_repair_result_path", text="复制候选", icon="COPYDOWN")
                    copy_candidate.path = candidate_path
                sizes = box.row(align=True)
                sizes.label(text="预期大小：%s" % item.get("expected_size_bytes", "未知"))
                sizes.label(text="实际大小：%s" % item.get("actual_size_bytes", "未知"))
            if len(filtered) > 30:
                layout.label(text="还有 %d 条记录未显示，请查看 JSON 完整报告。" % (len(filtered) - 30))
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            layout.label(text="无法读取结果报告：" + str(exc)[:160], icon="ERROR")

    def execute(self, context):
        self.report({"INFO"}, "结果报告查看器已关闭。")
        return {"FINISHED"}


class RH_OT_relink_asset_source(bpy.types.Operator):
    bl_idname = "rh_studio.relink_asset_source"
    bl_label = "重新关联原始资源文件"
    bl_description = "Repair the selected assets' source-file reference and synchronize their import-history batch"
    bl_options = {"REGISTER", "UNDO"}

    filepath: StringProperty(name="原始资源文件", subtype="FILE_PATH")
    filter_glob: StringProperty(
        default="*.obj;*.fbx;*.glb;*.gltf;*.stl;*.ply", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        selected = list(context.selected_objects or [])
        return bool(selected and all(obj.get("rh_studio_source_path") for obj in selected))

    def invoke(self, context, event):
        selected = list(context.selected_objects or [])
        old_path = selected[0].get("rh_studio_source_path", "") if selected else ""
        if old_path:
            old_abs = bpy.path.abspath(old_path)
            parent = os.path.dirname(old_abs)
            if os.path.isdir(parent):
                self.filepath = parent + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        selected = list(context.selected_objects or [])
        if not selected:
            self.report({"ERROR"}, "请先选择需要修复原始路径的资源对象。")
            return {"CANCELLED"}
        if any(not obj.get("rh_studio_source_path") for obj in selected):
            self.report({"ERROR"}, "所选对象中有对象没有原始资源路径；请只选择需要重新关联的已导入资源。")
            return {"CANCELLED"}

        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        if not os.path.isfile(filepath):
            self.report({"ERROR"}, "所选文件不存在或不是普通文件。")
            return {"CANCELLED"}
        extension = Path(filepath).suffix.lower()
        if extension not in SUPPORTED_IMPORTS:
            self.report({"ERROR"}, "格式不支持。请选择 OBJ、FBX、GLB、GLTF、STL 或 PLY 文件。")
            return {"CANCELLED"}

        old_paths = [str(obj.get("rh_studio_source_path", "")) for obj in selected]
        for old_path in old_paths:
            old_extension = Path(old_path).suffix.lower()
            if old_extension and old_extension != extension:
                self.report({"ERROR"}, "新文件扩展名与原始路径不一致；为避免误关联，请选择同格式文件。")
                return {"CANCELLED"}

        batch_ids = {str(obj.get("rh_studio_import_batch_id", "")) for obj in selected}
        nonempty_batch_ids = {batch_id for batch_id in batch_ids if batch_id}
        if len(nonempty_batch_ids) > 1 or (nonempty_batch_ids and "" in batch_ids):
            self.report({"ERROR"}, "所选对象包含多个导入批次或混合批次；请按同一批次分别重新关联。")
            return {"CANCELLED"}
        batch_id = next(iter(nonempty_batch_ids), "")

        scene = context.scene
        project_root = os.path.abspath(bpy.path.abspath(scene.rh_studio_project_root or "//"))
        manifest_path = os.path.join(project_root, "realhuman_project.json")
        manifest = None
        matching_entries = []
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as stream:
                    manifest = json.load(stream)
                if not isinstance(manifest, dict):
                    raise ValueError("项目清单根节点必须是 JSON 对象")
                entries = manifest.setdefault("asset_sources", [])
                if not isinstance(entries, list):
                    raise ValueError("asset_sources 必须是 JSON 数组")
                if batch_id:
                    matching_entries = [
                        entry for entry in entries
                        if isinstance(entry, dict) and str(entry.get("batch_id", "")) == batch_id
                    ]
                    if not matching_entries:
                        self.report({"ERROR"}, "项目清单中找不到所选对象的导入批次；未修改任何数据。")
                        return {"CANCELLED"}
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.report({"ERROR"}, "无法安全更新项目清单，未修改任何数据：" + str(exc))
                return {"CANCELLED"}

        try:
            source_stat = os.stat(filepath)
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            if manifest is not None and matching_entries:
                for entry in matching_entries:
                    previous = entry.get("source_path", "")
                    entry["relinked_from"] = previous
                    entry["source_path"] = filepath
                    entry["source_size_bytes"] = source_stat.st_size
                    entry["source_mtime"] = datetime.fromtimestamp(
                        source_stat.st_mtime).astimezone().isoformat(timespec="seconds")
                    entry["relinked_at"] = now
                temp_path = manifest_path + "." + uuid.uuid4().hex + ".tmp"
                try:
                    with open(temp_path, "w", encoding="utf-8") as stream:
                        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
                        stream.write("\n")
                    os.replace(temp_path, manifest_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
        except (OSError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, "重新关联失败，项目清单未能安全更新：" + str(exc))
            return {"CANCELLED"}

        for obj in selected:
            obj["rh_studio_source_path"] = filepath
            obj["rh_studio_relinked_at"] = now
        if manifest is None:
            self.report({"WARNING"}, "已更新 %d 个对象的原始路径；未找到项目清单，因此导入历史未同步。" % len(selected))
        elif not batch_id:
            self.report({"WARNING"}, "已更新 %d 个对象的原始路径；对象缺少批次 ID，无法可靠匹配导入历史。" % len(selected))
        else:
            self.report({"INFO"}, "已重新关联 %d 个对象，并同步导入批次 %s 的历史记录。注意：此操作只修复路径元数据，不会重新导入或替换网格。" %
                        (len(selected), batch_id[:8]))
        return {"FINISHED"}


class RH_OT_audit_project_assets(bpy.types.Operator):
    bl_idname = "rh_studio.audit_project_assets"
    bl_label = "检查整个项目资源"
    bl_description = "Audit all objects in the current .blend and cross-check project import history"
    bl_options = {"REGISTER"}

    filepath: StringProperty(
        name="项目检查报告", subtype="FILE_PATH",
        default="//logs/project_integrity.json")

    def invoke(self, context, event):
        root = bpy.path.abspath(context.scene.rh_studio_project_root or "//")
        if os.path.isdir(root):
            logs_dir = os.path.join(root, "logs")
            self.filepath = os.path.join(logs_dir, "project_integrity.json")
        else:
            self.filepath = bpy.path.abspath("//project_integrity.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene = context.scene
        objects = list(bpy.data.objects)
        names = {obj.name for obj in objects}
        unit_scale = float(scene.unit_settings.scale_length or 1.0)
        valid_scale = math.isfinite(unit_scale) and unit_scale > 0.0
        records = []
        counts = {
            "objects": len(objects), "missing_source_files": 0,
            "missing_armature_targets": 0, "missing_uvs": 0,
            "missing_materials": 0, "suspicious_dimensions": 0,
            "missing_import_batch_ids": 0,
        }

        for obj in objects:
            warnings = []
            source_path = str(obj.get("rh_studio_source_path", ""))
            if source_path and not os.path.isfile(bpy.path.abspath(source_path)):
                warnings.append("原始资源文件不存在或路径已失效")
                counts["missing_source_files"] += 1
            if obj.get("rh_studio_category") and not obj.get("rh_studio_import_batch_id"):
                warnings.append("有资源分类但缺少导入批次 ID")
                counts["missing_import_batch_ids"] += 1

            dimensions = [float(value) for value in obj.dimensions]
            has_geometry = obj.type in {"MESH", "ARMATURE", "CURVE", "SURFACE", "FONT", "META"}
            if has_geometry and not all(math.isfinite(value) for value in dimensions):
                warnings.append("对象尺寸包含非有限数值")
                counts["suspicious_dimensions"] += 1
            elif has_geometry and valid_scale:
                largest_m = max(dimensions) * unit_scale
                if not math.isfinite(largest_m) or largest_m < 0.005 or largest_m > 20.0:
                    warnings.append("尺寸超出 5 毫米至 20 米的启发式检查范围")
                    counts["suspicious_dimensions"] += 1

            targets = []
            for modifier in obj.modifiers:
                if modifier.type == "ARMATURE":
                    if modifier.object is None:
                        warnings.append("骨架修改器没有绑定目标")
                        counts["missing_armature_targets"] += 1
                    else:
                        targets.append(modifier.object.name)
            if obj.parent and obj.parent.type == "ARMATURE" and obj.parent.name not in targets:
                targets.append(obj.parent.name)

            mesh_data = None
            if obj.type == "MESH":
                uv_count = len(obj.data.uv_layers)
                material_count = sum(1 for slot in obj.material_slots if slot.material)
                mesh_data = {
                    "vertices": len(obj.data.vertices),
                    "polygons": len(obj.data.polygons),
                    "uv_layers": [layer.name for layer in obj.data.uv_layers],
                    "materials": [slot.material.name if slot.material else None
                                  for slot in obj.material_slots],
                    "shape_keys": [key.name for key in obj.data.shape_keys.key_blocks]
                                  if obj.data.shape_keys else [],
                }
                if obj.data.polygons and not uv_count:
                    warnings.append("网格没有 UV 图层")
                    counts["missing_uvs"] += 1
                if obj.data.polygons and not material_count:
                    warnings.append("网格没有已分配材质")
                    counts["missing_materials"] += 1

            records.append({
                "name": obj.name, "type": obj.type,
                "category": obj.get("rh_studio_category", "UNASSIGNED"),
                "source_path": source_path,
                "source_path_exists": bool(source_path and os.path.isfile(
                    bpy.path.abspath(source_path))),
                "import_batch_id": obj.get("rh_studio_import_batch_id", ""),
                "imported_at": obj.get("rh_studio_imported_at", ""),
                "dimensions_world": [
                    value if math.isfinite(value) else None for value in dimensions
                ],
                "dimensions_world_m": [
                    round(value * unit_scale, 6)
                    if valid_scale and math.isfinite(value)
                    and math.isfinite(value * unit_scale) else None
                    for value in dimensions
                ],
                "armature_targets": sorted(set(targets)),
                "mesh": mesh_data, "warnings": warnings,
            })

        project_manifest_path = os.path.join(
            bpy.path.abspath(scene.rh_studio_project_root or "//"),
            "realhuman_project.json")
        history = {"status": "not_found", "batch_count": 0, "warnings": []}
        if os.path.isfile(project_manifest_path):
            try:
                with open(project_manifest_path, "r", encoding="utf-8") as stream:
                    project_manifest = json.load(stream)
                if not isinstance(project_manifest, dict):
                    raise ValueError("项目清单根节点不是 JSON 对象")
                batches = project_manifest.get("asset_sources", [])
                if not isinstance(batches, list):
                    raise ValueError("asset_sources 不是 JSON 数组")
                history = {"status": "ok", "batch_count": len(batches), "warnings": []}
                for batch in batches:
                    if not isinstance(batch, dict):
                        history["warnings"].append("发现格式无效的导入批次记录")
                        continue
                    source = batch.get("source_path", "")
                    if source and not os.path.isfile(source):
                        history["warnings"].append(
                            "导入批次 %s 的源文件不存在：%s" %
                            (batch.get("batch_id", "unknown"), source))
                    recorded_names = [
                        item.get("name") for item in batch.get("objects", [])
                        if isinstance(item, dict) and item.get("name")
                    ]
                    missing_names = [name for name in recorded_names if name not in names]
                    if missing_names:
                        history["warnings"].append(
                            "导入批次 %s 中记录的对象名称当前未找到：%s" %
                            (batch.get("batch_id", "unknown"), ", ".join(missing_names)))
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                history = {"status": "invalid", "batch_count": 0,
                           "warnings": ["无法读取项目清单：" + str(exc)]}
        else:
            history["warnings"].append("未找到 realhuman_project.json；未执行导入历史交叉检查")

        payload = {
            "schema": "realhuman_studio_project_integrity_v1",
            "application": "RealHuman Studio",
            "blender_version": bpy.app.version_string,
            "blend_file": bpy.data.filepath or None,
            "project_root": bpy.path.abspath(scene.rh_studio_project_root or "//"),
            "meters_per_blender_unit": unit_scale if valid_scale else None,
            "project_history": history,
            "summary": counts,
            "object_count": len(records),
            "objects": records,
        }
        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        try:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            temp_path = filepath + ".tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.write("\n")
                os.replace(temp_path, filepath)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except (OSError, TypeError, ValueError) as exc:
            self.report({"ERROR"}, "无法写入项目检查报告：" + str(exc))
            return {"CANCELLED"}

        issue_count = sum(value for key, value in counts.items() if key != "objects")
        issue_count += len(history.get("warnings", []))
        self.report({"INFO"}, "项目检查完成：%d 个对象，%d 项检查提示。报告：%s" %
                    (len(records), issue_count, filepath))
        return {"FINISHED"}


class RH_OT_audit_selected_assets(bpy.types.Operator):
    bl_idname = "rh_studio.audit_selected_assets"
    bl_label = "检查所选资源并生成报告"
    bl_description = "Write a JSON report with mesh statistics, materials, UVs, shape keys, rig links and geometry warnings"
    bl_options = {"REGISTER"}

    filepath: StringProperty(
        name="报告文件", subtype="FILE_PATH",
        default="//rh_studio_asset_audit.json")

    def invoke(self, context, event):
        root = bpy.path.abspath(context.scene.rh_studio_project_root or "//")
        logs_dir = os.path.join(root, "logs") if root else ""
        if logs_dir and os.path.isdir(logs_dir):
            self.filepath = os.path.join(logs_dir, "asset_audit.json")
        else:
            self.filepath = bpy.path.abspath("//rh_studio_asset_audit.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        objects = list(context.selected_objects)
        if not objects:
            self.report({"WARNING"}, "请先选择要检查的对象。")
            return {"CANCELLED"}

        scene = context.scene
        unit_scale = float(scene.unit_settings.scale_length or 1.0)
        valid_unit_scale = math.isfinite(unit_scale) and unit_scale > 0.0
        report_objects = []
        for obj in objects:
            source_path = obj.get("rh_studio_source_path", "")
            dimensions = [float(v) for v in obj.dimensions]
            dimensions_m = (
                [round(value * unit_scale, 6) for value in dimensions]
                if valid_unit_scale and all(math.isfinite(value) for value in dimensions)
                else None
            )
            warnings = []
            record = {
                "name": obj.name,
                "type": obj.type,
                "category": obj.get("rh_studio_category", "UNASSIGNED"),
                "source_path": source_path,
                "source_path_exists": bool(source_path and os.path.isfile(source_path)),
                "import_batch_id": obj.get("rh_studio_import_batch_id", ""),
                "imported_at": obj.get("rh_studio_imported_at", ""),
                "dimensions_world": [round(value, 6) for value in dimensions],
                "dimensions_world_m": dimensions_m,
                "meters_per_blender_unit": unit_scale if valid_unit_scale else None,
                "world_bounds": None,
                "warnings": warnings,
            }
            if source_path and not os.path.isfile(source_path):
                warnings.append("原始资源文件不存在或路径已失效。")
            if any(not math.isfinite(value) for value in dimensions):
                warnings.append("对象尺寸包含非有限数值。")
            elif any(value <= 1e-6 for value in dimensions):
                warnings.append("对象至少有一个近零尺寸轴；请检查网格或对象变换。")
            if valid_unit_scale and dimensions_m:
                largest_dimension_m = max(dimensions_m)
                if largest_dimension_m > 20.0 or largest_dimension_m < 0.005:
                    warnings.append(
                        "包围尺寸超出 5 毫米至 20 米的常规检查范围；"
                        "请确认源文件单位与资源用途（启发式提示，不代表模型必然错误）。")
            if not valid_unit_scale:
                warnings.append("场景单位比例无效，无法可靠计算米制尺寸。")
            if obj.bound_box:
                corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                record["world_bounds"] = {
                    "min": [round(min(p[i] for p in corners), 6) for i in range(3)],
                    "max": [round(max(p[i] for p in corners), 6) for i in range(3)],
                }

            if obj.type == "MESH":
                mesh = obj.data
                uv_names = [layer.name for layer in mesh.uv_layers]
                material_names = [
                    slot.material.name if slot.material else None
                    for slot in obj.material_slots
                ]
                shape_keys = (
                    [key.name for key in mesh.shape_keys.key_blocks]
                    if mesh.shape_keys else []
                )
                armature_targets = [
                    modifier.object.name for modifier in obj.modifiers
                    if modifier.type == "ARMATURE" and modifier.object
                ]
                if any(modifier.type == "ARMATURE" and modifier.object is None
                       for modifier in obj.modifiers):
                    warnings.append("存在没有目标骨架的骨架修改器。")
                bm = bmesh.new()
                try:
                    bm.from_mesh(mesh)
                    non_manifold_edges = sum(1 for edge in bm.edges if not edge.is_manifold)
                    loose_vertices = sum(1 for vertex in bm.verts if not vertex.link_edges)
                    loose_edges = sum(1 for edge in bm.edges if not edge.link_faces)
                finally:
                    bm.free()
                record["mesh"] = {
                    "vertices": len(mesh.vertices),
                    "edges": len(mesh.edges),
                    "polygons": len(mesh.polygons),
                    "uv_layers": uv_names,
                    "materials": material_names,
                    "shape_keys": shape_keys,
                    "armature_targets": armature_targets,
                    "non_manifold_edges": non_manifold_edges,
                    "loose_vertices": loose_vertices,
                    "loose_edges": loose_edges,
                }
                if mesh.polygons and not uv_names:
                    record["warnings"].append("网格没有 UV 图层；UV 印花和纹理工作流可能不可用。")
                if mesh.polygons and not any(material_names):
                    record["warnings"].append("网格没有已分配材质。")
                if not mesh.vertices:
                    record["warnings"].append("网格没有顶点。")
                if non_manifold_edges:
                    record["warnings"].append(
                        "存在 %d 条非流形边；开口服装边缘可能是有意设计，请结合用途检查。" %
                        non_manifold_edges
                    )
            elif obj.type == "ARMATURE":
                record["armature"] = {
                    "bones": len(obj.data.bones),
                    "pose_bones": len(obj.pose.bones) if obj.pose else 0,
                    "action": (
                        obj.animation_data.action.name
                        if obj.animation_data and obj.animation_data.action else None
                    ),
                }
            report_objects.append(record)

        payload = {
            "schema": "realhuman_studio_asset_audit_v1",
            "blender_version": bpy.app.version_string,
            "blend_file": bpy.data.filepath or None,
            "object_count": len(report_objects),
            "objects": report_objects,
        }
        path = os.path.abspath(bpy.path.abspath(self.filepath))
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, "无法写入资源检查报告：" + str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "已检查 %d 个对象并写入报告：%s" % (len(report_objects), path))
        return {"FINISHED"}


class RH_OT_diagnose_asset_scale(bpy.types.Operator):
    bl_idname = "rh_studio.diagnose_asset_scale"
    bl_label = "诊断资源尺寸与单位"
    bl_description = "Measure selected objects in world space and report plausible unit interpretations without changing the scene"
    bl_options = {"REGISTER"}

    filepath: StringProperty(
        name="尺寸诊断报告", subtype="FILE_PATH",
        default="//rh_studio_scale_diagnosis.json")

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def invoke(self, context, event):
        self.filepath = bpy.path.abspath("//rh_studio_scale_diagnosis.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        objects = list(context.selected_objects)
        points = []
        object_records = []
        for obj in objects:
            corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            points.extend(corners)
            object_records.append({
                "name": obj.name,
                "type": obj.type,
                "dimensions_world": [round(float(v), 6) for v in obj.dimensions],
                "scale": [round(float(v), 6) for v in obj.scale],
            })
        if not points:
            self.report({"ERROR"}, "所选对象没有有效边界框。")
            return {"CANCELLED"}

        minimum = [min(float(p[i]) for p in points) for i in range(3)]
        maximum = [max(float(p[i]) for p in points) for i in range(3)]
        dimensions = [maximum[i] - minimum[i] for i in range(3)]
        height = dimensions[2]
        scene = context.scene
        unit_scale = float(scene.unit_settings.scale_length) if scene.unit_settings else 1.0
        # These are hypotheses only. Blender object coordinates have no guaranteed real-world unit.
        candidates = []
        for label, factor in (("按米解释", 1.0), ("按厘米解释", 0.01), ("按毫米解释", 0.001)):
            estimated_m = height * factor * unit_scale
            plausible = 1.35 <= estimated_m <= 2.25
            candidates.append({
                "interpretation": label,
                "meters_per_coordinate_unit": factor,
                "estimated_height_m": round(estimated_m, 6),
                "plausible_adult_human_height": plausible,
            })
        payload = {
            "schema": "realhuman_studio_scale_diagnosis_v1",
            "warning": "Unit interpretations are heuristic only; no scale or object transform was changed.",
            "object_count": len(objects),
            "scene_unit_system": scene.unit_settings.system,
            "scene_unit_scale": unit_scale,
            "world_bounds": {
                "min": [round(v, 6) for v in minimum],
                "max": [round(v, 6) for v in maximum],
                "dimensions": [round(v, 6) for v in dimensions],
            },
            "unit_hypotheses": candidates,
            "objects": object_records,
        }
        path = bpy.path.abspath(self.filepath)
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
        except (OSError, ValueError, TypeError) as exc:
            self.report({"ERROR"}, "无法写入尺寸诊断报告：" + str(exc))
            return {"CANCELLED"}

        plausible_labels = [item["interpretation"] for item in candidates
                            if item["plausible_adult_human_height"]]
        hint = "；可能的人体尺寸解释：" + "、".join(plausible_labels) if plausible_labels else "；未发现明显符合成人身高的常见单位解释"
        self.report({"INFO"}, "所选组世界尺寸 %.4f × %.4f × %.4f（场景单位）；报告已保存%s" %
                    (dimensions[0], dimensions[1], dimensions[2], hint))
        return {"FINISHED"}


class RH_OT_normalize_selected_assets(bpy.types.Operator):
    bl_idname = "rh_studio.normalize_selected_assets"
    bl_label = "规范化所选资源位置"
    bl_description = "Center the selected asset group on X/Y and/or place its lowest point on Z=0 without changing mesh data"
    bl_options = {"REGISTER", "UNDO"}

    center_xy: BoolProperty(name="水平居中到原点", default=True)
    floor_to_zero: BoolProperty(name="底部对齐地面", default=True)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objects = list(context.selected_objects)
        points = []
        for obj in objects:
            try:
                corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            except (AttributeError, TypeError, ValueError):
                corners = []
            points.extend(corners)

        if not points:
            self.report({"ERROR"}, "所选对象没有可用于定位的边界框。")
            return {"CANCELLED"}

        min_xyz = [min(point[i] for point in points) for i in range(3)]
        max_xyz = [max(point[i] for point in points) for i in range(3)]
        delta = Vector((
            -(min_xyz[0] + max_xyz[0]) * 0.5 if self.center_xy else 0.0,
            -(min_xyz[1] + max_xyz[1]) * 0.5 if self.center_xy else 0.0,
            -min_xyz[2] if self.floor_to_zero else 0.0,
        ))
        if delta.length_squared > 1e-16:
            # Translate in world space while preserving mesh data and relative spacing.
            for obj in objects:
                world_matrix = obj.matrix_world.copy()
                world_matrix.translation += delta
                obj.matrix_world = world_matrix

        for obj in objects:
            obj["rh_studio_position_normalized"] = True
            obj["rh_studio_normalization_offset"] = [round(float(v), 6) for v in delta]
        context.view_layer.update()
        self.report(
            {"INFO"},
            "已规范化 %d 个对象的位置（偏移 %.4f, %.4f, %.4f）；未改动网格数据或物体缩放。" %
            (len(objects), delta.x, delta.y, delta.z)
        )
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
        scene = context.scene
        unit_settings = scene.unit_settings
        # Blender dimensions are expressed in Blender units; scale_length converts
        # one Blender unit to meters. The UI target is explicitly specified in meters.
        meters_per_blender_unit = float(unit_settings.scale_length) if unit_settings else 1.0
        if not math.isfinite(meters_per_blender_unit) or meters_per_blender_unit <= 0.0:
            self.report({"ERROR"}, "场景单位比例无效，无法安全校准。")
            return {"CANCELLED"}
        current_height = float(obj.dimensions.z)
        if not math.isfinite(current_height) or current_height <= 1e-8:
            self.report({"ERROR"}, "当前对象高度为零或无效，无法校准。")
            return {"CANCELLED"}
        target_height_bu = float(self.target_height) / meters_per_blender_unit
        factor = target_height_bu / current_height
        if not math.isfinite(factor) or factor <= 0.0:
            self.report({"ERROR"}, "计算出的缩放比例无效，未修改模型。")
            return {"CANCELLED"}

        # Uniformly scale only the active mesh object. Translate via matrix_world
        # rather than obj.location so parented meshes are moved along world Z.
        obj.scale = tuple(component * factor for component in obj.scale)
        context.view_layer.update()
        world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        if world_corners:
            world_matrix = obj.matrix_world.copy()
            world_matrix.translation.z -= min(point.z for point in world_corners)
            obj.matrix_world = world_matrix
        context.view_layer.update()
        actual_height_m = float(obj.dimensions.z) * meters_per_blender_unit
        self.report(
            {"INFO"},
            "当前网格已校准至约 %.3f 米并落地；仅修改活动网格，不会同步缩放骨架或衣物。" % actual_height_m
        )
        return {"FINISHED"}

class RH_OT_fit_selected_group_height(bpy.types.Operator):
    bl_idname = "rh_studio.fit_selected_group_height"
    bl_label = "校准所选资源组身高"
    bl_description = "Uniformly scale all selected objects as one world-space group and place the group's bottom at Z=0"
    bl_options = {"REGISTER", "UNDO"}

    target_height: FloatProperty(name="目标身高（米）", default=1.75, min=0.1, max=3.0)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        objects = list(context.selected_objects)
        selected_pointers = {obj.as_pointer() for obj in objects}
        # Refuse partial scaling when a selected mesh is bound to an armature
        # outside the selection. Silently scaling only one side of this pair
        # is a common way to break a character after import.
        missing_armatures = []
        for obj in objects:
            if obj.type != "MESH":
                continue
            for modifier in obj.modifiers:
                target = modifier.object if modifier.type == "ARMATURE" else None
                if target is not None and target.as_pointer() not in selected_pointers:
                    missing_armatures.append((obj.name, target.name))
            if obj.parent is not None and obj.parent.type == "ARMATURE" and obj.parent.as_pointer() not in selected_pointers:
                missing_armatures.append((obj.name, obj.parent.name))
        if missing_armatures:
            details = ", ".join("%s → %s" % pair for pair in missing_armatures[:3])
            self.report(
                {"ERROR"},
                "检测到未选中的绑定骨架，已取消以避免角色变形：%s。请同时选择网格和对应骨架。" % details
            )
            return {"CANCELLED"}

        scene = context.scene
        unit_settings = scene.unit_settings
        meters_per_blender_unit = float(unit_settings.scale_length) if unit_settings else 1.0
        if not math.isfinite(meters_per_blender_unit) or meters_per_blender_unit <= 0.0:
            self.report({"ERROR"}, "场景单位比例无效，未修改所选资源。")
            return {"CANCELLED"}

        corners = []
        original_matrices = {}
        for obj in objects:
            try:
                object_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            except (AttributeError, TypeError, ValueError):
                object_corners = []
            if object_corners:
                corners.extend(object_corners)
                original_matrices[obj.name] = obj.matrix_world.copy()
        if not corners:
            self.report({"ERROR"}, "所选对象没有有效边界框，未修改资源。")
            return {"CANCELLED"}

        minimum = Vector((
            min(point.x for point in corners),
            min(point.y for point in corners),
            min(point.z for point in corners),
        ))
        maximum = Vector((
            max(point.x for point in corners),
            max(point.y for point in corners),
            max(point.z for point in corners),
        ))
        current_height = maximum.z - minimum.z
        if not math.isfinite(current_height) or current_height <= 1e-8:
            self.report({"ERROR"}, "所选资源组高度为零或无效，未修改资源。")
            return {"CANCELLED"}

        target_height_bu = float(self.target_height) / meters_per_blender_unit
        factor = target_height_bu / current_height
        if not math.isfinite(factor) or factor <= 0.0:
            self.report({"ERROR"}, "计算出的缩放比例无效，未修改资源。")
            return {"CANCELLED"}

        # Move the group's horizontal center and bottom to the world origin,
        # then apply a uniform scale. This guarantees the final lower Z is zero.
        # Apply parent objects before selected descendants so their final world
        # matrices remain consistent with the same group transform.
        pivot = Vector(((minimum.x + maximum.x) * 0.5,
                        (minimum.y + maximum.y) * 0.5, minimum.z))
        scale = Matrix.Diagonal((factor, factor, factor, 1.0))
        transform = scale @ Matrix.Translation(-pivot)

        def parent_depth(obj):
            depth, parent = 0, obj.parent
            while parent is not None:
                depth += 1
                parent = parent.parent
            return depth

        for obj in sorted(objects, key=parent_depth):
            original = original_matrices.get(obj.name)
            if original is not None:
                obj.matrix_world = transform @ original
        context.view_layer.update()

        final_corners = [
            obj.matrix_world @ Vector(corner)
            for obj in objects for corner in obj.bound_box
        ]
        final_height_m = (
            max(point.z for point in final_corners) -
            min(point.z for point in final_corners)
        ) * meters_per_blender_unit
        final_bottom_m = min(point.z for point in final_corners) * meters_per_blender_unit
        self.report(
            {"INFO"},
            "已校准所选 %d 个对象组成的资源组：高度 %.3f 米，底部 Z=%.4f 米。请确认骨架、身体网格和衣物均已选中。" %
            (len(objects), final_height_m, final_bottom_m)
        )
        return {"FINISHED"}


class RH_OT_generate_body_proportion_keys(bpy.types.Operator):
    bl_idname = "rh_studio.generate_body_proportion_keys"
    bl_label = "生成 / 更新体型控制"
    bl_description = "Create reusable shape keys for broad shoulder, chest, waist and hip proportions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and len(obj.data.vertices) >= 4)

    def execute(self, context):
        obj = context.active_object
        # This first-stage proportion tool assumes an upright, single full-body
        # mesh in local Z-up coordinates. Validate geometry before adding Basis:
        # a rejected mesh must not be modified as a side effect.
        shape_keys = obj.data.shape_keys
        basis = shape_keys.key_blocks[0] if shape_keys else None
        if basis is None:
            base_coords = [vertex.co.copy() for vertex in obj.data.vertices]
        else:
            base_coords = [basis.data[i].co.copy()
                           for i in range(len(obj.data.vertices))]
        if not base_coords:
            self.report({"ERROR"}, "当前网格没有顶点。")
            return {"CANCELLED"}

        min_x = min(co.x for co in base_coords)
        max_x = max(co.x for co in base_coords)
        min_y = min(co.y for co in base_coords)
        max_y = max(co.y for co in base_coords)
        min_z = min(co.z for co in base_coords)
        max_z = max(co.z for co in base_coords)
        height = max_z - min_z
        if height < 1e-6 or max_x - min_x < 1e-6:
            self.report({"ERROR"}, "网格尺寸异常，无法生成体型控制。")
            return {"CANCELLED"}

        # Only create Basis after all geometry preconditions have passed.
        if basis is None:
            basis = obj.shape_key_add(name="Basis", from_mix=False)
            base_coords = [basis.data[i].co.copy()
                           for i in range(len(obj.data.vertices))]

        center_x = (min_x + max_x) * 0.5
        center_y = (min_y + max_y) * 0.5
        # name, label, vertical center, vertical falloff, X width, Y depth
        specs = (
            ("RH体型 | 肩宽", "肩宽", 0.79, 0.075, 0.16, 0.06),
            ("RH体型 | 胸围", "胸围", 0.66, 0.085, 0.12, 0.14),
            ("RH体型 | 腰围", "腰围", 0.52, 0.070, 0.18, 0.16),
            ("RH体型 | 臀宽", "臀宽", 0.42, 0.075, 0.16, 0.10),
        )
        blocks = obj.data.shape_keys.key_blocks
        created = 0
        updated = 0
        for key_name, label, center_ratio, sigma_ratio, x_amount, y_amount in specs:
            key = blocks.get(key_name)
            if key is None:
                key = obj.shape_key_add(name=key_name, from_mix=False)
                created += 1
            else:
                updated += 1
            key.relative_key = basis
            key.slider_min = -1.0
            key.slider_max = 1.0
            center_z = min_z + center_ratio * height
            sigma = max(height * sigma_ratio, 1e-6)

            # Optional artist-authored vertex-group masks refine the broad
            # vertical falloff without changing the default workflow.
            mask_group = obj.vertex_groups.get("RH遮罩 | " + label)
            mask_index = mask_group.index if mask_group is not None else None
            mask_weights = None
            if mask_index is not None:
                mask_weights = []
                for vertex in obj.data.vertices:
                    mask_weight = 0.0
                    for membership in vertex.groups:
                        if membership.group == mask_index:
                            mask_weight = membership.weight
                            break
                    mask_weights.append(max(0.0, min(1.0, mask_weight)))

            for index, co in enumerate(base_coords):
                weight = math.exp(-0.5 * ((co.z - center_z) / sigma) ** 2)
                if mask_weights is not None:
                    weight *= mask_weights[index]
                source = co
                key.data[index].co = (
                    center_x + (source.x - center_x) * (1.0 + x_amount * weight),
                    center_y + (source.y - center_y) * (1.0 + y_amount * weight),
                    source.z,
                )
        context.view_layer.update()
        masked = sum(
            1 for label in ("肩宽", "胸围", "腰围", "臀宽")
            if obj.vertex_groups.get("RH遮罩 | " + label) is not None
        )
        self.report(
            {"INFO"},
            "体型控制已就绪：新建 %d 个，更新 %d 个，使用区域遮罩 %d 个。滑块范围为 -1 到 1。" %
            (created, updated, masked)
        )
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
    rotation: FloatProperty(name="旋转（度）", default=0.0, min=-math.pi, max=math.pi, subtype="ANGLE")
    coordinate_source: EnumProperty(name="坐标来源", items=(
        ("UV", "UV 贴图", "Use the garment's UV map"),
        ("OBJECT", "物体坐标", "Place the pattern in object-local 3D coordinates"),
        ("GENERATED", "生成坐标", "Use normalized generated coordinates")), default="UV")
    offset_x: FloatProperty(name="位置 X", default=0.0, min=-100.0, max=100.0, precision=3)
    offset_y: FloatProperty(name="位置 Y", default=0.0, min=-100.0, max=100.0, precision=3)
    scale_x: FloatProperty(name="横向比例", default=1.0, min=0.01, max=100.0, precision=3)
    scale_y: FloatProperty(name="纵向比例", default=1.0, min=0.01, max=100.0, precision=3)
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
        layout.prop(self, "coordinate_source")
        row = layout.row(align=True)
        row.prop(self, "offset_x")
        row.prop(self, "offset_y")
        row = layout.row(align=True)
        row.prop(self, "scale_x")
        row.prop(self, "scale_y")
        layout.label(text="编辑模式下只给选中面分配印花；物体模式应用到当前材质槽。")
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
        mapping.inputs["Scale"].default_value = (
            self.density * self.scale_x, self.density * self.scale_y, self.density)
        mapping.inputs["Location"].default_value = (self.offset_x, self.offset_y, 0.0)
        coordinate_socket = {"UV": "UV", "OBJECT": "Object", "GENERATED": "Generated"}[self.coordinate_source]
        links.new(texcoord.outputs[coordinate_socket], mapping.inputs["Vector"])

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
        assigned = 0
        face_region_count = 0
        for obj in meshes:
            if obj.mode == "EDIT":
                bm = bmesh.from_edit_mesh(obj.data)
                selected_faces = [face for face in bm.faces if face.select]
                if not selected_faces:
                    continue
                obj.data.materials.append(material)
                slot_index = len(obj.data.materials) - 1
                for face in selected_faces:
                    face.material_index = slot_index
                bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
                face_region_count += len(selected_faces)
                assigned += 1
            else:
                if not obj.data.materials:
                    obj.data.materials.append(material)
                else:
                    slot_index = min(max(obj.active_material_index, 0), len(obj.data.materials) - 1)
                    obj.data.materials[slot_index] = material
                assigned += 1
        if assigned == 0:
            if material.users == 0:
                bpy.data.materials.remove(material)
            self.report({"WARNING"}, "没有可应用的网格；若在编辑模式，请先选中至少一个面。")
            return {"CANCELLED"}
        material["rh_studio_material_type"] = "procedural_fabric_print"
        material["rh_studio_pattern"] = self.pattern
        material["rh_studio_density"] = self.density
        material["rh_studio_sparsity"] = self.sparsity
        material["rh_studio_rotation_degrees"] = self.rotation * 57.295779513
        material["rh_studio_coordinate_source"] = self.coordinate_source
        material["rh_studio_offset_x"] = self.offset_x
        material["rh_studio_offset_y"] = self.offset_y
        material["rh_studio_scale_x"] = self.scale_x
        material["rh_studio_scale_y"] = self.scale_y
        if face_region_count:
            message = "已为 %d 个网格的 %d 个选中面应用局部印花。" % (assigned, face_region_count)
        else:
            message = "已为 %d 个网格应用印花材质。" % assigned
        self.report({"INFO"}, message)
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
    hip_height_ratio: FloatProperty(
        name="髋部高度比例", description="髋部距网格底部的高度 / 总身高",
        default=0.535, min=0.42, max=0.62, precision=3,
    )
    knee_height_ratio: FloatProperty(
        name="膝部高度比例", description="膝部距网格底部的高度 / 总身高",
        default=0.285, min=0.18, max=0.38, precision=3,
    )
    shoulder_height_ratio: FloatProperty(
        name="肩部高度比例", description="肩部距网格底部的高度 / 总身高",
        default=0.805, min=0.70, max=0.90, precision=3,
    )
    shoulder_width_ratio: FloatProperty(
        name="肩宽半比例", description="单侧肩部距身体中线的距离 / 总身高",
        default=0.12, min=0.07, max=0.22, precision=3,
    )
    arm_reach_ratio: FloatProperty(
        name="手臂展开比例", description="单侧手臂从身体中线到手尖的水平距离 / 总身高",
        default=0.50, min=0.34, max=0.68, precision=3,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        self.layout.label(text="按当前人体网格包围盒估算关节位置，可先调整基础比例。")
        self.layout.label(text="这只是初始骨架；生成后仍需检查关节位置、权重和衣物变形。")
        self.layout.prop(self, "hip_height_ratio")
        self.layout.prop(self, "knee_height_ratio")
        self.layout.prop(self, "shoulder_height_ratio")
        self.layout.prop(self, "shoulder_width_ratio")
        self.layout.prop(self, "arm_reach_ratio")
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
        hip_z = min_z + self.hip_height_ratio * h
        knee_z = min_z + self.knee_height_ratio * h
        shoulder_z = min_z + self.shoulder_height_ratio * h
        chest_z = min_z + (self.shoulder_height_ratio - 0.04) * h
        neck_z = min_z + min(0.96, self.shoulder_height_ratio + 0.06) * h
        head_z = min_z + min(0.975, self.shoulder_height_ratio + 0.09) * h
        head_top = min_z + 0.985 * h
        ankle_z = min_z + 0.055 * h
        hip_half = max(0.055 * h, min(0.085 * h, (max_x - min_x) * 0.09))
        shoulder_half = self.shoulder_width_ratio * h
        hand_dist = self.arm_reach_ratio * h
        arm_span = max(0.0, hand_dist - shoulder_half)
        elbow_dist = shoulder_half + arm_span * 0.447
        wrist_dist = shoulder_half + arm_span * 0.908
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
    """Rotate a pose bone around a world-space axis while respecting posed parents."""
    pose_bone = armature.pose.bones.get(bone_name)
    data_bone = armature.data.bones.get(bone_name)
    if pose_bone is None or data_bone is None:
        return False

    # Convert the bone's rest frame into the currently posed parent frame.
    # Using matrix_local alone ignores a rotated parent, which made side-facing
    # poses behave differently from front-facing poses.
    frame_matrix = data_bone.matrix_local.copy()
    parent = pose_bone.parent
    if parent is not None:
        try:
            frame_matrix = (
                parent.matrix
                @ parent.bone.matrix_local.inverted()
                @ data_bone.matrix_local
            )
        except (ValueError, RuntimeError):
            frame_matrix = data_bone.matrix_local.copy()

    pose_bone.rotation_mode = "QUATERNION"
    bone_world_orientation = (
        armature.matrix_world.to_quaternion() @ frame_matrix.to_quaternion()
    )
    world_axis = Vector(axis)
    if world_axis.length_squared < 1e-12:
        return False
    world_axis.normalize()
    world_delta = Quaternion(world_axis, math.radians(degrees))
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




class RH_OT_adjust_active_bone(bpy.types.Operator):
    bl_idname = "rh_studio.adjust_active_bone"
    bl_label = "微调当前骨骼"
    bl_description = "Set the active pose bone's local XYZ rotation in degrees and optionally key it"
    bl_options = {"REGISTER", "UNDO"}

    bone_name: StringProperty(name="目标骨骼", default="")
    rotation_x: FloatProperty(name="X 旋转（度）", subtype="ANGLE",
                              default=0.0, min=math.radians(-360.0), max=math.radians(360.0), precision=2)
    rotation_y: FloatProperty(name="Y 旋转（度）", subtype="ANGLE",
                              default=0.0, min=math.radians(-360.0), max=math.radians(360.0), precision=2)
    rotation_z: FloatProperty(name="Z 旋转（度）", subtype="ANGLE",
                              default=0.0, min=math.radians(-360.0), max=math.radians(360.0), precision=2)
    insert_keyframe: BoolProperty(name="应用后记录当前帧", description="Insert a rotation keyframe for this bone on the current frame", default=False)

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.active_object.type == "ARMATURE"
                    and len(context.active_object.pose.bones) > 0)

    def _target_bone(self, context):
        rig = context.active_object
        name = self.bone_name or (context.active_pose_bone.name if context.active_pose_bone else "")
        return rig.pose.bones.get(name) if rig and rig.type == "ARMATURE" and name else None

    def invoke(self, context, event):
        bone = self._target_bone(context)
        if bone is None:
            self.report({"ERROR"}, "请先选择一根目标骨骼。")
            return {"CANCELLED"}
        self.bone_name = bone.name
        try:
            euler = bone.matrix_basis.to_euler("XYZ")
            self.rotation_x, self.rotation_y, self.rotation_z = euler
        except Exception:
            self.rotation_x = self.rotation_y = self.rotation_z = 0.0
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.label(text="骨骼：%s（局部 XYZ 旋转）" % (self.bone_name or "未指定"))
        layout.prop(self, "rotation_x")
        layout.prop(self, "rotation_y")
        layout.prop(self, "rotation_z")
        layout.prop(self, "insert_keyframe")

    def execute(self, context):
        bone = self._target_bone(context)
        if bone is None:
            self.report({"ERROR"}, "目标骨骼不存在，请重新选择骨架和骨骼。")
            return {"CANCELLED"}
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (self.rotation_x, self.rotation_y, self.rotation_z)
        context.view_layer.update()
        if self.insert_keyframe:
            frame = context.scene.frame_current
            bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone.name)
            self.report({"INFO"}, "已调整骨骼「%s」并记录第 %d 帧关键帧。" % (bone.name, frame))
        else:
            self.report({"INFO"}, "已调整骨骼「%s」的局部旋转；需要动画时可记录关键帧。" % bone.name)
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
        animation_data = rig.animation_data
        action_before = animation_data.action if animation_data else None
        inserted = 0
        for pose_bone in rig.pose.bones:
            if pose_bone.rotation_mode == "QUATERNION":
                rotation_path = "rotation_quaternion"
            elif pose_bone.rotation_mode == "AXIS_ANGLE":
                rotation_path = "rotation_axis_angle"
            else:
                rotation_path = "rotation_euler"
            pose_bone.keyframe_insert(data_path=rotation_path, frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)
            inserted += 1

        # Name only the Action created by this operation. Existing/imported/shared
        # Actions keep their names and identity; inserting a key must not rename them.
        animation_data = rig.animation_data
        action_after = animation_data.action if animation_data else None
        if action_before is None and action_after is not None:
            action_after.name = "RealHuman Motion"
        self.report({"INFO"}, "已在第 %d 帧为 %d 根骨骼记录位置、旋转和缩放关键帧。" % (frame, inserted))
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




# Pose presets are stored inside the .blend scene so they travel with the project.
def _pose_snapshot(rig):
    snapshot = {}
    for bone in rig.pose.bones:
        snapshot[bone.name] = {
            "rotation_mode": bone.rotation_mode,
            "rotation_quaternion": list(bone.rotation_quaternion),
            "rotation_euler": list(bone.rotation_euler),
            "location": list(bone.location),
            "scale": list(bone.scale),
        }
    return snapshot


class RH_OT_save_pose_preset(bpy.types.Operator):
    bl_idname = "rh_studio.save_pose_preset"
    bl_label = "保存当前动作预设"
    bl_description = "Save the current rig pose in the current .blend scene"
    bl_options = {"REGISTER", "UNDO"}

    preset_name: StringProperty(name="预设名称", default="我的动作", maxlen=64)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE" and len(obj.pose.bones) > 0)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def execute(self, context):
        rig = context.active_object
        raw = context.scene.get("rh_studio_pose_library", "{}")
        try:
            library = json.loads(raw)
        except (TypeError, ValueError):
            library = {}
        library[self.preset_name.strip() or "我的动作"] = _pose_snapshot(rig)
        context.scene["rh_studio_pose_library"] = json.dumps(library, ensure_ascii=False)
        self.report({"INFO"}, "已保存动作预设「%s」，保存在当前 .blend 场景中。" % (self.preset_name.strip() or "我的动作"))
        return {"FINISHED"}


class RH_OT_load_pose_preset(bpy.types.Operator):
    bl_idname = "rh_studio.load_pose_preset"
    bl_label = "载入已保存动作预设"
    bl_description = "Load a previously saved pose from this .blend scene"
    bl_options = {"REGISTER", "UNDO"}

    preset_name: StringProperty(name="预设名称", default="我的动作", maxlen=64)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != "ARMATURE":
            return False
        try:
            return bool(json.loads(context.scene.get("rh_studio_pose_library", "{}")))
        except (TypeError, ValueError):
            return False

    def invoke(self, context, event):
        try:
            library = json.loads(context.scene.get("rh_studio_pose_library", "{}"))
        except (TypeError, ValueError):
            library = {}
        if library and self.preset_name == "我的动作":
            self.preset_name = next(iter(library))
        return context.window_manager.invoke_props_dialog(self, width=360)

    def execute(self, context):
        rig = context.active_object
        try:
            library = json.loads(context.scene.get("rh_studio_pose_library", "{}"))
        except (TypeError, ValueError):
            library = {}
        pose = library.get(self.preset_name)
        if not pose:
            self.report({"ERROR"}, "没有找到该预设。可先保存动作，或检查名称。")
            return {"CANCELLED"}
        restored = 0
        for name, values in pose.items():
            bone = rig.pose.bones.get(name)
            if bone is None:
                continue
            bone.rotation_mode = values.get("rotation_mode", "QUATERNION")
            if "rotation_quaternion" in values:
                bone.rotation_quaternion = values["rotation_quaternion"]
            if "rotation_euler" in values:
                bone.rotation_euler = values["rotation_euler"]
            if "location" in values:
                bone.location = values["location"]
            if "scale" in values:
                bone.scale = values["scale"]
            restored += 1
        context.view_layer.update()
        self.report({"INFO"}, "已载入预设「%s」，恢复 %d 根骨骼。" % (self.preset_name, restored))
        return {"FINISHED"}


# Named action-set library. Unlike a single pose preset, this stores the full
# keyed animation Action in the current .blend file for later reuse.
_ACTION_SET_PREFIX = "RH动作集 | "


# Blender dynamic EnumProperty callbacks require returned strings and the
# item tuples/list to remain alive while Blender holds their pointers. Keep a
# stable cached tuple for each distinct action-set signature rather than
# replacing the list on every callback (which can invalidate old item tuples).
_ACTION_SET_ENUM_ITEMS_CACHE = {}
_ACTION_SET_ENUM_STRING_CACHE = set()


def _action_set_items(_self, _context):
    items = []
    for action in bpy.data.actions:
        if action.name.startswith(_ACTION_SET_PREFIX):
            label = str(action.name[len(_ACTION_SET_PREFIX):])
            identifier = str(action.name)
            description = "已保存的整套关键帧动作"
            _ACTION_SET_ENUM_STRING_CACHE.update((identifier, label, description))
            items.append((identifier, label, description))
    if not items:
        placeholder = ("", "暂无已保存动作集", "先为骨架记录至少一个关键帧，再保存动作集")
        _ACTION_SET_ENUM_STRING_CACHE.update(placeholder)
        items.append(placeholder)
    signature = tuple(items)
    cached = _ACTION_SET_ENUM_ITEMS_CACHE.get(signature)
    if cached is None:
        cached = tuple(items)
        _ACTION_SET_ENUM_ITEMS_CACHE[signature] = cached
    return cached

class RH_OT_save_action_set(bpy.types.Operator):
    bl_idname = "rh_studio.save_action_set"
    bl_label = "保存整套动作"
    bl_description = "Duplicate the active animation Action as a named reusable action set inside this .blend file"
    bl_options = {"REGISTER", "UNDO"}

    action_set_name: StringProperty(name="动作集名称", default="我的动作集", maxlen=64)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE"
                    and obj.animation_data and obj.animation_data.action)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)

    def execute(self, context):
        rig = context.active_object
        source = rig.animation_data.action if rig.animation_data else None
        if source is None:
            self.report({"ERROR"}, "当前骨架没有动画关键帧。先摆姿并按 K 或“记录当前姿势关键帧”。")
            return {"CANCELLED"}

        # Refuse to save a layered Action without an active slot: otherwise
        # loading the saved set would have to guess which animation channels
        # the source rig intended to use. Validate before replacing any
        # existing named set, so a rejected save cannot destroy prior data.
        source_slots = getattr(source, "slots", None)
        source_slot = getattr(rig.animation_data, "action_slot", None)
        if source_slots is not None and len(source_slots):
            if source_slot is None or not any(
                    slot.identifier == source_slot.identifier for slot in source_slots):
                self.report(
                    {"ERROR"},
                    "当前动作有 Action Slot，但骨架未绑定有效槽位；请先在动作属性中选择槽位后再保存。",
                )
                return {"CANCELLED"}

        label = self.action_set_name.strip()
        if not label:
            self.report({"ERROR"}, "动作集名称不能为空。")
            return {"CANCELLED"}
        full_name = _ACTION_SET_PREFIX + label
        existing = bpy.data.actions.get(full_name)
        if existing == source:
            self.report({"ERROR"}, "当前正在编辑的动作就是同名动作集；请先改名或复制动画。")
            return {"CANCELLED"}

        # Never delete an existing Action that may still drive another rig.
        # If the name is already in use, preserve that Action and create a
        # numbered library entry instead of silently breaking other objects.
        target_name = full_name
        real_users = 0
        if existing is not None:
            # A saved Action has a fake user to persist in the .blend file.
            # Do not mistake that persistence flag for another rig using it.
            real_users = existing.users - (1 if existing.use_fake_user else 0)
        if existing is not None and real_users > 0:
            suffix = 2
            while bpy.data.actions.get("%s (%d)" % (full_name, suffix)) is not None:
                suffix += 1
            target_name = "%s (%d)" % (full_name, suffix)
        elif existing is not None:
            bpy.data.actions.remove(existing)

        saved = source.copy()
        saved.name = target_name
        saved.use_fake_user = True
        # Preserve which Action Slot the source rig was using. Actions can
        # contain multiple slots of the same ID type, so blindly choosing the
        # first slot when loading can silently select the wrong animation data.
        if source_slot is not None:
            saved["rh_studio_action_slot_identifier"] = source_slot.identifier
        if target_name != full_name:
            self.report({"WARNING"}, "同名动作集仍被其他对象使用，已安全另存为“%s”。" %
                        target_name[len(_ACTION_SET_PREFIX):])
        else:
            self.report({"INFO"}, "已保存整套动作“%s”（关键帧随 .blend 文件保存）。" % label)
        return {"FINISHED"}


class RH_OT_load_action_set(bpy.types.Operator):
    bl_idname = "rh_studio.load_action_set"
    bl_label = "载入整套动作"
    bl_description = "Assign a saved named animation Action to the active armature"
    bl_options = {"REGISTER", "UNDO"}

    action_set: EnumProperty(name="动作集", items=_action_set_items)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE")

    def invoke(self, context, event):
        if not any(action.name.startswith(_ACTION_SET_PREFIX) for action in bpy.data.actions):
            self.report({"WARNING"}, "还没有已保存的动作集。")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=420)

    def execute(self, context):
        rig = context.active_object
        action = bpy.data.actions.get(self.action_set)
        if action is None or not action.name.startswith(_ACTION_SET_PREFIX):
            self.report({"ERROR"}, "找不到所选动作集；请确认它仍保存在当前 .blend 文件中。")
            return {"CANCELLED"}
        rig.animation_data_create()
        rig.animation_data.action = action
        # Layered Actions (Blender 4.4+) need a slot bound to the target ID.
        # An armature may still carry a slot from its previously assigned
        # Action, so explicitly bind a slot belonging to the newly loaded Action.
        action_slots = getattr(action, "slots", None)
        if action_slots is not None and len(action_slots):
            preferred_identifier = action.get("rh_studio_action_slot_identifier", "")
            preferred_slot = next(
                (slot for slot in action_slots
                 if preferred_identifier and slot.identifier == preferred_identifier),
                None,
            )
            if preferred_slot is None:
                # Legacy action sets may not carry slot metadata. Prefer a
                # slot compatible with Object animation, then fall back safely.
                preferred_slot = next(
                    (slot for slot in action_slots
                     if getattr(slot, "target_id_type", "OBJECT") == "OBJECT"),
                    action_slots[0],
                )
            rig.animation_data.action_slot = preferred_slot
        start, end = action.frame_range
        context.scene.frame_set(int(start))
        context.view_layer.update()
        self.report({"INFO"}, "已载入动作集“%s”，帧范围 %.0f–%.0f。" %
                    (action.name[len(_ACTION_SET_PREFIX):], start, end))
        return {"FINISHED"}


class RH_OT_export_action_json(bpy.types.Operator, ExportHelper):
    bl_idname = "rh_studio.export_action_json"
    bl_label = "导出动作 JSON"
    bl_description = "Export the active armature action as portable sampled local bone transforms"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE" and obj.animation_data
                    and obj.animation_data.action)

    def execute(self, context):
        rig = context.active_object
        action = rig.animation_data.action
        start, end = action.frame_range
        first, last = math.floor(start), math.ceil(end)
        if last < first or last - first + 1 > 5000:
            self.report({"ERROR"}, "动作帧范围无效或超过 5000 帧；请先裁剪动作。")
            return {"CANCELLED"}
        scene = context.scene
        original_frame = scene.frame_current
        frames = []
        try:
            for frame in range(first, last + 1):
                scene.frame_set(frame)
                context.view_layer.update()
                bones = {}
                for bone in rig.pose.bones:
                    bones[bone.name] = {
                        "location": [float(v) for v in bone.location],
                        # matrix_basis reflects the active rotation mode (Euler,
                        # axis-angle, or quaternion); rotation_quaternion can be stale
                        # when the bone is animated in a different mode.
                        "rotation_quaternion": [float(v) for v in bone.matrix_basis.to_quaternion()],
                        "scale": [float(v) for v in bone.scale],
                    }
                frames.append({"frame": frame, "bones": bones})
            payload = {
                "format": "realhuman_studio_action_v1",
                "name": action.name,
                "source_rig": rig.name,
                "fps": scene.render.fps / max(scene.render.fps_base, 1e-8),
                "frame_start": first,
                "frame_end": last,
                "rotation_representation": "local_quaternion",
                "frames": frames,
            }
            filepath = os.path.abspath(bpy.path.abspath(self.filepath))
            if Path(filepath).suffix.lower() != ".json":
                filepath = str(Path(filepath).with_suffix(".json"))
            # Write beside the destination, then atomically replace it. A failed
            # serialization must not truncate a previously valid export.
            temporary_path = filepath + ".tmp-" + uuid.uuid4().hex
            try:
                with open(temporary_path, "x", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, filepath)
                temporary_path = None
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    try:
                        os.remove(temporary_path)
                    except OSError:
                        pass
        except Exception as exc:
            self.report({"ERROR"}, "导出动作 JSON 失败：" + str(exc))
            return {"CANCELLED"}
        finally:
            scene.frame_set(original_frame)
            context.view_layer.update()
        self.report({"INFO"}, "已导出 %d 帧、%d 根骨骼的动作 JSON。" %
                    (len(frames), len(rig.pose.bones)))
        return {"FINISHED"}


class RH_OT_import_action_json(bpy.types.Operator, ImportHelper):
    bl_idname = "rh_studio.import_action_json"
    bl_label = "导入动作 JSON"
    bl_description = "Import a RealHuman Studio sampled action onto matching bones of the active armature"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE" and len(obj.pose.bones) > 0)

    def execute(self, context):
        rig = context.active_object
        filepath = os.path.abspath(bpy.path.abspath(self.filepath))
        try:
            with open(filepath, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, dict) or payload.get("format") != "realhuman_studio_action_v1":
                raise ValueError("文件格式不属于 RealHuman Studio action_v1。")
            rotation_representation = payload.get("rotation_representation", "local_quaternion")
            if rotation_representation != "local_quaternion":
                raise ValueError("暂不支持该旋转表示方式：" + str(rotation_representation))
            source_fps = payload.get("fps")
            if source_fps is not None:
                if isinstance(source_fps, bool) or not isinstance(source_fps, (int, float)):
                    raise ValueError("动作 FPS 元数据无效。")
                source_fps = float(source_fps)
                if not math.isfinite(source_fps) or source_fps <= 0.0 or source_fps > 1000.0:
                    raise ValueError("动作 FPS 必须是 0 到 1000 之间的有限正数。")
            frames = payload.get("frames")
            if not isinstance(frames, list) or not frames or len(frames) > 5000:
                raise ValueError("动作帧数据为空或超过 5000 个采样点。")
            validated = []
            available_bones = {bone.name for bone in rig.pose.bones}
            matched_bones = set()
            previous_frame = None
            for entry in frames:
                if (not isinstance(entry, dict) or not isinstance(entry.get("frame"), int)
                        or isinstance(entry.get("frame"), bool)):
                    raise ValueError("帧数据结构无效。")
                frame = entry["frame"]
                if abs(frame) > 1000000:
                    raise ValueError("帧号超出安全范围。")
                if previous_frame is not None and frame <= previous_frame:
                    raise ValueError("帧号必须严格递增。")
                previous_frame = frame
                bone_data = entry.get("bones")
                if not isinstance(bone_data, dict):
                    raise ValueError("骨骼数据结构无效。")
                validated_bones = {}
                for name, values in bone_data.items():
                    if name not in available_bones:
                        continue
                    if not isinstance(values, dict):
                        raise ValueError("骨骼 %s 的数据无效。" % name)
                    clean = {}
                    for key, length in (("location", 3), ("rotation_quaternion", 4), ("scale", 3)):
                        vector = values.get(key)
                        if not isinstance(vector, list) or len(vector) != length:
                            raise ValueError("骨骼 %s 缺少有效的 %s。" % (name, key))
                        numbers = [float(value) for value in vector]
                        if not all(math.isfinite(value) for value in numbers):
                            raise ValueError("骨骼 %s 含有非有限数值。" % name)
                        clean[key] = numbers
                    quaternion = clean["rotation_quaternion"]
                    quaternion_length = math.sqrt(sum(value * value for value in quaternion))
                    if quaternion_length <= 1e-12:
                        raise ValueError("骨骼 %s 的四元数长度为零。" % name)
                    clean["rotation_quaternion"] = [
                        value / quaternion_length for value in quaternion
                    ]
                    validated_bones[name] = clean
                    matched_bones.add(name)
                validated.append((frame, validated_bones))
            if not matched_bones:
                raise ValueError("当前骨架与该动作没有同名骨骼，无法导入。")
        except Exception as exc:
            self.report({"ERROR"}, "动作 JSON 无法导入：" + str(exc))
            return {"CANCELLED"}

        scene = context.scene
        original_frame = scene.frame_current
        old_action = rig.animation_data.action if rig.animation_data else None
        old_action_slot = (
            getattr(rig.animation_data, "action_slot", None)
            if rig.animation_data else None
        )
        # Keep a full pose snapshot so an exception during key insertion cannot
        # leave the rig visually half-imported when no old Action is assigned.
        pose_snapshot = {
            bone.name: {
                "location": tuple(bone.location),
                "rotation_mode": bone.rotation_mode,
                "rotation_quaternion": tuple(bone.rotation_quaternion),
                "rotation_euler": tuple(bone.rotation_euler),
                "rotation_axis_angle": tuple(bone.rotation_axis_angle),
                "scale": tuple(bone.scale),
            }
            for bone in rig.pose.bones
        }
        new_action = None
        rollback_pose = False
        try:
            rig.animation_data_create()
            rig.animation_data.action = None
            for frame, bone_data in validated:
                scene.frame_set(frame)
                for name, values in bone_data.items():
                    bone = rig.pose.bones.get(name)
                    bone.location = values["location"]
                    bone.rotation_mode = "QUATERNION"
                    bone.rotation_quaternion = values["rotation_quaternion"]
                    bone.scale = values["scale"]
                    _insert_action_json_keyframe(bone, "location", frame, name)
                    _insert_action_json_keyframe(bone, "rotation_quaternion", frame, name)
                    _insert_action_json_keyframe(bone, "scale", frame, name)
            new_action = rig.animation_data.action
            if new_action is None:
                raise RuntimeError("Blender 未创建动画 Action。")
            imported_name = Path(filepath).stem
            new_action.name = "RH导入动作 | " + imported_name[:64]
            new_action.use_fake_user = True
        except Exception as exc:
            partial_action = rig.animation_data.action if rig.animation_data else None
            rig.animation_data.action = old_action
            if old_action is not None and old_action_slot is not None:
                try:
                    if any(
                        slot.identifier == old_action_slot.identifier
                        for slot in old_action.slots
                    ):
                        rig.animation_data.action_slot = old_action_slot
                except (AttributeError, ReferenceError, RuntimeError):
                    # Older Blender versions do not expose Action Slots.
                    pass
            rollback_pose = True
            orphan_action = new_action or partial_action
            if (orphan_action is not None and orphan_action != old_action
                    and orphan_action.users == 0):
                bpy.data.actions.remove(orphan_action)
            self.report({"ERROR"}, "写入动作失败，已恢复原动作与骨骼姿态：" + str(exc))
            return {"CANCELLED"}
        finally:
            # Restore the frame first because evaluating the original Action can
            # overwrite manually restored pose values. Reapply the snapshot only
            # on the rollback path, after frame evaluation has completed.
            scene.frame_set(original_frame)
            if rollback_pose:
                for bone_name, values in pose_snapshot.items():
                    bone = rig.pose.bones.get(bone_name)
                    if bone is None:
                        continue
                    bone.location = values["location"]
                    bone.rotation_mode = values["rotation_mode"]
                    bone.rotation_quaternion = values["rotation_quaternion"]
                    bone.rotation_euler = values["rotation_euler"]
                    bone.rotation_axis_angle = values["rotation_axis_angle"]
                    bone.scale = values["scale"]
            context.view_layer.update()
        if source_fps is not None:
            scene_fps = scene.render.fps / max(scene.render.fps_base, 1e-8)
            if abs(source_fps - scene_fps) > 0.01:
                self.report(
                    {"WARNING"},
                    "动作源帧率 %.3g FPS，当前场景 %.3g FPS；未自动改帧率，请确认播放速度。" %
                    (source_fps, scene_fps))
            else:
                self.report({"INFO"}, "动作源帧率与当前场景一致（%.3g FPS）。" % scene_fps)
        self.report({"INFO"}, "已导入动作 JSON，匹配 %d 根骨骼、%d 个采样帧。" %
                    (len(matched_bones), len(validated)))
        return {"FINISHED"}


class RH_OT_check_action_sequence(bpy.types.Operator):
    bl_idname = "rh_studio.check_action_sequence"
    bl_label = "检查动作序列"
    bl_description = "Check basic animation conditions before playback or export"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE")

    def execute(self, context):
        rig = context.active_object
        action = rig.animation_data.action if rig.animation_data else None
        if action is None:
            self.report({"ERROR"}, "动作序列不成立：当前骨架没有绑定动画动作。")
            return {"CANCELLED"}
        start, end = action.frame_range
        if end < start or not math.isfinite(start) or not math.isfinite(end):
            self.report({"ERROR"}, "动作序列帧范围无效，请检查关键帧。")
            return {"CANCELLED"}
        if end - start < 1:
            self.report({"WARNING"}, "动作序列只有一个时间点；至少再记录一帧才能形成动作。")
            return {"FINISHED"}
        if context.scene.frame_current < start or context.scene.frame_current > end:
            self.report({"WARNING"}, "当前时间帧在动作范围之外（动作范围 %.0f–%.0f）。" % (start, end))
            return {"FINISHED"}
        self.report({"INFO"}, "基础检查通过：动作“%s”，帧范围 %.0f–%.0f。此检查不代表已验证动作衔接或网格碰撞。" %
                    (action.name, start, end))
        return {"FINISHED"}



class RH_OT_check_pose_clearance(bpy.types.Operator):
    bl_idname = "rh_studio.check_pose_clearance"
    bl_label = "检查肢体间距 / 重叠风险"
    bl_description = "Run simple geometric warnings for near-crossing limbs and torso intersections"
    bl_options = {"REGISTER"}

    min_clearance: FloatProperty(name="最小间距（米）", default=0.035, min=0.001, max=0.25, subtype="DISTANCE")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "ARMATURE")

    def execute(self, context):
        rig = context.active_object
        context.view_layer.update()
        def point(name, endpoint):
            pb = rig.pose.bones.get(name)
            if pb is None:
                return None
            v = pb.head if endpoint == "head" else pb.tail
            return rig.matrix_world @ v
        warnings = []
        for side_a, side_b, joint in (("L", "R", "hand"), ("L", "R", "forearm"),
                                      ("L", "R", "foot"), ("L", "R", "thigh")):
            a = point(joint + "." + side_a, "tail")
            b = point(joint + "." + side_b, "tail")
            if a is not None and b is not None and (a-b).length < self.min_clearance:
                warnings.append("%s.%s 与 %s.%s 太近" % (joint, side_a, joint, side_b))
        chest = point("chest", "head")
        for side in ("L", "R"):
            hand = point("hand." + side, "tail")
            if chest is not None and hand is not None and (chest-hand).length < self.min_clearance * 1.5:
                warnings.append("手部可能穿入胸口：hand." + side)
        if warnings:
            self.report({"WARNING"}, "检测到 %d 项近距离风险：" % len(warnings) + "；".join(warnings[:4]))
        else:
            self.report({"INFO"}, "未发现简单距离规则触发的风险；这不是完整的网格碰撞检测。")
        return {"FINISHED"}


class RH_OT_turn_body_preset(bpy.types.Operator):
    bl_idname = "rh_studio.turn_body_preset"
    bl_label = "身体朝向预设"
    bl_description = "Turn the torso and head for three-quarter or side-facing poses"
    bl_options = {"REGISTER", "UNDO"}

    facing: EnumProperty(name="朝向", items=(
        ("FRONT", "正面", "Face forward"),
        ("THREE_QUARTER_L", "左侧 45°", "Three-quarter left"),
        ("THREE_QUARTER_R", "右侧 45°", "Three-quarter right"),
        ("SIDE_L", "左侧面", "Face left"),
        ("SIDE_R", "右侧面", "Face right"),
        ("BACK", "背面", "Face away"),
    ), default="THREE_QUARTER_L")

    @classmethod
    def poll(cls, context):
        return bool(context.active_object and context.active_object.type == "ARMATURE")

    def execute(self, context):
        rig = context.active_object
        angle = {"FRONT": 0, "THREE_QUARTER_L": -45, "THREE_QUARTER_R": 45,
                 "SIDE_L": -90, "SIDE_R": 90, "BACK": 180}[self.facing]
        # Rotate root for global facing; add slight counter-rotation in chest/head
        # so profile poses can be refined without forcing a perfectly rigid torso.
        root = rig.pose.bones.get("root")
        if root:
            root.rotation_mode = "XYZ"
            root.rotation_euler.z = math.radians(angle)
        context.view_layer.update()
        self.report({"INFO"}, "已设置身体朝向 %s。可继续分别旋转胸腔、颈部和头部。" % self.facing)
        return {"FINISHED"}


BODY_REACTION_TOKENS = {
    "ANGER_VEINS": ("vein", "vascular", "bloodvessel", "blood_vessel", "veins", "血管", "青筋"),
    "MUSCLE_TENSE": ("muscle", "tense", "flex", "bulge", "pump", "肌肉", "紧绷", "凸起"),
}
class RH_OT_body_reaction_preset(bpy.types.Operator):
    bl_idname = "rh_studio.body_reaction_preset"
    bl_label = "情绪身体反应"
    bl_description = "Drive existing body morph keys for reactions such as bulging veins or tense muscles"
    bl_options = {"REGISTER", "UNDO"}

    reaction: EnumProperty(name="反应", items=(
        ("ANGER_VEINS", "愤怒：青筋凸起", "Enable recognized vein/vascular morph keys"),
        ("MUSCLE_TENSE", "紧绷：肌肉凸起", "Enable recognized tense-muscle morph keys"),
        ("RESET", "身体反应复位", "Reset recognized body-reaction morph keys"),
    ), default="ANGER_VEINS")
    amount: FloatProperty(name="强度", default=1.0, min=0.0, max=1.0, subtype="FACTOR")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.data.shape_keys
                    and len(obj.data.shape_keys.key_blocks) > 1)

    def execute(self, context):
        obj = context.active_object
        keys = list(obj.data.shape_keys.key_blocks)[1:]
        groups = {name: [key for key in keys if any(token in key.name.lower() for token in tokens)]
                  for name, tokens in BODY_REACTION_TOKENS.items()}
        reaction_keys = [key for values in groups.values() for key in values]
        if self.reaction == "RESET":
            for key in reaction_keys:
                key.value = 0.0
            self.report({"INFO"}, "已复位 %d 个可识别的身体反应形态键。" % len(reaction_keys))
            return {"FINISHED"} if reaction_keys else {"CANCELLED"}
        matched = groups.get(self.reaction, [])
        if not matched:
            self.report({"WARNING"}, "没有找到血管/肌肉反应形态键；需要模型本身提供这些 morph/Shape Keys。")
            return {"CANCELLED"}
        for key in reaction_keys:
            key.value = 0.0
        for key in matched:
            key.value = self.amount
        self.report({"INFO"}, "已设置 %d 个身体反应形态键，强度 %.2f。" % (len(matched), self.amount))
        return {"FINISHED"}



def _insert_rig_pose_keyframes(rig, frame):
    """Insert the active rotation representation, location, and scale for every pose bone."""
    inserted = 0
    for bone in rig.pose.bones:
        if bone.rotation_mode == "QUATERNION":
            path = "rotation_quaternion"
        elif bone.rotation_mode == "AXIS_ANGLE":
            path = "rotation_axis_angle"
        else:
            path = "rotation_euler"
        bone.keyframe_insert(data_path=path, frame=frame, group=bone.name)
        bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
        bone.keyframe_insert(data_path="scale", frame=frame, group=bone.name)
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Minimal 2D pose pad: circle head + large-character body, with four drag handles.
# The drawing is rendered into the 3D VIEW region, not the sidebar region.
def _simple_pose_pad_center(width, height):
    """Return a sketch center that keeps the head and footer inside small view regions."""
    width = float(width)
    height = float(height)
    cx = max(120.0, min(width - 120.0, width * 0.72))
    # The drawing extends roughly 99 px above and 124 px below its center.
    # Keep at least 124 px below for the footer and 100 px above for the head.
    cy = max(124.0, min(height - 100.0, height * 0.50))
    return cx, cy


class RH_OT_simple_2d_pose_pad(bpy.types.Operator):
    bl_idname = "rh_studio.simple_2d_pose_pad"
    bl_label = "简笔摆姿"
    bl_description = "Minimal circle-head / 大-shaped pose editor: drag hands and feet"
    bl_options = {"REGISTER", "UNDO"}

    _CONTROL_BONES = {
        "hand.L": "upper_arm.L",
        "hand.R": "upper_arm.R",
        "foot.L": "thigh.L",
        "foot.R": "thigh.R",
    }

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        required = (
            "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R",
            "hand.L", "hand.R", "thigh.L", "thigh.R",
            "shin.L", "shin.R", "foot.L", "foot.R",
        )
        return bool(obj and obj.type == "ARMATURE"
                    and all(obj.pose.bones.get(name) for name in required))

    def _draw(self):
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader

        ctx = bpy.context
        if (ctx.area != self._area or not ctx.region
                or ctx.region.type != "WINDOW"):
            return

        # Blender 4.5+ requires the POLYLINE shader variant for reliable
        # line widths; gpu.state.line_width_set() alone is not sufficient.
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")

        def line(points, color, width=2.0, closed=False):
            if len(points) < 2:
                return
            coords = [(point[0], point[1], 0.0) for point in points]
            if closed:
                coords.append(coords[0])
            batch = batch_for_shader(shader, "LINE_STRIP", {"pos": coords})
            shader.bind()
            shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
            shader.uniform_float("lineWidth", float(width))
            shader.uniform_float("color", color)
            batch.draw(shader)

        def circle(cx, cy, radius, color, width=2.0):
            points = [
                (cx + math.cos(i * 2.0 * math.pi / 48.0) * radius,
                 cy + math.sin(i * 2.0 * math.pi / 48.0) * radius)
                for i in range(48)
            ]
            line(points, color, width, closed=True)

        try:
            gpu.state.blend_set("ALPHA")
            pale = (0.82, 0.88, 0.98, 0.96)
            accent = (0.22, 0.72, 1.0, 1.0)
            handle = (1.0, 0.62, 0.18, 1.0)
            p = self._points

            # Intentionally no elbows/knees: only the circle head, trunk,
            # diagonal limbs, and four draggable endpoints.
            circle(*p["head"], 15.0, accent, 2.0)
            line([p["neck"], p["hips"]], pale, 2.5)
            line([p["neck"], p["shoulder.L"]], pale, 2.0)
            line([p["neck"], p["shoulder.R"]], pale, 2.0)
            line([p["shoulder.L"], p["hand.L"]], pale, 2.5)
            line([p["shoulder.R"], p["hand.R"]], pale, 2.5)
            line([p["hips"], p["hip.L"]], pale, 1.5)
            line([p["hips"], p["hip.R"]], pale, 1.5)
            line([p["hip.L"], p["foot.L"]], pale, 2.5)
            line([p["hip.R"], p["foot.R"]], pale, 2.5)

            for name in self._CONTROL_BONES:
                circle(*p[name], 6.0, handle, 2.0)

            blf.color(0, 0.92, 0.95, 1.0, 1.0)
            blf.position(0, self._cx - 37, self._cy + 115, 0)
            blf.size(0, 13)
            blf.draw(0, "简笔摆姿")
            blf.position(0, self._cx - 78, self._cy - 108, 0)
            blf.size(0, 11)
            blf.draw(0, "拖动手 / 脚端点")
            blf.position(0, self._cx - 105, self._cy - 124, 0)
            blf.draw(0, "K 记录关键帧 · R 复位 · Esc 退出")
        finally:
            gpu.state.blend_set("NONE")

    def _remove_handler(self):
        handle = getattr(self, "_draw_handle", None)
        if handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            except (ReferenceError, RuntimeError):
                pass
            self._draw_handle = None
        for region in (getattr(self, "_view_region", None),
                       getattr(self, "_source_region", None)):
            if region is not None:
                try:
                    region.tag_redraw()
                except ReferenceError:
                    pass
        area = getattr(self, "_area", None)
        if area is not None:
            try:
                area.tag_redraw()
            except ReferenceError:
                pass

    @staticmethod
    def _set_bone_quaternion(bone, quaternion, original_mode):
        """Convert an edited quaternion back to the bone's original rotation mode."""
        q = quaternion.copy()
        bone.rotation_mode = original_mode
        if original_mode == "QUATERNION":
            bone.rotation_quaternion = q
        elif original_mode == "AXIS_ANGLE":
            axis = q.axis
            bone.rotation_axis_angle = (q.angle, axis.x, axis.y, axis.z)
        else:
            bone.rotation_euler = q.to_euler(original_mode)

    def _apply_pose(self, context):
        rig = self._rig
        if rig is None or rig.type != "ARMATURE":
            return

        # Use the active 3D view's camera-facing axis even when this operator
        # was launched from the sidebar (whose region_data is None).
        axis = Vector((0.0, 1.0, 0.0))
        space = getattr(self, "_space", None)
        region_3d = getattr(space, "region_3d", None) if space else None
        if region_3d is not None:
            axis = region_3d.view_rotation @ Vector((0.0, 0.0, 1.0))
        if axis.length > 1e-8:
            axis.normalize()

        for name, state in self._base_states.items():
            bone = rig.pose.bones.get(name)
            if bone:
                bone.rotation_mode = "QUATERNION"
                bone.rotation_quaternion = state["quaternion"]
                bone.location = state["location"]
                bone.scale = state["scale"]

        for endpoint, bone_name in self._CONTROL_BONES.items():
            delta = self._angles.get(endpoint, 0.0)
            if abs(delta) > 1e-7:
                _rotate_pose_bone_about_world_axis(
                    rig, bone_name, axis, math.degrees(delta)
                )

        # Keep each bone's original rotation mode so the normal keyframing
        # workflow continues to use the right animation channels.
        for name, state in self._base_states.items():
            bone = rig.pose.bones.get(name)
            if bone:
                current = bone.rotation_quaternion.copy()
                self._set_bone_quaternion(bone, current, state["mode"])
        context.view_layer.update()

    def _mouse_in_view(self, event):
        # Region.x/y are window-relative. mouse_x/y are likewise window-relative;
        # mouse_region_x/y would jump when the pointer crosses the sidebar edge.
        return (
            float(event.mouse_x - self._view_region.x),
            float(event.mouse_y - self._view_region.y),
        )

    def _redraw(self):
        try:
            self._view_region.tag_redraw()
            self._area.tag_redraw()
        except ReferenceError:
            pass

    def _reset_sketch(self, context):
        cx, cy = self._cx, self._cy
        self._points.update({
            "head": (cx, cy + 84.0),
            "neck": (cx, cy + 65.0),
            "shoulder.L": (cx - 20.0, cy + 43.0),
            "shoulder.R": (cx + 20.0, cy + 43.0),
            "hips": (cx, cy - 5.0),
            "hip.L": (cx - 12.0, cy - 5.0),
            "hip.R": (cx + 12.0, cy - 5.0),
            "hand.L": (cx - 72.0, cy + 65.0),
            "hand.R": (cx + 72.0, cy + 65.0),
            "foot.L": (cx - 49.0, cy - 78.0),
            "foot.R": (cx + 49.0, cy - 78.0),
        })
        for name in self._CONTROL_BONES:
            self._angles[name] = 0.0
        self._apply_pose(context)
        self._redraw()

    def _insert_keyframes(self, context):
        rig = self._rig
        if not rig or rig.type != "ARMATURE":
            self.report({"ERROR"}, "当前骨架不可用，无法记录关键帧。")
            return False
        frame = context.scene.frame_current
        previous_action = rig.animation_data.action if rig.animation_data else None
        inserted = _insert_rig_pose_keyframes(rig, frame)
        current_action = rig.animation_data.action if rig.animation_data else None
        # Name only an Action created by this operation. Renaming a pre-existing
        # Action can unexpectedly change its name for every object sharing it.
        if current_action is not None and current_action is not previous_action:
            current_action.name = "RealHuman Motion"
        self.report({"INFO"}, "已记录第 %d 帧的 %d 根骨骼姿势（位置、旋转、缩放）。可切换时间轴帧继续摆姿。" %
                    (frame, inserted))
        return True

    def invoke(self, context, event):
        self._area = context.area
        self._source_region = context.region
        self._view_region = next(
            (region for region in context.area.regions if region.type == "WINDOW"), None
        )
        if self._view_region is None:
            self.report({"ERROR"}, "找不到 3D 视图区域，请在 3D 视图中启动简笔摆姿。")
            return {"CANCELLED"}

        self._space = context.area.spaces.active
        width = float(self._view_region.width)
        height = float(self._view_region.height)
        if width < 240 or height < 224:
            self.report({"ERROR"}, "3D 视图太小（至少 240×224），请先放大视图区域。")
            return {"CANCELLED"}
        self._cx, self._cy = _simple_pose_pad_center(width, height)

        self._points = {}
        self._angles = {name: 0.0 for name in self._CONTROL_BONES}
        self._reset_sketch_points_only()
        self._drag_handle = None
        self._rig = context.active_object
        context.view_layer.update()
        self._base_states = {}
        for name in set(self._CONTROL_BONES.values()):
            bone = self._rig.pose.bones.get(name)
            if bone is None:
                self.report({"WARNING"}, "此骨架缺少必要的四肢骨骼。")
                return {"CANCELLED"}
            self._base_states[name] = {
                "mode": bone.rotation_mode,
                "quaternion": bone.matrix_basis.to_quaternion(),
                "location": bone.location.copy(),
                "scale": bone.scale.copy(),
            }

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw, (), "WINDOW", "POST_PIXEL"
        )
        context.window_manager.modal_handler_add(self)
        self._redraw()
        self.report({"INFO"}, "拖动四个橙色端点；K 记录关键帧，R 复位，Esc 退出。")
        return {"RUNNING_MODAL"}

    def _reset_sketch_points_only(self):
        cx, cy = self._cx, self._cy
        self._points = {
            "head": (cx, cy + 84.0),
            "neck": (cx, cy + 65.0),
            "shoulder.L": (cx - 20.0, cy + 43.0),
            "shoulder.R": (cx + 20.0, cy + 43.0),
            "hips": (cx, cy - 5.0),
            "hip.L": (cx - 12.0, cy - 5.0),
            "hip.R": (cx + 12.0, cy - 5.0),
            "hand.L": (cx - 72.0, cy + 65.0),
            "hand.R": (cx + 72.0, cy + 65.0),
            "foot.L": (cx - 49.0, cy - 78.0),
            "foot.R": (cx + 49.0, cy - 78.0),
        }
        self._base_points = {
            name: self._points[name] for name in self._CONTROL_BONES
        }

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            self._remove_handler()
            return {"FINISHED"}

        if event.type == "K" and event.value == "PRESS":
            self._insert_keyframes(context)
            self._redraw()
            return {"RUNNING_MODAL"}

        if event.type == "R" and event.value == "PRESS":
            self._reset_sketch(context)
            return {"RUNNING_MODAL"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"RUNNING_MODAL", "PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            mx, my = self._mouse_in_view(event)
            for name in self._CONTROL_BONES:
                x, y = self._points[name]
                if (mx - x) ** 2 + (my - y) ** 2 <= 16.0 ** 2:
                    self._drag_handle = name
                    return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE" and self._drag_handle:
            name = self._drag_handle
            root_name = {
                "hand.L": "shoulder.L", "hand.R": "shoulder.R",
                "foot.L": "hip.L", "foot.R": "hip.R",
            }[name]
            root_x, root_y = self._points[root_name]
            mx, my = self._mouse_in_view(event)
            dx, dy = mx - root_x, my - root_y
            if math.hypot(dx, dy) > 1.0:
                target_angle = math.atan2(dy, dx)
                base_x, base_y = self._base_points[name]
                base_angle = math.atan2(base_y - root_y, base_x - root_x)
                raw_delta = target_angle - base_angle
                self._angles[name] = math.atan2(math.sin(raw_delta), math.cos(raw_delta))
                length = math.hypot(base_x - root_x, base_y - root_y)
                self._points[name] = (
                    root_x + math.cos(target_angle) * length,
                    root_y + math.sin(target_angle) * length,
                )
                self._apply_pose(context)
                self._redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._drag_handle = None
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._remove_handler()

CLASSES = (
    RH_OT_setup_project, RH_OT_create_layers, RH_OT_import_asset,
    RH_OT_export_asset_manifest, RH_OT_scan_missing_sources, RH_OT_apply_missing_source_repairs,
    RH_OT_view_missing_source_repair_results, RH_OT_copy_repair_result_path, RH_OT_relink_asset_source, RH_OT_audit_project_assets, RH_OT_audit_selected_assets, RH_OT_diagnose_asset_scale, RH_OT_normalize_selected_assets,
    RH_OT_assign_category, RH_OT_toggle_category, RH_OT_select_category,
    RH_OT_fit_height, RH_OT_fit_selected_group_height, RH_OT_generate_body_proportion_keys, RH_OT_reset_shape_keys, RH_OT_set_view, RH_OT_export_model,
    RH_OT_create_fabric_print, RH_OT_generate_simple_rig,
    RH_OT_apply_pose_preset, RH_OT_adjust_active_bone, RH_OT_toggle_pose_mode,
    RH_OT_insert_pose_keyframe, RH_OT_expression_preset,
    RH_OT_save_pose_preset, RH_OT_load_pose_preset,
    RH_OT_save_action_set, RH_OT_load_action_set,
    RH_OT_export_action_json, RH_OT_import_action_json, RH_OT_check_action_sequence,
    RH_OT_check_pose_clearance, RH_OT_turn_body_preset, RH_OT_body_reaction_preset,
    RH_OT_simple_2d_pose_pad,
)

def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
