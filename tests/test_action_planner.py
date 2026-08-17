import json
import unittest
from pathlib import Path

from planning.action_planner import plan_actions


ROOT = Path(__file__).resolve().parents[1]


class ActionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / "outputs/planning/sdcc.landscape_demo.plan.json").read_text())
        self.schema = json.loads((ROOT / "schemas/blender_tools_v1.json").read_text())

    def test_local_fallback_can_reduce_tree_density(self):
        actions, planner = plan_actions("降低入口前乔木密度", self.plan, self.schema, api_key="")
        self.assertEqual(planner, "local-rules-fallback")
        self.assertEqual(actions[0]["tool_id"], "landscape.configure")
        self.assertLess(actions[0]["parameters"]["tree_density"], 0.32)

    def test_local_fallback_can_build_blue_hour_lighting(self):
        actions, _ = plan_actions("改为黄昏蓝紫色天空", self.plan, self.schema, api_key="")
        self.assertEqual({action["tool_id"] for action in actions}, {"lighting.set_sun", "lighting.set_world"})


if __name__ == "__main__":
    unittest.main()
