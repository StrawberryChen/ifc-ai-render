import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from validate_asset_registry import validate


class AssetRegistryTests(unittest.TestCase):
    def test_core_registry_and_preset_are_valid(self):
        root = Path(__file__).parents[1]
        summary = validate(
            root / "assets/registry/asset_registry.json",
            [root / "assets/presets/campus_northeast_china.json"],
        )
        self.assertEqual(summary["assets"], 10)
        self.assertEqual(summary["licenses"], 1)


if __name__ == "__main__":
    unittest.main()
