#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 生成 routine-feed 的 feed.xml。也供 WebUI 预览调用。

import argparse
import datetime
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEDULE = PROJECT_ROOT / "config" / "schedule.yml"
FEED = PROJECT_ROOT / "feed.xml"
KEEP = 5
REPO = os.environ.get("GITHUB_REPOSITORY", "unknown/repo")
DEFAULT_LINK = f"https://github.com/{REPO}"

WEEKDAY_NAMES = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]


def cdata(text):
    text = "" if text is None else str(text)
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def load_schedule():
    with open(SCHEDULE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_counter(schedule, today):
    """返回 (day, week, month, day_in_month, weekday_offset)。

    weekday_offset: 0=周日, 1=周一, ..., 6=周六

    校准优先：counter_override = {date, day, week}
             date 是校准日，day 是那天第几天，week 是那天第几周。
             周的基准是 date 所在周的周日（自动反推）。

    没校准时：anchor 是第 1 天，day=(today-anchor)+1。
    """
    override = schedule.get("counter_override")
    if override and override.get("date"):
        base_date = datetime.date.fromisoformat(str(override["date"]))
        base_day = int(override["day"])
        base_week = int(override["week"])

        # base_date 所在周的周日（周日=0）
        base_offset = (base_date.weekday() + 1) % 7
        base_sunday = base_date - datetime.timedelta(days=base_offset)

        day = base_day + (today - base_date).days

        sunday_delta = (today - base_sunday).days
        week_delta = sunday_delta // 7
        week = base_week + week_delta
        weekday_offset = sunday_delta % 7
    else:
        anchor = datetime.date.fromisoformat(str(schedule["anchor"]))
        day = (today - anchor).days + 1
        week = (day - 1) // 7 + 1
        weekday_offset = (today.weekday() + 1) % 7

    month = (week - 1) // 4 + 1
    week_in_month = (week - 1) % 4
    day_in_month = week_in_month * 7 + weekday_offset + 1

    return day, week, month, day_in_month, weekday_offset


def format_title(task, today, schedule):
    day, week, month, day_in_month, weekday_offset = get_counter(schedule, today)
    freq = task.get("frequency", {})
    period = int(freq.get("period", 1))
    title = task.get("title", "")
    if period == 7:
        return f"{week:03d}周 - {weekday_offset} - {title}"
    if period == 28:
        return f"{month:03d}月 - {day_in_month:02d} - {title}"
    return f"{day:03d}日 - {title}"


def due_tasks(schedule, today):
    anchor = datetime.date.fromisoformat(str(schedule["anchor"]))
    delta = (today - anchor).days
    out = []
    for task in schedule.get("tasks", []):
        if not task.get("enabled", True):
            continue
        freq = task.get("frequency", {})
        period = int(freq.get("period", 1))
        offsets = freq.get("offsets", [0])
        if period <= 0 or not offsets:
            continue
        if delta % period in offsets:
            out.append(task)
    return out


def build_items(tasks, today, schedule=None):
    if schedule is None:
        schedule = {"anchor": today.isoformat()}
    items = []
    for task in tasks:
        ts = today.strftime("%Y-%m-%dT%H:%M:%S")
        pub = today.strftime("%a, %d %b %Y %H:%M:%S +0000")
        guid = f"{task['id']}-{ts}"
        title = format_title(task, today, schedule)
        link = task.get("link", "") or DEFAULT_LINK
        desc = task.get("description", "") or ""
        items.append({
            "id": task["id"],
            "title": title,
            "link": link,
            "description": desc,
            "guid": guid,
            "pubDate": pub,
        })
    return items


def merge_with_existing(items, today):
    existing = []
    if FEED.exists():
        try:
            root = ET.parse(FEED).getroot()
            for it in root.findall("./channel/item"):
                pub = it.findtext("pubDate") or ""
                existing.append((pub, ET.tostring(it, encoding="unicode")))
        except Exception as e:
            print(f"[warn] parse old feed failed: {e}", file=sys.stderr)
    pub = today.strftime("%a, %d %b %Y %H:%M:%S +0000")
    for it in items:
        desc_html = (it['description'] or '').replace('\n', '<br>')
        xml = (
            "<item>\n"
            f"  <title>{cdata(it['title'])}</title>\n"
            f"  <link>{it['link']}</link>\n"
            f"  <description>{cdata(desc_html)}</description>\n"
            f'  <guid isPermaLink="false">{it["guid"]}</guid>\n'
            f"  <pubDate>{it['pubDate']}</pubDate>\n"
            "</item>"
        )
        existing.append((pub, xml))
    existing.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in existing[:KEEP]]


def render_feed(item_xmls, today):
    pub = today.strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "<channel>\n"
        "<title>内务提醒</title>\n"
        f"<link>{DEFAULT_LINK}</link>\n"
        "<description>日常内务循环提醒</description>\n"
        f"<lastBuildDate>{pub}</lastBuildDate>\n"
        + "\n".join(item_xmls) +
        "\n</channel>\n</rss>\n"
    )


def build(today=None):
    if today is None:
        today = datetime.datetime.now(datetime.timezone.utc).date()
    schedule = load_schedule()
    tasks = due_tasks(schedule, today)
    return build_items(tasks, today, schedule)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, default UTC today")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.date:
        today = datetime.date.fromisoformat(args.date)
    else:
        today = datetime.datetime.now(datetime.timezone.utc).date()

    schedule = load_schedule()
    tasks = due_tasks(schedule, today)
    items = build_items(tasks, today, schedule)
    for it in items:
        print(f"due: {it['id']} {it['title']}")

    if not items and FEED.exists() and not args.dry_run:
        print("no due task today, feed unchanged")
        return

    item_xmls = merge_with_existing(items, today)
    xml = render_feed(item_xmls, today)

    if args.dry_run:
        print(xml)
        return

    FEED.write_text(xml, encoding="utf-8")
    print(f"wrote {FEED} ({len(item_xmls)} items)")


if __name__ == "__main__":
    main()
