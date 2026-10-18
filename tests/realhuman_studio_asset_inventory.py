# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory a Blender .blend asset library without appending its objects.

Usage in Blender:
1. Edit SOURCE_BLEND below to point at a .blend file from an asset bundle.
2. Open this script in Blender's Text Editor and Run Script.
3. Review the generated JSON beside the source file (or set OUTPUT_JSON).

This uses bpy.data.libraries.load only to inspect datablock names. It does not
append, link, modify, or save the source asset. Object names in the report can
then be used by RealHuman Studio's exact-name import filter and category map.
"""
import json
import os
from datetime import datetime, timezone

import bpy

# Set this to the extracted asset .blend file. Example: r"D:\\Assets\\human.blend"
SOURCE_BLEND = r""
# Optional absolute output path; blank writes beside SOURCE_BLEND.
OUTPUT_JSON = r""


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    source_path = os.path.abspath(bpy.path.abspath(SOURCE_BLEND)) if SOURCE_BLEND else ""
    ensure(source_path and os.path.isfile(source_path),
           "Set SOURCE_BLEND to an existing .blend file before running the inventory script.")
    ensure(os.path.splitext(source_path)[1].lower() == ".blend",
           "SOURCE_BLEND must point to a .blend file, not the bundle ZIP itself.")

    with bpy.data.libraries.load(source_path, link=True) as (data_from, _data_to):
        inventory = {
            "objects": sorted(data_from.objects),
            "collections": sorted(data_from.collections),
            "meshes": sorted(data_from.meshes),
            "armatures": sorted(data_from.armatures),
            "materials": sorted(data_from.materials),
            "images": sorted(data_from.images),
            "actions": sorted(data_from.actions),
            "curves": sorted(data_from.curves),
        }

    inventory["schema"] = "realhuman_studio_blend_library_inventory_v1"
    inventory["created_utc"] = datetime.now(timezone.utc).isoformat()
    inventory["blender_version"] = bpy.app.version_string
    inventory["source_blend"] = source_path
    inventory["counts"] = {key: len(value) for key, value in inventory.items()
                            if isinstance(value, list)}

    # Name-based suggestions are intentionally advisory. They never alter the
    # source file or auto-import objects; review them before using category_map_json.
    category_rules = (
        ("BASE_BODY", ("base body", "base_body", "basemesh", "base mesh", "body base", "bodymesh", "body mesh", "human body")),
        ("SKIN", ("skin", "epiderm", "dermis", "皮肤")),
        ("FAT", ("fat", "adipose", "脂肪")),
        ("BONES", ("bone", "skeleton", "skeletal", "骨骼")),
        ("MUSCLES", ("muscle", "muscular", "肌肉")),
        ("NERVES", ("nerve", "nervous", "神经")),
        ("VESSELS", ("vessel", "artery", "arteries", "vein", "veins", "vascular", "血管")),
        ("ORGANS", ("organ", "organs", "viscera", "内脏", "器官")),
        ("HAIR", ("hair", "scalp", "毛发")),
        ("TISSUE", ("fascia", "connective tissue", "tissue", "筋膜", "组织")),
        ("CLOTHING", ("cloth", "clothing", "garment", "衣服", "服装")),
        ("RIG", ("armature", "rig", "skeleton rig", "骨架绑定")),
    )

    suggestions = []
    for object_name in inventory["objects"]:
        normalized = object_name.casefold()
        matches = []
        for category, terms in category_rules:
            if any(term.casefold() in normalized for term in terms):
                matches.append(category)
        suggestions.append({
            "object_name": object_name,
            "suggested_category": matches[0] if len(matches) == 1 else None,
            "candidate_categories": matches,
            "status": "suggested_review_required" if len(matches) == 1 else (
                "ambiguous_review_required" if matches else "unclassified_review_required"),
        })
    inventory["category_suggestions"] = suggestions
    inventory["notes"] = [
        "This report inventories datablock names only; it does not prove mesh quality or anatomy.",
        "Object names are exact source-library names and may differ from collection names.",
        "A collection's nested hierarchy is not inferred from the name list.",
        "category_suggestions are keyword-based hints only; manually verify anatomy before importing.",
        "An object name can match multiple categories or none; ambiguous/unclassified entries are not auto-assigned.",
        "Inspect upstream license and attribution separately before redistributing any asset.",
    ]

    output_path = os.path.abspath(OUTPUT_JSON) if OUTPUT_JSON else os.path.join(
        os.path.dirname(source_path), "realhuman_studio_asset_inventory.json")
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(inventory, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

    print("REALHUMAN_STUDIO_ASSET_INVENTORY: PASS")
    print("Source: %s" % source_path)
    print("Output: %s" % output_path)
    for key in ("objects", "collections", "meshes", "armatures", "materials", "images", "actions"):
        print("%s: %d" % (key, inventory["counts"].get(key, 0)))


main()
