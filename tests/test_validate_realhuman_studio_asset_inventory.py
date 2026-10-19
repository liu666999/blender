# SPDX-FileCopyrightText: 2026 RealHuman Studio contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the offline asset inventory report validator."""
import copy
import unittest

from validate_realhuman_studio_asset_inventory import validate


class AssetInventoryValidatorTests(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "schema": "realhuman_studio_blend_library_inventory_v1",
            "objects": ["Body"],
            "collections": [], "meshes": ["BodyMesh"], "armatures": [],
            "materials": [], "images": [], "actions": [], "curves": [],
            "category_suggestions": [{
                "object_name": "Body",
                "candidate_categories": ["BASE_BODY"],
                "suggested_category": "BASE_BODY",
                "status": "suggested_review_required",
            }],
            "category_map_draft": {"Body": "BASE_BODY"},
            "category_map_draft_review_required": True,
        }

    def test_accepts_valid_report_but_marks_draft_for_review(self):
        self.assertEqual(validate(self.valid), [])

    def test_rejects_duplicate_object_names(self):
        report = copy.deepcopy(self.valid)
        report["objects"] = ["Body", "Body"]
        self.assertTrue(any("objects contains duplicate names" in e for e in validate(report)))

    def test_rejects_draft_for_unknown_object(self):
        report = copy.deepcopy(self.valid)
        report["category_map_draft"]["Unknown"] = "SKIN"
        errors = validate(report)
        self.assertTrue(any("draft references unknown object" in e for e in errors))
        self.assertTrue(any("draft entry is not a unique suggestion" in e for e in errors))

    def test_rejects_ambiguous_mapping_draft(self):
        report = copy.deepcopy(self.valid)
        report["category_suggestions"][0]["candidate_categories"] = ["BASE_BODY", "SKIN"]
        report["category_suggestions"][0]["suggested_category"] = None
        report["category_suggestions"][0]["status"] = "ambiguous_review_required"
        self.assertTrue(any("draft entry is not a unique suggestion" in e for e in validate(report)))

    def test_malformed_suggestion_key_does_not_crash(self):
        report = copy.deepcopy(self.valid)
        report["category_suggestions"].append({
            "object_name": ["unhashable"], "candidate_categories": None,
            "suggested_category": None, "status": "unclassified_review_required",
        })
        self.assertTrue(validate(report))

    def test_rejects_missing_review_flag(self):
        report = copy.deepcopy(self.valid)
        report["category_map_draft_review_required"] = False
        self.assertTrue(any("category_map_draft_review_required must be true" in e for e in validate(report)))


if __name__ == "__main__":
    unittest.main()
