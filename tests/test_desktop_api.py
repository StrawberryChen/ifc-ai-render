import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import app as desktop_api


class DesktopApiTests(unittest.TestCase):
    def test_project_has_real_preview_resources(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(desktop_api, "REVISION_ROOT", Path(folder)):
            response = desktop_api.current_project()
        self.assertTrue(response["source_model_url"].endswith("building.obj"))

    def test_history_is_limited_to_five(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(desktop_api, "REVISION_ROOT", Path(folder)):
            for number in range(7):
                desktop_api.create_prompt_preview(
                    desktop_api.PromptRequest(prompt=f"修改第{number}次场景灯光")
                )
            response = desktop_api.revisions(limit=5)
        self.assertEqual(len(response), 5)


if __name__ == "__main__":
    unittest.main()
