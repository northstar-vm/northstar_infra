#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os


HOST_ROOT = "/host"
MEMINFO_PATH = "/host/proc/meminfo"


def bytes_to_gib(value):
    return round(value / (1024 ** 3), 1)


def read_memory():
    values = {}
    with open(MEMINFO_PATH, "r", encoding="utf-8") as meminfo:
        for line in meminfo:
            key, raw_value = line.split(":", 1)
            parts = raw_value.strip().split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0]) * 1024

    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0)

    return {
        "total_gib": bytes_to_gib(total),
        "used_gib": bytes_to_gib(used),
        "available_gib": bytes_to_gib(available),
        "used_percent": round((used / total) * 100, 1) if total else 0,
    }


def read_disk():
    stats = os.statvfs(HOST_ROOT)
    total = stats.f_blocks * stats.f_frsize
    available = stats.f_bavail * stats.f_frsize
    used = total - available

    return {
        "mount": "/",
        "total_gib": bytes_to_gib(total),
        "used_gib": bytes_to_gib(used),
        "available_gib": bytes_to_gib(available),
        "used_percent": round((used / total) * 100, 1) if total else 0,
    }


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/api", "/health"):
            self.send_error(404)
            return

        if self.path == "/health":
            payload = {"ok": True}
        else:
            payload = {
                "memory": read_memory(),
                "disk": read_disk(),
            }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), StatusHandler)
    server.serve_forever()
