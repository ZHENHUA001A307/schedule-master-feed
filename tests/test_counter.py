# -*- coding: utf-8 -*-
"""编号格式测试"""

import datetime
import importlib.util
import unittest
from pathlib import Path

_MAIN_PATH = Path(__file__).resolve().parent.parent / "src" / "main.py"
_spec = importlib.util.spec_from_file_location("feed_main", _MAIN_PATH)
feed_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(feed_main)


def task(period, title="T"):
    return {"id": 1, "title": title,
            "frequency": {"period": period, "offsets": [0]},
            "enabled": True}


def sched(anchor="2026-10-25", override=None):
    s = {"anchor": anchor, "tasks": []}
    if override:
        s["counter_override"] = override
    return s


def d(s):
    return datetime.date.fromisoformat(s)


class TestCounterNoOverride(unittest.TestCase):
    def test_daily_day_1(self):
        s = sched()
        self.assertEqual(feed_main.format_title(task(1), d("2026-10-25"), s), "001日 - T")

    def test_daily_day_4(self):
        s = sched()
        self.assertEqual(feed_main.format_title(task(1), d("2026-10-28"), s), "004日 - T")

    def test_weekly_wed(self):
        s = sched()
        self.assertEqual(feed_main.format_title(task(7), d("2026-10-28"), s), "001周 - 3 - T")

    def test_weekly_sun(self):
        s = sched()
        self.assertEqual(feed_main.format_title(task(7), d("2026-10-25"), s), "001周 - 0 - T")


class TestCounterOverride(unittest.TestCase):
    """校准：2026-10-22（周四）= 第 295 天 / 第 43 周。
    base_sunday = 2026-10-18（周日）。
    """

    def ov(self):
        return {"date": "2026-10-22", "day": 295, "week": 43}

    def test_same_day(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-22"))
        self.assertEqual((day, week, wd, month, dim), (295, 43, 4, 11, 19))

    def test_next_sunday(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-25"))
        self.assertEqual((day, week, wd, month, dim), (298, 44, 0, 11, 22))

    def test_next_monday(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-26"))
        self.assertEqual((day, week, wd, month, dim), (299, 44, 1, 11, 23))

    def test_saturday_same_week(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-24"))
        self.assertEqual((day, week, wd, month, dim), (297, 43, 6, 11, 21))

    def test_base_sunday(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-18"))
        self.assertEqual((day, week, wd, month), (291, 43, 0, 11))

    def test_previous_week(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-10-11"))
        self.assertEqual((day, week, wd, month, dim), (284, 42, 0, 11, 8))

    def test_crosses_month(self):
        s = sched(override=self.ov())
        day, week, month, dim, wd = feed_main.get_counter(s, d("2026-11-15"))
        self.assertEqual(week, 47)
        self.assertEqual(month, 12)
        self.assertEqual(wd, 0)
        self.assertEqual(dim, 15)

    def test_format_weekly(self):
        s = sched(override=self.ov())
        self.assertEqual(feed_main.format_title(task(7), d("2026-10-22"), s), "043周 - 4 - T")

    def test_format_monthly(self):
        s = sched(override=self.ov())
        self.assertEqual(feed_main.format_title(task(28), d("2026-10-22"), s), "011月 - 19 - T")

    def test_format_daily(self):
        s = sched(override=self.ov())
        self.assertEqual(feed_main.format_title(task(1), d("2026-10-22"), s), "295日 - T")


if __name__ == "__main__":
    unittest.main()
