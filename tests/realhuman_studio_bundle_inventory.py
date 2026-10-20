# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory every .blend file in an extracted asset-bundle directory.

Run inside Blender (Text Editor > Run Script). Set SOURCE_DIRECTORY below to
an extracted asset bundle folder. The script reads library datablock names only;
it does not append, link, modify, or save any source asset.

Output: realhuman_studio_bundle_inventory.json in SOURCE_DIRECTORY, unless
OUTPUT_JSON is set to an absolute path.
"""
import json
import os
from datetime import datetime, timezone

import bpy

SOURCE_DIRECTORY = r""
OUTPUT_JSON = r""
SCHEMA = "realhuman_studio_blend_bundle_inventory_v1"

CATEGORY_RULES = (
    ("BASE_BODY", ("base body", "base_body", "basemesh", "base mesh", "body base", "bodymesh", "body mesh", "human body", "realistic male", "realistic female")),
    ("SKIN", ("skin", "epiderm", "dermis", "皮肤")),
    ("FAT", ("fat", "adipose", "脂肪")),
    ("BONES", ("bone", "skeleton", "skeletal", "skull", "骨骼")),
    ("MUSCLES", ("muscle", "muscular", "肌肉")),
    ("NERVES", ("nerve", "nervous", "神经")),
    ("VESSELS", ("vessel", "artery", "arteries", "vein", "veins", "vascular", "血管")),
    ("ORGANS", ("organ", "organs", "viscera", "内脏", "器官")),
    ("HAIR", ("hair", "scalp", "毛发")),
    ("TISSUE", ("fascia", "connective tissue", "tissue", "筋膜", "组织")),
    ("CLOTHING", ("cloth", "clothing", "garment", "衣服", "服装")),
    ("RIG", ("armature", "rig", "skeleton rig", "骨架绑定")),
)


def suggest_category(name):
    normalized = name.casefold()
    matches = [category for category, terms in CATEGORY_RULES
               if any(term.casefold() in normalized for term in terms)]
    return {
        "suggested_category": matches[0] if len(matches) == 1 else None,
        "candidate_categories": matches,
        "status": "suggested_review_required" if len(matches) == 1 else (
            "ambiguous_review_required" if matches else "unclassified_review_required"),
    }


def inspect_blend(path):
    with bpy.data.libraries.load(path, link=True) as (data_from, _data_to):
        result = {
            "file": os.path.basename(path),
            "path": os.path.abspath(path),
            "objects": sorted(data_from.objects),
            "collections": sorted(data_from.collections),
            "meshes": sorted(data_from.meshes),
            "armatures": sorted(data_from.armatures),
            "materials": sorted(data_from.materials),
            "images": sorted(data_from.images),
            "actions": sorted(data_from.actions),
        }
    result["object_suggestions"] = [
        {"object_name": name, **suggest_category(name)} for name in result["objects"]
    ]
    result["notes"] = [
        "Name-based categories are advisory only; review actual geometry before import.",
        "Library datablock names do not prove topology, anatomical correctness, or license.",
        "Source URL, license, and attribution must be verified separately for each source.",
    ]
    return result


def main():
    directory = os.path.abspath(bpy.path.abspath(SOURCE_DIRECTORY)) if SOURCE_DIRECTORY else ""
    if not directory or not os.path.isdir(directory):
        raise RuntimeError("Set SOURCE_DIRECTORY to an existing extracted asset-bundle folder.")
    files = []
    for root, dirs, names in os.walk(directory):
        dirs.sort()
        for name in sorted(names):
            if name.lower().endswith(".blend"):
                files.append(os.path.join(root, name))
    if not files:
        raise RuntimeError("No .blend files found beneath SOURCE_DIRECTORY.")

    entries = []
    failures = []
    for path in files:
        try:
            entries.append(inspect_blend(path))
        except Exception as exc:
            failures.append({"path": os.path.abspath(path), "error": str(exc)})

    report = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "blender_version": bpy.app.version_string,
        "source_directory": directory,
        "files_discovered": len(files),
        "files_inspected": len(entries),
        "files_failed": len(failures),
        "assets": entries,
        "failures": failures,
        "review_required": True,
        "notes": [
            "This is an inventory, not an import operation; no source assets are appended or changed.",
            "A file can contain multiple collections and objects; hierarchy and dependencies need manual review.",
            "Do not auto-import suggested categories without visually checking each asset.",
            "The bundle folder may contain assets with different licenses; verify each asset's own metadata.",
        ],
    }
    output = os.path.abspath(OUTPUT_JSON) if OUTPUT_JSON else os.path.join(
        directory, "realhuman_studio_bundle_inventory.json")
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("REALHUMAN_STUDIO_BUNDLE_INVENTORY: %s" % ("PASS" if not failures else "PARTIAL"))
    print("Files discovered: %d; inspected: %d; failed: %d" %
          (len(files), len(entries), len(failures)))
    print("Output: %s" % output)
    if failures:
        print("Some files could not be read; inspect the failures array before using this report.")


main()
