import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "planning"))
from plan_editor import PlanEditor, RevisionStore
from scene_planner import build_template_plan


class PlanEditorTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        schema = json.loads((root / "schemas/blender_tools_v1.json").read_text())
        inventory = json.loads((root / "data/examples/campus_scene_inventory.json").read_text())
        brief = json.loads((root / "data/examples/campus_visual_brief.json").read_text())
        self.editor = PlanEditor(schema)
        self.plan = build_template_plan(inventory, brief)

    def test_landscape_patch_is_local(self):
        result = self.editor.apply(self.plan, "landscape.configure", {"tree_density": 0.5})
        self.assertEqual(result["landscape_plan"]["tree_density"], 0.5)
        self.assertNotEqual(self.plan["landscape_plan"]["tree_density"], 0.5)
        self.assertEqual(result["lighting_plan"], self.plan["lighting_plan"])

    def test_out_of_range_value_is_rejected(self):
        with self.assertRaises(ValueError):
            self.editor.apply(self.plan, "landscape.configure", {"tree_density": 2.0})

    def test_revision_store_can_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RevisionStore(Path(directory))
            store.initialize(self.plan)
            edited = self.editor.apply(self.plan, "lighting.set_sun", {"elevation_deg": 20})
            store.commit(edited, "raise sun")
            previous = store.undo()
            self.assertEqual(previous["lighting_plan"]["sun"]["elevation_deg"], 8)


if __name__ == "__main__":
    unittest.main()
