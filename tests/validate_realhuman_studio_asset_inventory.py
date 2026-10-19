# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate a JSON report produced by realhuman_studio_asset_inventory.py.

Run with standard Python (no Blender required):
    python tests/validate_realhuman_studio_asset_inventory.py path/to/realhuman_studio_asset_inventory.json
This validates report structure and safe mapping-draft invariants; it does not
validate anatomical correctness or replace review of the source asset.
"""
import json
import sys
from pathlib import Path

SCHEMA = "realhuman_studio_blend_library_inventory_v1"
ALLOWED_CATEGORIES = {
    "BASE_BODY", "SKIN", "FAT", "BONES", "MUSCLES", "NERVES",
    "VESSELS", "ORGANS", "HAIR", "TISSUE", "CLOTHING", "RIG",
}
LIST_FIELDS = ("objects", "collections", "meshes", "armatures", "materials", "images", "actions", "curves")


def validate(report):
    errors = []
    if not isinstance(report, dict):
        return ["root must be a JSON object"]
    if report.get("schema") != SCHEMA:
        errors.append("unexpected or missing schema")
    for field in LIST_FIELDS:
        values = report.get(field)
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            errors.append("%s must be an array of strings" % field)
        elif len(values) != len(set(values)):
            errors.append("%s contains duplicate names" % field)
    objects = report.get("objects", [])
    if not isinstance(objects, list):
        objects = []
    object_names = set(v for v in objects if isinstance(v, str))
    suggestions = report.get("category_suggestions")
    if not isinstance(suggestions, list):
        errors.append("category_suggestions must be an array")
        suggestions = []
    seen = set()
    for index, item in enumerate(suggestions):
        prefix = "category_suggestions[%d]" % index
        if not isinstance(item, dict):
            errors.append(prefix + " must be an object")
            continue
        name = item.get("object_name")
        candidates = item.get("candidate_categories")
        suggested = item.get("suggested_category")
        status = item.get("status")
        if not isinstance(name, str) or name not in object_names:
            errors.append(prefix + " references an unknown object")
        elif name in seen:
            errors.append(prefix + " duplicates object suggestion: " + name)
        else:
            seen.add(name)
        if not isinstance(candidates, list) or any(not isinstance(c, str) or c not in ALLOWED_CATEGORIES for c in candidates):
            errors.append(prefix + " has invalid candidate_categories")
            candidates = []
        if suggested is not None and (not isinstance(suggested, str) or suggested not in ALLOWED_CATEGORIES or len(candidates) != 1 or candidates[0] != suggested):
            errors.append(prefix + " suggested_category must be the sole candidate")
        expected = "suggested_review_required" if len(candidates) == 1 else ("ambiguous_review_required" if candidates else "unclassified_review_required")
        if status != expected:
            errors.append(prefix + " status does not match candidate count")
    if suggestions and seen != object_names:
        errors.append("category_suggestions must contain exactly one entry per source object")
    draft = report.get("category_map_draft")
    if not isinstance(draft, dict):
        errors.append("category_map_draft must be a JSON object")
        draft = {}
    if report.get("category_map_draft_review_required") is not True:
        errors.append("category_map_draft_review_required must be true")
    suggestion_by_name = {i.get("object_name"): i for i in suggestions if isinstance(i, dict)}
    for name, category in draft.items():
        item = suggestion_by_name.get(name)
        if name not in object_names:
            errors.append("draft references unknown object: " + str(name))
        if not isinstance(category, str) or category not in ALLOWED_CATEGORIES:
            errors.append("draft contains invalid category for: " + str(name))
        if not item or item.get("suggested_category") != category or len(item.get("candidate_categories", [])) != 1:
            errors.append("draft entry is not a unique suggestion: " + str(name))
    return errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python tests/validate_realhuman_studio_asset_inventory.py <inventory.json>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("ASSET_INVENTORY_VALIDATION: FAIL - cannot read JSON: %s" % exc)
        return 1
    errors = validate(report)
    if errors:
        print("ASSET_INVENTORY_VALIDATION: FAIL")
        for error in errors:
            print("- " + error)
        return 1
    print("ASSET_INVENTORY_VALIDATION: PASS")
    print("Objects: %d; reviewed draft entries: %d" % (len(report["objects"]), len(report["category_map_draft"])))
    print("Note: structural validation only; anatomical correctness still requires human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
