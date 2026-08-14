import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "inference"))
from generate_sdxl_scene_two_stage import load_config, prepare_environment_mask


class SdxlSceneTwoStageTests(unittest.TestCase):
    def test_repository_config_is_valid(self):
        path = Path(__file__).parents[1] / "configs" / "sdxl_scene_two_stage.json"
        config = load_config(path)
        self.assertEqual(config["inpaint"]["strength"], 0.99)

    def test_protected_white_building_becomes_black(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            image = Image.new("L", (512, 512), 0)
            image.putpixel((256, 256), 255)
            image.save(path)
            result = prepare_environment_mask(path, 512, 512, "cover", True, 0, 0)
            self.assertEqual(result.getpixel((0, 0)), 255)
            self.assertEqual(result.getpixel((256, 256)), 0)

    def test_strength_one_is_rejected(self):
        config = {
            "input": {}, "inpaint": {"strength": 1.0}, "refinement": {},
            "runtime": {}, "output": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
