import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "semantic"))
from semantic_mapper import map_inventory, score_object


class SemanticMapperTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.rules = json.loads((root / "configs/semantic_mapping_rules.json").read_text())

    def test_chinese_material_maps_green_area(self):
        obj = {"name": "Group_1", "materials": ["校园绿地"], "collections": [], "dimensions": [20, 15, 0.1]}
        semantic_type, confidence, _, _ = score_object(obj, self.rules)
        self.assertEqual(semantic_type, "green_area")
        self.assertGreaterEqual(confidence, 0.25)

    def test_project_override_is_confirmed(self):
        raw = {
            "raw_schema_version": "1.0",
            "project": {"id": "x"},
            "objects": [{
                "source_id": "Object", "suggested_id": "object", "name": "Object",
                "materials": [], "collections": [], "dimensions": [1, 1, 1],
            }],
        }
        manifest = map_inventory(raw, self.rules, {"object_mapping": {"Object": "building"}})
        self.assertEqual(manifest["objects"][0]["type"], "building")
        self.assertEqual(manifest["objects"][0]["mapping_status"], "confirmed")

    def test_ambiguous_object_requires_confirmation(self):
        raw = {
            "raw_schema_version": "1.0",
            "project": {"id": "x"},
            "objects": [{
                "source_id": "Cube.001", "suggested_id": "cube_001", "name": "Cube.001",
                "materials": ["Material"], "collections": ["Collection"], "dimensions": [2, 2, 2],
            }],
        }
        manifest = map_inventory(raw, self.rules, {})
        self.assertEqual(manifest["objects"][0]["type"], "unknown")
        self.assertEqual(manifest["mapping_summary"]["needs_confirmation"], 1)


if __name__ == "__main__":
    unittest.main()
