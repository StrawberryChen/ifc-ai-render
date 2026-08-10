import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))
from inference.generate_qwen_depth import prepare_depth, valid_resolution


class GenerateQwenDepthTests(unittest.TestCase):
    def test_resolution_validation(self):
        self.assertEqual(valid_resolution("768"), 768)
        with self.assertRaises(Exception):
            valid_resolution("770")

    def test_prepare_16_bit_depth(self):
        path = Path(self.id().replace(".", "_") + ".png")
        try:
            image = Image.new("I;16", (2, 2))
            image.putdata([0, 1000, 2000, 3000])
            image.save(path)
            result = prepare_depth(path, 256, 256)
            self.assertEqual(result.mode, "RGB")
            self.assertEqual(result.size, (256, 256))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
