import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "inference"))
from generate_sdxl_img2img import load_config, prepare_control_image, prepare_image


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

    def test_canny_config_is_valid(self):
        path = Path(__file__).parents[1] / "configs" / "sdxl_canny_img2img.json"
        config = load_config(path)
        self.assertEqual(config["controlnet"]["model_id"], "diffusers/controlnet-canny-sdxl-1.0")
        self.assertEqual(config["controlnet"]["conditioning_scale"], 0.7)
        self.assertTrue(config["controlnet"]["invert_image"])

    def test_control_image_can_be_inverted(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edge.png"
            Image.new("RGB", (512, 512), "white").save(path)
            result = prepare_control_image(path, 512, 512, "cover", invert=True)
            self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))

    def test_invalid_control_guidance_is_rejected(self):
        config = {
            "model": {}, "input": {"width": 1024, "height": 768}, "prompt": "x",
            "inference": {"strengths": [0.4], "num_inference_steps": 1},
            "runtime": {}, "output": {},
            "controlnet": {"model_id": "x", "image": "x.png", "guidance_start": 0.9, "guidance_end": 0.2},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
