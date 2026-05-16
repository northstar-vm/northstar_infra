#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import socket
import struct


HOST_ROOT = "/host"
MEMINFO_PATH = "/host/proc/meminfo"
MINECRAFT_HOST = os.environ.get("MINECRAFT_HOST", "northstar-minecraft")
MINECRAFT_PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))
MINECRAFT_LOG_PATH = "/minecraft-logs/latest.log"
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


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


def read_minecraft_log():
    if not os.path.exists(MINECRAFT_LOG_PATH):
        return []

    with open(MINECRAFT_LOG_PATH, "r", encoding="utf-8", errors="replace") as log_file:
        lines = log_file.readlines()[-60:]

    redacted = []
    for line in lines:
        line = IP_PATTERN.sub("[ip]", line.rstrip())
        if line:
            redacted.append(line)
    return redacted


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
                "minecraft": {
                    "status": query_minecraft_status(),
                    "logs": read_minecraft_log(),
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
