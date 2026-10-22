#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 routine-feed 的 feed.xml。也供 WebUI 预览调用。"""

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


def cdata(text):
    text = "" if text is None else str(text)
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def load_schedule():
    with open(SCHEDULE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def due_tasks(schedule, today):
    anchor = datetime.date.fromisoformat(schedule["anchor"])
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


def build_items(tasks, today):
    items = []
    for task in tasks:
        ts = today.strftime("%Y-%m-%dT%H:%M:%S")
        pub = today.strftime("%a, %d %b %Y %H:%M:%S +0000")
        guid = f"{task['id']}-{ts}"
        title = task.get("title", "")
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
        xml = (
            "<item>\n"
            f"  <title>{cdata(it['title'])}</title>\n"
            f"  <link>{it['link']}</link>\n"
            f"  <description>{cdata(it['description'])}</description>\n"
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
        today = datetime.datetime.utcnow().date()
    schedule = load_schedule()
    tasks = due_tasks(schedule, today)
    return build_items(tasks, today)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, default UTC today")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.date:
        today = datetime.date.fromisoformat(args.date)
    else:
        today = datetime.datetime.utcnow().date()

    schedule = load_schedule()
    tasks = due_tasks(schedule, today)
    items = build_items(tasks, today)
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