import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "inference"))
from generate_sdxl_img2img import load_config, prepare_image


class SdxlImg2ImgTests(unittest.TestCase):
    def test_repository_config_is_valid(self):
        path = Path(__file__).parents[1] / "configs" / "sdxl_img2img_baseline.json"
        config = load_config(path)
        self.assertEqual(config["input"]["width"], 1024)
        self.assertEqual(config["inference"]["strengths"], [0.15, 0.25, 0.35])

    def test_invalid_strength_is_rejected(self):
        config = {
            "model": {}, "input": {"width": 1024, "height": 768}, "prompt": "x",
            "inference": {"strengths": [0], "num_inference_steps": 1},
            "runtime": {}, "output": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
