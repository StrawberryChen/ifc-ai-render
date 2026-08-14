import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "planning"))
from scene_planner import build_chat_payload, build_template_plan, validate_inventory, validate_plan


class ScenePlannerTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        self.inventory = json.loads((root / "data/examples/campus_scene_inventory.json").read_text())
        self.brief = json.loads((root / "data/examples/campus_visual_brief.json").read_text())

    def test_template_plan_is_valid(self):
        validate_inventory(self.inventory)
        plan = build_template_plan(self.inventory, self.brief)
        validate_plan(plan, self.inventory)
        self.assertEqual(plan["lighting_plan"]["preset"], "blue_hour")
        self.assertIn("green_zones", plan["landscape_plan"]["target_ids"])

    def test_unknown_material_target_is_rejected(self):
        plan = build_template_plan(self.inventory, self.brief)
        plan["material_plan"]["assignments"][0]["target_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_plan(plan, self.inventory)

    def test_duplicate_ids_are_rejected(self):
        self.inventory["objects"].append(dict(self.inventory["objects"][0]))
        with self.assertRaises(ValueError):
            validate_inventory(self.inventory)

    def test_deepseek_payload_requests_json_and_disables_thinking(self):
        payload = build_chat_payload("deepseek-v4-flash", "plan", "disabled")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})


if __name__ == "__main__":
    unittest.main()
