# -*- coding: utf-8 -*-
"""src/main.py 的自动化测试"""

import datetime
import shutil
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

_MAIN_PATH = Path(__file__).resolve().parent.parent / "src" / "main.py"
if not _MAIN_PATH.exists():
    raise FileNotFoundError("main.py not found: " + str(_MAIN_PATH))

_spec = importlib.util.spec_from_file_location("feed_main", _MAIN_PATH)
feed_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(feed_main)


def task(id, title="t", period=1, offsets=(0,), enabled=True,
         description="", link=""):
    return {
        "id": id,
        "title": title,
        "frequency": {"period": period, "offsets": list(offsets)},
        "enabled": enabled,
        "description": description,
        "link": link,
    }


def sched(tasks, anchor="2026-10-25"):
    return {"anchor": anchor, "tasks": tasks}


def d(s):
    return datetime.date.fromisoformat(s)


class TestDueTasks(unittest.TestCase):
    def test_daily_fires_every_day(self):
        s = sched([task(1)])
        for day in ["2026-10-25", "2026-10-26", "2027-01-01", "2025-01-01"]:
            self.assertEqual(len(feed_main.due_tasks(s, d(day))), 1, day)

    def test_weekly_single(self):
        # 锚点 2026-10-25 是周日
        s = sched([task(1, period=7, offsets=[0])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-01"))), 1)  # 周日
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-02"))), 0)  # 周一

    def test_weekly_multi(self):
        # 周一到周五
        s = sched([task(1, period=7, offsets=[1, 2, 3, 4, 5])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-26"))), 1)  # 周一
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-31"))), 0)  # 周六
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-01"))), 0)  # 周日

    def test_weekend(self):
        s = sched([task(1, period=7, offsets=[6, 0])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-31"))), 1)  # 周六
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-01"))), 1)  # 周日
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-02"))), 0)  # 周一

    def test_period_28(self):
        s = sched([task(1, period=28, offsets=[0])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-25"))), 1)  # 锚点
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-22"))), 1)  # +28
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-11-15"))), 0)  # +21

    def test_disabled(self):
        s = sched([task(1, enabled=False)])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-25"))), 0)

    def test_before_anchor(self):
        # 负数 delta 依赖 Python 正数取模
        s = sched([task(1, period=7, offsets=[4])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-22"))), 1)  # 周四

    def test_invalid_period(self):
        s = sched([task(1, period=0, offsets=[0])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-25"))), 0)

    def test_empty_offsets(self):
        s = sched([task(1, period=7, offsets=[])])
        self.assertEqual(len(feed_main.due_tasks(s, d("2026-10-25"))), 0)


class TestBuildItems(unittest.TestCase):
    def test_guid_unique_per_date(self):
        t = task(1)
        g1 = feed_main.build_items([t], d("2026-10-25"))[0]["guid"]
        g2 = feed_main.build_items([t], d("2026-10-26"))[0]["guid"]
        self.assertNotEqual(g1, g2)

    def test_guid_stable_same_date(self):
        t = task(1)
        today = d("2026-10-25")
        g1 = feed_main.build_items([t], today)[0]["guid"]
        g2 = feed_main.build_items([t], today)[0]["guid"]
        self.assertEqual(g1, g2)

    def test_default_link(self):
        t = task(1, link="")
        items = feed_main.build_items([t], d("2026-10-25"))
        self.assertEqual(items[0]["link"], feed_main.DEFAULT_LINK)

    def test_custom_link(self):
        t = task(1, link="https://example.com/x")
        items = feed_main.build_items([t], d("2026-10-25"))
        self.assertEqual(items[0]["link"], "https://example.com/x")


class TestMergeAndRender(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.feed = self.tmp / "feed.xml"
        self.patcher = mock.patch.object(feed_main, "FEED", self.feed)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_keep_last_5(self):
        today = d("2026-10-25")
        items = feed_main.build_items([task(i) for i in range(1, 7)], today)
        merged = feed_main.merge_with_existing(items, today)
        self.assertEqual(len(merged), 5)

    def test_render_valid_xml(self):
        today = d("2026-10-25")
        items = feed_main.build_items([task(1)], today)
        merged = feed_main.merge_with_existing(items, today)
        xml = feed_main.render_feed(merged, today)
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "rss")

    def test_cdata_injection(self):
        """description 含 ]]> 时 XML 不应损坏"""
        today = d("2026-10-25")
        t = task(1, description="bad ]]> content")
        items = feed_main.build_items([t], today)
        merged = feed_main.merge_with_existing(items, today)
        xml = feed_main.render_feed(merged, today)
        ET.fromstring(xml)

    def test_merge_keeps_old(self):
        today1 = d("2026-10-25")
        today2 = d("2026-10-26")
        items1 = feed_main.build_items([task(1)], today1)
        self.feed.write_text(
            feed_main.render_feed(feed_main.merge_with_existing(items1, today1), today1),
            encoding="utf-8"
        )
        items2 = feed_main.build_items([task(2)], today2)
        merged = feed_main.merge_with_existing(items2, today2)
        self.assertEqual(len(merged), 2)

    def test_corrupt_old_feed_does_not_crash(self):
        self.feed.write_text("<not-xml", encoding="utf-8")
        today = d("2026-10-25")
        items = feed_main.build_items([task(1)], today)
        merged = feed_main.merge_with_existing(items, today)
        self.assertEqual(len(merged), 1)


class TestEndToEnd(unittest.TestCase):
    """从 schedule.yml 到 feed.xml 的全链路"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.schedule = self.tmp / "schedule.yml"
        self.feed = self.tmp / "feed.xml"
        self.patchers = [
            mock.patch.object(feed_main, "SCHEDULE", self.schedule),
            mock.patch.object(feed_main, "FEED", self.feed),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_pipeline(self):
        self.schedule.write_text(
            'anchor: "2026-10-25"\n'
            "tasks:\n"
            "  - id: 1\n"
            "    title: 每天运动\n"
            "    frequency: {period: 1, offsets: [0]}\n"
            "    enabled: true\n"
            '    description: ""\n'
            '    link: ""\n'
            "  - id: 2\n"
            "    title: 每周三洗澡\n"
            "    frequency: {period: 7, offsets: [3]}\n"
            "    enabled: true\n"
            '    description: ""\n'
            '    link: ""\n'
            "  - id: 3\n"
            "    title: 每周日登记\n"
            "    frequency: {period: 7, offsets: [0]}\n"
            "    enabled: true\n"
            '    description: ""\n'
            '    link: ""\n',
            encoding="utf-8",
        )
        # 2026-10-25 是周日：应触发 id=1 和 id=3
        items = feed_main.build(today=d("2026-10-25"))
        ids = sorted(it["id"] for it in items)
        self.assertEqual(ids, [1, 3])

        # 2026-10-28 是周三：应触发 id=1 和 id=2
        items = feed_main.build(today=d("2026-10-28"))
        ids = sorted(it["id"] for it in items)
        self.assertEqual(ids, [1, 2])

        # 2026-10-27 是周二：只触发 id=1
        items = feed_main.build(today=d("2026-10-27"))
        self.assertEqual([it["id"] for it in items], [1])

    def test_empty_schedule(self):
        self.schedule.write_text('anchor: "2026-10-25"\ntasks: []\n', encoding="utf-8")
        items = feed_main.build(today=d("2026-10-25"))
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()