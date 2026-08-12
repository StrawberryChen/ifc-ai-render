import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "inference"))
from run_depth_experiment import load_cases


class DepthExperimentTests(unittest.TestCase):
    def test_load_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps([{"name": "case_1", "seed": 1, "prompt": "x"}]))
            self.assertEqual(load_cases(path)[0]["name"], "case_1")

    def test_duplicate_case_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            case = {"name": "same", "seed": 1, "prompt": "x"}
            path.write_text(json.dumps([case, case]))
            with self.assertRaises(ValueError):
                load_cases(path)


if __name__ == "__main__":
    unittest.main()
