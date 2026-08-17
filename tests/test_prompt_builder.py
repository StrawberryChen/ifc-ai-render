import json
import unittest
from pathlib import Path

from planning.prompt_builder import build_planner_prompt
from planning.scene_planner import build_template_plan


ROOT = Path(__file__).resolve().parents[1]


class PromptBuilderTests(unittest.TestCase):
    def test_prompt_uses_live_tools_assets_and_playbook(self):
        inventory = json.loads((ROOT / "data/examples/campus_scene_inventory.json").read_text())
        brief = json.loads((ROOT / "data/examples/campus_visual_brief.json").read_text())
        prompt = build_planner_prompt(
            inventory,
            brief,
            build_template_plan(inventory, brief),
            json.loads((ROOT / "schemas/blender_tools_v1.json").read_text()),
            json.loads((ROOT / "assets/registry/asset_registry.json").read_text()),
            json.loads((ROOT / "playbooks/architectural_visualization_v1.json").read_text()),
        )
        self.assertIn("camera.update_shot", prompt)
        self.assertIn("tree_deciduous_01", prompt)
        self.assertIn("never emit Python", prompt)


if __name__ == "__main__":
    unittest.main()
