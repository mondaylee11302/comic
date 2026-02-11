from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comic_splitter.workflow import (
    AgentRetryMatrix,
    PanelScriptOptions,
    PanelScriptPaths,
    StoryboardOptions,
    StoryboardPaths,
    load_panel_script_config,
    load_storyboard_config,
)


class WorkflowConfigTests(unittest.TestCase):
    def test_load_storyboard_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "storyboard.toml"
            cfg.write_text(
                """
[paths]
image_path = "/tmp/a.psd"
out_dir = "/tmp/out"
debug_dir = "/tmp/out/debug"
prefix = "p1"

[options]
split_mode = "stage2"
strict_ocr = false
ocr_mode = "multilang"
ocr_lang = "ko"
panel_pad = 12

[retry]
default_max_attempts = 3
default_backoff_sec = 0.1

[retry.per_agent_max_attempts]
split_agent = 4
""",
                encoding="utf-8",
            )
            defaults_paths = StoryboardPaths(
                image_path=Path("/x.psd"),
                out_dir=Path("/x/out"),
                debug_dir=Path("/x/out/debug"),
                prefix="x",
            )
            defaults_opts = StoryboardOptions()
            defaults_retry = AgentRetryMatrix()

            paths, opts, retry = load_storyboard_config(cfg, defaults_paths, defaults_opts, defaults_retry)
            self.assertEqual(str(paths.image_path), "/tmp/a.psd")
            self.assertEqual(str(paths.out_dir), "/tmp/out")
            self.assertEqual(paths.prefix, "p1")
            self.assertEqual(opts.split_mode, "stage2")
            self.assertFalse(opts.strict_ocr)
            self.assertEqual(opts.ocr_mode, "multilang")
            self.assertEqual(opts.ocr_lang, "ko")
            self.assertEqual(opts.panel_pad, 12)
            self.assertEqual(retry.default_max_attempts, 3)
            self.assertEqual(retry.per_agent_max_attempts.get("split_agent"), 4)

    def test_load_panel_script_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "panel_script.toml"
            cfg.write_text(
                """
[paths]
out_dir = "/tmp/out"
prefix = "p2"
panel_id = "panel_005"

[options]
selected_text_ids = ["text_001", "text_003"]
goal = "test goal"
model_retries = 5
allow_local_fallback = false

[retry]
default_max_attempts = 2
[retry.per_agent_max_attempts]
generate_script_agent = 3
""",
                encoding="utf-8",
            )
            defaults_paths = PanelScriptPaths(out_dir=Path("/x/out"), prefix="x", panel_id="panel_001")
            defaults_opts = PanelScriptOptions()
            defaults_retry = AgentRetryMatrix()

            paths, opts, retry = load_panel_script_config(cfg, defaults_paths, defaults_opts, defaults_retry)
            self.assertEqual(str(paths.out_dir), "/tmp/out")
            self.assertEqual(paths.prefix, "p2")
            self.assertEqual(paths.panel_id, "panel_005")
            self.assertEqual(opts.selected_text_ids, ["text_001", "text_003"])
            self.assertEqual(opts.goal, "test goal")
            self.assertEqual(opts.model_retries, 5)
            self.assertFalse(opts.allow_local_fallback)
            self.assertEqual(retry.default_max_attempts, 2)
            self.assertEqual(retry.per_agent_max_attempts.get("generate_script_agent"), 3)


if __name__ == "__main__":
    unittest.main()
