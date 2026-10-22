#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schedule Master Feed - WebUI backend (port 8766)"""

import datetime
import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEDULE = PROJECT_ROOT / "config" / "schedule.yml"
HOST = "127.0.0.1"
PORT = 8766

_lock = threading.Lock()


def read_schedule():
    with open(SCHEDULE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_schedule(cfg):
    SCHEDULE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def next_id(tasks):
    return max((int(t.get("id", 0)) for t in tasks), default=0) + 1


def git(args, timeout=60):
    r = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT)] + args,
        capture_output=True, text=True, timeout=timeout
    )
    return r.returncode == 0, r.stdout, r.stderr


def git_status():
    dirty_out = git(["status", "--porcelain"])[1]
    ahead_out = git(["rev-list", "--count", "@{u}..HEAD"])[1]
    dirty = len([l for l in dirty_out.splitlines() if l.strip()])
    ahead = int(ahead_out.strip()) if ahead_out.strip().isdigit() else 0
    return {"dirty": dirty, "ahead": ahead}


def git_commit_push(msg):
    ok, out, err = git(["add", "config/schedule.yml", "feed.xml"])
    if not ok:
        return False, err
    ok, out, err = git(["commit", "-m", msg])
    if not ok and "nothing to commit" not in (out + err):
        return False, err
    ok, out, err = git(["push"])
    return ok, out + err


def get_counter_today():
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import main as feed_main
    today = datetime.datetime.utcnow().date()
    schedule = read_schedule()
    day, week, month, day_in_month, weekday_offset = feed_main.get_counter(schedule, today)
    return {
        "date": today.isoformat(),
        "day": day,
        "week": week,
        "month": month,
        "day_in_month": day_in_month,
        "weekday_offset": weekday_offset,
        "weekday_name": feed_main.WEEKDAY_NAMES[weekday_offset],
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _read_body(self):
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n).decode("utf-8") if n else ""

    def _parts(self):
        return [p for p in urllib.parse.urlparse(self.path).path.split("/") if p]

    def do_GET(self):
        parts = self._parts()

        if not parts:
            html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return

        if parts == ["api", "schedule"]:
            self._json(read_schedule())
            return

        if parts == ["api", "counter", "today"]:
            try:
                self._json(get_counter_today())
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return

        if parts == ["api", "git", "status"]:
            self._json(git_status())
            return

        if parts == ["api", "preview"]:
            sys.path.insert(0, str(PROJECT_ROOT / "src"))
            import main as feed_main
            items = feed_main.build()
            self._json({"items": items})
            return

        self._send(404, "not found", "text/plain")

    def do_POST(self):
        parts = self._parts()
        body = self._read_body()
        try:
            if parts == ["api", "schedule"]:
                data = json.loads(body)
                with _lock:
                    write_schedule(data)
                self._json({"ok": True})
                return

            if parts == ["api", "schedule", "anchor"]:
                data = json.loads(body)
                with _lock:
                    cfg = read_schedule()
                    cfg["anchor"] = data["anchor"]
                    write_schedule(cfg)
                self._json({"ok": True})
                return

            if parts == ["api", "counter", "override"]:
                if self.command == "DELETE":
                    with _lock:
                        cfg = read_schedule()
                        cfg.pop("counter_override", None)
                        write_schedule(cfg)
                    self._json({"ok": True})
                    return
                data = json.loads(body)
                with _lock:
                    cfg = read_schedule()
                    cfg["counter_override"] = {
                        "date": data["date"],
                        "day": int(data["day"]),
                        "week": int(data["week"]),
                    }
                    write_schedule(cfg)
                self._json({"ok": True})
                return

            if parts == ["api", "task"]:
                data = json.loads(body)
                with _lock:
                    cfg = read_schedule()
                    tasks = cfg.get("tasks", [])
                    data["id"] = next_id(tasks)
                    tasks.append(data)
                    cfg["tasks"] = tasks
                    write_schedule(cfg)
                self._json({"ok": True, "id": data["id"]})
                return

            if len(parts) == 3 and parts[0] == "api" and parts[1] == "task":
                task_id = int(parts[2])
                with _lock:
                    cfg = read_schedule()
                    tasks = cfg.get("tasks", [])
                    if self.command == "DELETE":
                        cfg["tasks"] = [t for t in tasks if int(t.get("id", 0)) != task_id]
                        write_schedule(cfg)
                        self._json({"ok": True})
                        return
                    data = json.loads(body)
                    for t in tasks:
                        if int(t.get("id", 0)) == task_id:
                            t.update({k: v for k, v in data.items() if k != "id"})
                            break
                    write_schedule(cfg)
                self._json({"ok": True})
                return

            if parts == ["api", "push"]:
                ok, out = git_commit_push("webui: update schedule")
                self._json({"ok": ok, "output": out})
                return

            self._send(404, "not found", "text/plain")
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def do_PUT(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()


def main():
    if not SCHEDULE.exists():
        print(f"schedule.yml not found: {SCHEDULE}", file=sys.stderr)
        sys.exit(1)
    os.chdir(str(PROJECT_ROOT))
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Schedule Master Feed WebUI: http://{HOST}:{PORT}")
    print("Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        server.shutdown()


if __name__ == "__main__":
    main()
