import argparse
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "inference"))
from generate_flux_depth_api import build_arguments, prepare_fal_depth


class FluxDepthApiTests(unittest.TestCase):
    def test_prepare_depth_keeps_background_and_inverts_distance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "control.png"
            image = Image.new("I;16", (2, 2))
            image.putdata([0, 100, 200, 300])
            image.save(source)
            result = prepare_fal_depth(source, output, invert=True)
            self.assertEqual(list(result.get_flattened_data()), [0, 255, 128, 0])

    def test_api_disables_server_depth_preprocessing(self):
        args = argparse.Namespace(
            prompt="test", control_strength=1.0, width=1024, height=768,
            steps=28, guidance=3.5, seed=7,
        )
        payload = build_arguments(args, "https://example.com/depth.png")
        self.assertFalse(payload["preprocess_depth"])
        self.assertEqual(payload["image_size"], {"width": 1024, "height": 768})


if __name__ == "__main__":
    unittest.main()
