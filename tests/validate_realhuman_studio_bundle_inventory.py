# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline structural validator for a Blender bundle inventory JSON report.

Usage:
    python tests/validate_realhuman_studio_bundle_inventory.py report.json

This checks report consistency only; it cannot establish anatomy, geometry quality,
source authenticity, or license permission.
"""
import json
import sys
from pathlib import Path

SCHEMA = "realhuman_studio_blend_bundle_inventory_v1"
ALLOWED_CATEGORIES = {
    "BASE_BODY", "SKIN", "FAT", "BONES", "MUSCLES", "NERVES",
    "VESSELS", "ORGANS", "HAIR", "TISSUE", "CLOTHING", "RIG",
}
ASSET_LIST_FIELDS = (
    "objects", "collections", "meshes", "armatures",
    "materials", "images", "actions",
)


def validate(report):
    errors = []
    if not isinstance(report, dict):
        return ["root must be a JSON object"]
    if report.get("schema") != SCHEMA:
        errors.append("unexpected or missing schema")
    for field in ("files_discovered", "files_inspected", "files_failed"):
        value = report.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append("%s must be a non-negative integer" % field)
    assets = report.get("assets")
    failures = report.get("failures")
    if not isinstance(assets, list):
        errors.append("assets must be an array")
        assets = []
    if not isinstance(failures, list):
        errors.append("failures must be an array")
        failures = []
    if all(isinstance(report.get(k), int) and not isinstance(report.get(k), bool)
           and report[k] >= 0 for k in ("files_discovered", "files_inspected", "files_failed")):
        if report["files_inspected"] != len(assets):
            errors.append("files_inspected does not match assets length")
        if report["files_failed"] != len(failures):
            errors.append("files_failed does not match failures length")
        if report["files_discovered"] != report["files_inspected"] + report["files_failed"]:
            errors.append("files_discovered must equal inspected plus failed")
    if report.get("review_required") is not True:
        errors.append("review_required must be true")

    seen_files = set()
    for index, asset in enumerate(assets):
        prefix = "assets[%d]" % index
        if not isinstance(asset, dict):
            errors.append(prefix + " must be an object")
            continue
        filename, path = asset.get("file"), asset.get("path")
        if not isinstance(filename, str) or not filename.lower().endswith(".blend"):
            errors.append(prefix + " file must be a .blend filename")
        if not isinstance(path, str) or not path:
            errors.append(prefix + " path must be a non-empty string")
        elif path in seen_files:
            errors.append(prefix + " duplicates asset path: " + path)
        else:
            seen_files.add(path)
        object_names = asset.get("objects")
        if not isinstance(object_names, list) or any(not isinstance(v, str) for v in object_names):
            errors.append(prefix + " objects must be an array of strings")
            object_names = []
        elif len(object_names) != len(set(object_names)):
            errors.append(prefix + " objects contains duplicate names")
        for field in ASSET_LIST_FIELDS:
            values = asset.get(field)
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                errors.append(prefix + " %s must be an array of strings" % field)
            elif len(values) != len(set(values)):
                errors.append(prefix + " %s contains duplicate names" % field)
        suggestions = asset.get("object_suggestions")
        if not isinstance(suggestions, list):
            errors.append(prefix + " object_suggestions must be an array")
            continue
        seen_suggestions = set()
        for si, item in enumerate(suggestions):
            sp = "%s object_suggestions[%d]" % (prefix, si)
            if not isinstance(item, dict):
                errors.append(sp + " must be an object")
                continue
            name = item.get("object_name")
            if not isinstance(name, str) or name not in object_names:
                errors.append(sp + " references an unknown object")
            elif name in seen_suggestions:
                errors.append(sp + " duplicates object suggestion: " + name)
            else:
                seen_suggestions.add(name)
            candidates = item.get("candidate_categories")
            if not isinstance(candidates, list) or any(
                not isinstance(c, str) or c not in ALLOWED_CATEGORIES for c in candidates
            ) or len(candidates) != len(set(candidates)):
                errors.append(sp + " has invalid candidate_categories")
                candidates = []
            suggested = item.get("suggested_category")
            if suggested is not None and (
                not isinstance(suggested, str) or suggested not in ALLOWED_CATEGORIES
                or len(candidates) != 1 or candidates[0] != suggested
            ):
                errors.append(sp + " suggested_category must be the sole candidate")
            expected = ("suggested_review_required" if len(candidates) == 1 else
                        "ambiguous_review_required" if candidates else
                        "unclassified_review_required")
            if item.get("status") != expected:
                errors.append(sp + " status does not match candidate count")
        if seen_suggestions != set(object_names):
            errors.append(prefix + " object_suggestions must cover each object exactly once")

    seen_failure_paths = set()
    for index, failure in enumerate(failures):
        prefix = "failures[%d]" % index
        if not isinstance(failure, dict):
            errors.append(prefix + " must be an object")
            continue
        path, error = failure.get("path"), failure.get("error")
        if not isinstance(path, str) or not path:
            errors.append(prefix + " path must be a non-empty string")
        elif path in seen_failure_paths or path in seen_files:
            errors.append(prefix + " duplicates a path already reported")
        else:
            seen_failure_paths.add(path)
        if not isinstance(error, str) or not error:
            errors.append(prefix + " error must be a non-empty string")
    return errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python tests/validate_realhuman_studio_bundle_inventory.py <inventory.json>", file=sys.stderr)
        return 2
    try:
        report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("BUNDLE_INVENTORY_VALIDATION: FAIL - cannot read JSON: %s" % exc)
        return 1
    errors = validate(report)
    if errors:
        print("BUNDLE_INVENTORY_VALIDATION: FAIL")
        for error in errors:
            print("- " + error)
        return 1
    print("BUNDLE_INVENTORY_VALIDATION: PASS")
    print("Discovered: %d; inspected: %d; failed: %d" % (
        report["files_discovered"], report["files_inspected"], report["files_failed"]))
    print("Note: structural validation only; anatomy, quality, and licenses need separate review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
