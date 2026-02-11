from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from comic_splitter.ui.react_api import create_react_workbench_app


class TestReactWorkbenchApi(unittest.TestCase):
    def test_health_and_assets_and_panel_details(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            static = root / "static"
            static.mkdir(parents=True, exist_ok=True)
            (static / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")

            out_dir = root / "output"
            out_dir.mkdir(parents=True, exist_ok=True)

            panel_dir = out_dir / "demo_panels"
            panel_dir.mkdir(parents=True, exist_ok=True)
            panel_png = panel_dir / "panel_001.png"
            panel_png.write_bytes(b"png")
            panel_txt = panel_dir / "panel_001.txt"
            panel_txt.write_text(
                json.dumps(
                    {
                        "text_id": "text_001",
                        "text": "hello",
                        "panel_rel_bbox": [1, 2, 3, 4],
                        "assignment_score": 0.9,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            panel_script_md = panel_dir / "panel_001_script.md"
            panel_script_md.write_text("# test script", encoding="utf-8")

            (out_dir / "demo_panels_manifest.json").write_text(
                json.dumps(
                    {
                        "panels": [
                            {
                                "panel_id": "panel_001",
                                "bbox": [0, 0, 100, 100],
                                "bbox_path": str(panel_png),
                                "txt_path": str(panel_txt),
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (out_dir / "demo_panel_text_manifest.json").write_text(
                json.dumps([{"panel_id": "panel_001", "text_count": 1}], ensure_ascii=False),
                encoding="utf-8",
            )
            source_psd = out_dir / "source.psd"
            source_psd.write_bytes(b"psd")
            (out_dir / "demo_pipeline_meta.json").write_text(
                json.dumps({"image": str(source_psd)}, ensure_ascii=False),
                encoding="utf-8",
            )

            app = create_react_workbench_app(
                static_dir=static,
                default_out_dir=out_dir,
                default_debug_dir=out_dir / "debug",
            )
            client = TestClient(app)

            resp = client.get("/api/health")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json().get("ok"), True)

            resp = client.get(
                "/api/assets/list",
                params={"out_dir": str(out_dir), "prefix_filter": "demo", "asset_type": "all"},
            )
            self.assertEqual(resp.status_code, 200)
            payload = resp.json()
            self.assertEqual(payload.get("ok"), True)
            self.assertGreaterEqual(len(payload.get("items", [])), 3)

            resp = client.get(
                "/api/panel/details",
                params={"out_dir": str(out_dir), "prefix": "demo", "panel_id": "panel_001"},
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["panel"]["panel_id"], "panel_001")
            self.assertEqual(len(body["texts"]), 1)

            resp = client.get("/api/script/preview", params={"path": str(panel_script_md)})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("test script", resp.json().get("content", ""))

            resp = client.get("/api/file", params={"path": str(panel_png)})
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
