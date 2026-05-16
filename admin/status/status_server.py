#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import socket
import struct
import time


HOST_ROOT = "/host"
MEMINFO_PATH = "/host/proc/meminfo"
MINECRAFT_HOST = os.environ.get("MINECRAFT_HOST", "northstar-minecraft")
MINECRAFT_PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))
MINECRAFT_LOG_PATH = "/minecraft-logs/latest.log"
STAT_PATH = "/host/proc/stat"
LOADAVG_PATH = "/host/proc/loadavg"
PLAYER_LOGIN_PATTERN = re.compile(r"^\[(?P<time>\d{2}:\d{2}:\d{2})\].*?: (?P<name>[A-Za-z0-9_]{3,16}) joined the game$")


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


def read_cpu_sample():
    with open(STAT_PATH, "r", encoding="utf-8") as stat_file:
        parts = stat_file.readline().split()

    if not parts or parts[0] != "cpu":
        return 0, 0

    values = [int(value) for value in parts[1:]]
    idle = values[3] + values[4]
    total = sum(values)
    return idle, total


def read_cpu():
    idle_a, total_a = read_cpu_sample()
    time.sleep(0.12)
    idle_b, total_b = read_cpu_sample()
    idle_delta = idle_b - idle_a
    total_delta = total_b - total_a
    used_percent = 0

    if total_delta > 0:
        used_percent = round((1 - idle_delta / total_delta) * 100, 1)

    load_1m = 0
    cores = 0

    try:
        with open(LOADAVG_PATH, "r", encoding="utf-8") as loadavg_file:
            load_1m = float(loadavg_file.readline().split()[0])
    except (OSError, ValueError, IndexError):
        load_1m = 0

    try:
        with open(STAT_PATH, "r", encoding="utf-8") as stat_file:
            cores = sum(1 for line in stat_file if line.startswith("cpu") and line[3:4].isdigit())
    except OSError:
        cores = 0

    return {
        "used_percent": max(0, min(100, used_percent)),
        "load_1m": round(load_1m, 2),
        "cores": cores,
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


def encode_varint(value):
    value &= 0xFFFFFFFF
    data = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        data.append(byte)
        if not value:
            return bytes(data)


def read_varint(sock):
    value = 0
    shift = 0
    for _ in range(5):
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("socket closed while reading varint")
        current = byte[0]
        value |= (current & 0x7F) << shift
        if not current & 0x80:
            return value
        shift += 7
    raise ValueError("varint is too large")


def read_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("socket closed while reading payload")
        data.extend(chunk)
    return bytes(data)


def packet(payload):
    return encode_varint(len(payload)) + payload


def query_minecraft_status():
    try:
        host = MINECRAFT_HOST.encode("utf-8")
        handshake = (
            encode_varint(0)
            + encode_varint(0)
            + encode_varint(len(host))
            + host
            + struct.pack(">H", MINECRAFT_PORT)
            + encode_varint(1)
        )
        request = encode_varint(0)

        with socket.create_connection((MINECRAFT_HOST, MINECRAFT_PORT), timeout=1.5) as sock:
            sock.settimeout(1.5)
            sock.sendall(packet(handshake))
            sock.sendall(packet(request))

            read_varint(sock)
            packet_id = read_varint(sock)
            if packet_id != 0:
                raise ValueError("unexpected status packet")

            response_length = read_varint(sock)
            response = read_exact(sock, response_length).decode("utf-8")
            status = json.loads(response)

        players = status.get("players", {})
        sample = players.get("sample") or []
        return {
            "reachable": True,
            "online": players.get("online", 0),
            "max": players.get("max", 0),
            "sample": [player.get("name", "unknown") for player in sample if player.get("name")],
            "version": status.get("version", {}).get("name", "unknown"),
        }
    except Exception as error:
        return {
            "reachable": False,
            "online": 0,
            "max": 0,
            "sample": [],
            "version": "unknown",
            "error": str(error),
        }


def read_full_minecraft_log():
    if not os.path.exists(MINECRAFT_LOG_PATH):
        return []

    with open(MINECRAFT_LOG_PATH, "r", encoding="utf-8", errors="replace") as log_file:
        return [line.rstrip() for line in log_file.readlines() if line.rstrip()]


def read_minecraft_log_text():
    lines = read_full_minecraft_log()
    if not lines:
        return "latest.log is not available yet.\n"

    return "\n".join(lines) + "\n"


def read_player_history():
    players = {}

    for line in read_full_minecraft_log():
        match = PLAYER_LOGIN_PATTERN.match(line)
        if not match:
            continue

        name = match.group("name")
        seen_at = match.group("time")
        if name not in players:
            players[name] = {
                "name": name,
                "first_login": seen_at,
                "last_login": seen_at,
            }
        else:
            players[name]["last_login"] = seen_at

    return sorted(players.values(), key=lambda player: player["last_login"], reverse=True)


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/minecraft/latest.log":
            body = read_minecraft_log_text().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path not in ("/api", "/health"):
            self.send_error(404)
            return

        if self.path == "/health":
            payload = {"ok": True}
        else:
            payload = {
                "cpu": read_cpu(),
                "memory": read_memory(),
                "disk": read_disk(),
                "minecraft": {
                    "status": query_minecraft_status(),
                    "logs": read_full_minecraft_log(),
                    "players": read_player_history(),
                },
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
