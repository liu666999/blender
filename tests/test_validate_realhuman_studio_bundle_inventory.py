# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the offline bundle inventory validator."""
import copy
import unittest

from validate_realhuman_studio_bundle_inventory import validate


class BundleInventoryValidatorTests(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "schema": "realhuman_studio_blend_bundle_inventory_v1",
            "files_discovered": 1, "files_inspected": 1, "files_failed": 0,
            "assets": [{
                "file": "human.blend", "path": "/assets/human.blend",
                "objects": ["Body"], "collections": ["Human"],
                "meshes": ["BodyMesh"], "armatures": [],
                "materials": ["Skin"], "images": [], "actions": [],
                "object_suggestions": [{
                    "object_name": "Body", "candidate_categories": ["BASE_BODY"],
                    "suggested_category": "BASE_BODY",
                    "status": "suggested_review_required",
                }],
                "notes": ["Name-only suggestion; review required."],
            }],
            "failures": [], "review_required": True, "notes": [],
        }

    def test_accepts_consistent_report(self):
        self.assertEqual(validate(self.valid), [])

    def test_rejects_count_mismatch(self):
        report = copy.deepcopy(self.valid)
        report["files_discovered"] = 2
        self.assertTrue(any("files_discovered must equal" in e for e in validate(report)))

    def test_rejects_duplicate_asset_path(self):
        report = copy.deepcopy(self.valid)
        report["assets"].append(copy.deepcopy(report["assets"][0]))
        report["files_discovered"] = 2
        report["files_inspected"] = 2
        self.assertTrue(any("duplicates asset path" in e for e in validate(report)))

    def test_rejects_missing_object_suggestion(self):
        report = copy.deepcopy(self.valid)
        report["assets"][0]["objects"].append("Head")
        self.assertTrue(any("cover each object exactly once" in e for e in validate(report)))

    def test_rejects_invalid_category_and_status(self):
        report = copy.deepcopy(self.valid)
        item = report["assets"][0]["object_suggestions"][0]
        item["candidate_categories"] = ["NOT_A_CATEGORY"]
        item["suggested_category"] = "NOT_A_CATEGORY"
        self.assertTrue(validate(report))

    def test_requires_human_review(self):
        report = copy.deepcopy(self.valid)
        report["review_required"] = False
        self.assertTrue(any("review_required must be true" in e for e in validate(report)))

    def test_rejects_failure_path_also_listed_as_asset(self):
        report = copy.deepcopy(self.valid)
        report["files_discovered"] = 2
        report["files_failed"] = 1
        report["failures"] = [{"path": "/assets/human.blend", "error": "failed"}]
        self.assertTrue(any("duplicates a path already reported" in e for e in validate(report)))


if __name__ == "__main__":
    unittest.main()
