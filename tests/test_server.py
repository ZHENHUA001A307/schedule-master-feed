# -*- coding: utf-8 -*-
"""webui/server.py 的 API 测试（不涉及 git）"""

import http.server
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webui"))
import server as web_server


INITIAL = (
    'anchor: "2026-10-25"\n'
    "tasks:\n"
    "  - id: 1\n"
    "    title: test\n"
    "    frequency: {period: 1, offsets: [0]}\n"
    "    enabled: true\n"
    '    description: ""\n'
    '    link: ""\n'
)


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.schedule = cls.tmp / "schedule.yml"
        cls.patcher = mock.patch.object(web_server, "SCHEDULE", cls.schedule)
        cls.patcher.start()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.patcher.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.schedule.write_text(INITIAL, encoding="utf-8")

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with urllib.request.urlopen(self._url(path)) as r:
            return json.loads(r.read().decode())

    def call(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method=method,
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())

    def test_get_schedule(self):
        cfg = self.get("/api/schedule")
        self.assertEqual(cfg["anchor"], "2026-10-25")
        self.assertEqual(len(cfg["tasks"]), 1)
        self.assertEqual(cfg["tasks"][0]["title"], "test")

    def test_add_task_auto_id(self):
        r = self.call("POST", "/api/task", {
            "title": "new",
            "frequency": {"period": 1, "offsets": [0]},
            "description": "",
            "link": "",
            "enabled": True,
        })
        self.assertTrue(r["ok"])
        self.assertEqual(r["id"], 2)

    def test_add_task_ignores_client_id(self):
        r = self.call("POST", "/api/task", {
            "id": 999,
            "title": "x",
            "frequency": {"period": 1, "offsets": [0]},
            "description": "",
            "link": "",
            "enabled": True,
        })
        self.assertNotEqual(r["id"], 999)

    def test_update_task_title(self):
        self.call("PUT", "/api/task/1", {"title": "updated"})
        cfg = self.get("/api/schedule")
        self.assertEqual(cfg["tasks"][0]["title"], "updated")

    def test_update_task_frequency(self):
        self.call("PUT", "/api/task/1", {
            "frequency": {"period": 7, "offsets": [3]}
        })
        cfg = self.get("/api/schedule")
        self.assertEqual(cfg["tasks"][0]["frequency"]["period"], 7)
        self.assertEqual(cfg["tasks"][0]["frequency"]["offsets"], [3])

    def test_delete_task(self):
        self.call("POST", "/api/task", {
            "title": "to delete",
            "frequency": {"period": 1, "offsets": [0]},
            "description": "",
            "link": "",
            "enabled": True,
        })
        self.call("DELETE", "/api/task/2")
        cfg = self.get("/api/schedule")
        self.assertFalse(any(t["id"] == 2 for t in cfg["tasks"]))

    def test_anchor_update(self):
        self.call("POST", "/api/schedule/anchor", {"anchor": "2027-01-03"})
        cfg = self.get("/api/schedule")
        self.assertEqual(cfg["anchor"], "2027-01-03")

    def test_multiline_description_roundtrip(self):
        text = "第一行\n第二行\n第三行"
        self.call("PUT", "/api/task/1", {"description": text})
        cfg = self.get("/api/schedule")
        self.assertEqual(cfg["tasks"][0]["description"], text)

    def test_delete_then_new_reuses_max(self):
        # 删除 id=1 后，新任务 id 应为 1
        self.call("DELETE", "/api/task/1")
        r = self.call("POST", "/api/task", {
            "title": "again",
            "frequency": {"period": 1, "offsets": [0]},
            "description": "",
            "link": "",
            "enabled": True,
        })
        self.assertEqual(r["id"], 1)


if __name__ == "__main__":
    unittest.main()