#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque
from datetime import datetime
import json
import os
import re
import socket
import sqlite3
import struct
import tarfile
import threading
import time
from urllib.parse import parse_qs, quote, urlparse


HOST_ROOT = "/host"
DATA_DIR = "/data"
BACKUP_DIR = os.environ.get("MINECRAFT_BACKUP_DIR", "/backups/minecraft")
MINECRAFT_DATA_DIR = os.environ.get("MINECRAFT_DATA_DIR", "/host/opt/northstar/apps/minecraft/data")
DB_PATH = os.environ.get("NORTHSTAR_DB_PATH", os.path.join(DATA_DIR, "northstar.db"))
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
METRICS_RETENTION_DAYS = int(os.environ.get("METRICS_RETENTION_DAYS", "10"))
METRICS_SAMPLE_SECONDS = int(os.environ.get("METRICS_SAMPLE_SECONDS", "60"))
MEMINFO_PATH = "/host/proc/meminfo"
MINECRAFT_HOST = os.environ.get("MINECRAFT_HOST", "northstar-minecraft")
MINECRAFT_CONTAINER = os.environ.get("MINECRAFT_CONTAINER", "northstar-minecraft")
MINECRAFT_PORT = int(os.environ.get("MINECRAFT_PORT", "25565"))
MINECRAFT_LOG_RECENT_SECONDS = int(os.environ.get("MINECRAFT_LOG_RECENT_SECONDS", "1800"))
MINECRAFT_LOG_RECENT_TAIL = int(os.environ.get("MINECRAFT_LOG_RECENT_TAIL", "200"))
MINECRAFT_LOG_STREAM_TAIL = int(os.environ.get("MINECRAFT_LOG_STREAM_TAIL", "220"))
MINECRAFT_LOG_STREAM_SECONDS = int(os.environ.get("MINECRAFT_LOG_STREAM_SECONDS", "7200"))
MINECRAFT_HISTORY_LOG_SECONDS = int(os.environ.get("MINECRAFT_HISTORY_LOG_SECONDS", "86400"))
MINECRAFT_HISTORY_LOG_TAIL = int(os.environ.get("MINECRAFT_HISTORY_LOG_TAIL", "5000"))
STAT_PATH = "/host/proc/stat"
LOADAVG_PATH = "/host/proc/loadavg"
LOG_PREFIX = r"^\[(?P<time>\d{2}:\d{2}:\d{2})(?:\s+[^\]]+)?\].*?: "
PLAYER_LOGIN_PATTERN = re.compile(LOG_PREFIX + r"(?P<name>[A-Za-z0-9_]{3,16}) joined the game$")
PLAYER_LOGOUT_PATTERN = re.compile(LOG_PREFIX + r"(?P<name>[A-Za-z0-9_]{3,16}) left the game$")
PLAYER_CONNECTED_PATTERN = re.compile(LOG_PREFIX + r"(?P<name>[A-Za-z0-9_]{3,16})\[/[^\]]+\] logged in with entity id \d+")
AUTHME_PLAYER_PATTERN = re.compile(LOG_PREFIX + r".*AuthMe.*\b(?P<name>[A-Za-z0-9_]{3,16})\b.*\b(logged in|registered|authenticated)\b", re.IGNORECASE)
PLAYER_UUID_PATTERN = re.compile(r"UUID of player (?P<name>[A-Za-z0-9_]{3,16}) is (?P<uuid>[0-9a-fA-F-]{32,36})")
DOCKER_TS_PATTERN = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\S+Z)\s+(?P<line>.*)$")
ALLOWED_CONTAINERS = {
    name.strip()
    for name in os.environ.get("DOCKER_ALLOWED_CONTAINERS", "").split(",")
    if name.strip()
}
PROTECTED_CONTAINERS = {
    name.strip()
    for name in os.environ.get("DOCKER_PROTECTED_CONTAINERS", "").split(",")
    if name.strip()
}
DOCKER_ACTIONS = {"start", "stop", "restart", "pause", "unpause"}
LATEST_PAYLOAD = None
LATEST_PAYLOAD_TS = 0
PAYLOAD_LOCK = threading.Lock()
BACKUP_LOCK = threading.Lock()


def bytes_to_gib(value):
    return round(value / (1024 ** 3), 1)


def bytes_to_mib(value):
    return round(value / (1024 ** 2), 1)


def now_ts():
    return int(time.time())


def log_event(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def open_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=8)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=8000")
    return connection


def init_db():
    with open_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vm_samples (
              ts INTEGER PRIMARY KEY,
              cpu_percent REAL NOT NULL,
              memory_percent REAL NOT NULL,
              memory_used_gib REAL NOT NULL,
              disk_percent REAL NOT NULL,
              disk_used_gib REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS container_samples (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              container_id TEXT NOT NULL,
              name TEXT NOT NULL,
              state TEXT NOT NULL,
              cpu_percent REAL NOT NULL,
              memory_used_mib REAL NOT NULL,
              memory_limit_mib REAL NOT NULL,
              memory_percent REAL NOT NULL,
              disk_rw_mib REAL NOT NULL,
              disk_rootfs_mib REAL NOT NULL,
              pids INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_container_samples_ts ON container_samples(ts);
            CREATE INDEX IF NOT EXISTS idx_container_samples_name_ts ON container_samples(name, ts);

            CREATE TABLE IF NOT EXISTS minecraft_samples (
              ts INTEGER PRIMARY KEY,
              reachable INTEGER NOT NULL,
              online INTEGER NOT NULL,
              max_players INTEGER NOT NULL,
              version TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              observed_ts INTEGER NOT NULL,
              log_time TEXT NOT NULL,
              player TEXT NOT NULL,
              action TEXT NOT NULL,
              raw_line TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_player_events_player ON player_events(player, observed_ts);

            CREATE TABLE IF NOT EXISTS player_profiles (
              player TEXT PRIMARY KEY,
              uuid TEXT,
              first_seen_ts INTEGER NOT NULL,
              first_seen_time TEXT NOT NULL,
              last_seen_ts INTEGER NOT NULL,
              last_seen_time TEXT NOT NULL,
              last_action TEXT NOT NULL,
              joins INTEGER NOT NULL DEFAULT 0,
              leaves INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_player_profiles_last_seen ON player_profiles(last_seen_ts);

            CREATE TABLE IF NOT EXISTS minecraft_log_lines (
              raw_line TEXT PRIMARY KEY,
              observed_ts INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_minecraft_log_lines_observed ON minecraft_log_lines(observed_ts);
            """
        )


def prune_history():
    cutoff = now_ts() - METRICS_RETENTION_DAYS * 86400
    with open_db() as db:
        db.execute("DELETE FROM vm_samples WHERE ts < ?", (cutoff,))
        db.execute("DELETE FROM container_samples WHERE ts < ?", (cutoff,))
        db.execute("DELETE FROM minecraft_samples WHERE ts < ?", (cutoff,))
        db.execute("DELETE FROM minecraft_log_lines WHERE observed_ts < ?", (cutoff,))


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


def decode_chunked(body):
    output = bytearray()
    index = 0
    while True:
        marker = body.find(b"\r\n", index)
        if marker == -1:
            return bytes(output)
        size = int(body[index:marker].split(b";", 1)[0], 16)
        index = marker + 2
        if size == 0:
            return bytes(output)
        output.extend(body[index : index + size])
        index += size + 2


class DockerClient:
    def raw_request(self, method, path, payload=None):
        if not os.path.exists(DOCKER_SOCKET):
            raise RuntimeError("Docker socket is not available")

        body = b""
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = (
            f"{method} {path} HTTP/1.1\r\n"
            "Host: docker\r\n"
            "User-Agent: northstar-status\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n"
        )
        if body:
            request += "Content-Type: application/json\r\n"
        request = request.encode("utf-8") + b"\r\n" + body

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(6)
            sock.connect(DOCKER_SOCKET)
            sock.sendall(request)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)

        response = b"".join(chunks)
        header_end = response.find(b"\r\n\r\n")
        if header_end == -1:
            raise RuntimeError("invalid Docker API response")

        header_blob = response[:header_end].decode("iso-8859-1")
        raw_body = response[header_end + 4 :]
        header_lines = header_blob.split("\r\n")
        status_code = int(header_lines[0].split()[1])
        headers = {}
        for line in header_lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip().lower()

        if headers.get("transfer-encoding") == "chunked":
            raw_body = decode_chunked(raw_body)

        if status_code >= 400:
            detail = raw_body.decode("utf-8", errors="replace")
            raise RuntimeError(f"Docker API {status_code}: {detail}")

        return status_code, headers, raw_body

    def request(self, method, path, payload=None):
        _, _, raw_body = self.raw_request(method, path, payload)
        if not raw_body:
            return None
        return json.loads(raw_body.decode("utf-8"))

    def request_text(self, method, path, payload=None):
        _, _, raw_body = self.raw_request(method, path, payload)
        return demux_docker_stream(raw_body).decode("utf-8", errors="replace")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path):
        return self.request("POST", path, {})


docker_client = DockerClient()


def demux_docker_stream(data):
    output = bytearray()
    index = 0
    while index + 8 <= len(data):
        stream_type = data[index]
        if stream_type not in (0, 1, 2):
            return data
        frame_size = int.from_bytes(data[index + 4 : index + 8], "big")
        index += 8
        if index + frame_size > len(data):
            return data
        output.extend(data[index : index + frame_size])
        index += frame_size
    if index == len(data):
        return bytes(output)
    return data


def container_name(container):
    names = container.get("Names") or []
    if names:
        return names[0].lstrip("/")
    return container.get("Id", "")[:12]


def is_allowed_container(name):
    return not ALLOWED_CONTAINERS or name in ALLOWED_CONTAINERS


def find_container_by_name(name):
    containers = docker_client.get("/containers/json?all=1") or []
    for container in containers:
        if container_name(container) == name:
            return container
    return None


def calculate_cpu_percent(stats):
    cpu_stats = stats.get("cpu_stats", {})
    previous = stats.get("precpu_stats", {})
    cpu_usage = cpu_stats.get("cpu_usage", {})
    previous_usage = previous.get("cpu_usage", {})
    cpu_delta = cpu_usage.get("total_usage", 0) - previous_usage.get("total_usage", 0)
    system_delta = cpu_stats.get("system_cpu_usage", 0) - previous.get("system_cpu_usage", 0)
    online_cpus = cpu_stats.get("online_cpus") or len(cpu_usage.get("percpu_usage") or []) or 1

    if cpu_delta > 0 and system_delta > 0:
        return round((cpu_delta / system_delta) * online_cpus * 100, 1)
    return 0


def calculate_memory(stats):
    memory = stats.get("memory_stats", {})
    raw_usage = memory.get("usage", 0)
    stats_values = memory.get("stats", {})
    cache = stats_values.get("total_inactive_file", stats_values.get("inactive_file", 0))
    usage = max(raw_usage - cache, 0)
    limit = memory.get("limit", 0)
    percent = round((usage / limit) * 100, 1) if limit else 0
    return usage, limit, percent


def read_container_stats():
    try:
        containers = docker_client.get("/containers/json?all=1&size=1") or []
    except Exception as error:
        return {"available": False, "error": str(error), "containers": []}

    result = []
    for container in containers:
        name = container_name(container)
        if not is_allowed_container(name):
            continue

        container_id = container.get("Id", "")
        state = container.get("State", "unknown")
        stats_payload = {}
        if state == "running":
            try:
                stats_payload = docker_client.get(f"/containers/{quote(container_id)}/stats?stream=false") or {}
            except Exception:
                stats_payload = {}

        memory_used, memory_limit, memory_percent = calculate_memory(stats_payload)
        pids = stats_payload.get("pids_stats", {}).get("current", 0)

        result.append(
            {
                "id": container_id[:12],
                "full_id": container_id,
                "name": name,
                "image": container.get("Image", ""),
                "state": state,
                "status": container.get("Status", ""),
                "protected": name in PROTECTED_CONTAINERS,
                "cpu_percent": calculate_cpu_percent(stats_payload),
                "memory_used_mib": bytes_to_mib(memory_used),
                "memory_limit_mib": bytes_to_mib(memory_limit),
                "memory_percent": memory_percent,
                "disk_rw_mib": bytes_to_mib(container.get("SizeRw") or 0),
                "disk_rootfs_mib": bytes_to_mib(container.get("SizeRootFs") or 0),
                "pids": pids,
            }
        )

    result.sort(key=lambda item: item["name"])
    return {"available": True, "containers": result}


def perform_container_action(name, action):
    if action not in DOCKER_ACTIONS:
        raise PermissionError("unsupported action")
    if name in PROTECTED_CONTAINERS:
        raise PermissionError("container is protected")
    if not is_allowed_container(name):
        raise PermissionError("container is not allowlisted")

    match = find_container_by_name(name)

    if not match:
        raise FileNotFoundError("container not found")

    suffix = "?t=10" if action in {"stop", "restart"} else ""
    docker_client.post(f"/containers/{quote(match['Id'])}/{action}{suffix}")
    return {"ok": True, "container": name, "action": action}


def read_container_log_text(name):
    if not is_allowed_container(name):
        raise PermissionError("container is not allowlisted")

    match = find_container_by_name(name)
    if not match:
        raise FileNotFoundError("container not found")

    path = f"/containers/{quote(match['Id'])}/logs?stdout=1&stderr=1&timestamps=1"
    text = docker_client.request_text("GET", path)
    return text if text.strip() else f"No logs for {name} yet.\n"


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


def read_minecraft_log_text(tail=500, since=None, timestamps=False, empty_message=True):
    try:
        container = find_container_by_name(MINECRAFT_CONTAINER)
        if not container:
            return "Minecraft container is not available.\n"
        ts_flag = "1" if timestamps else "0"
        path = f"/containers/{quote(container['Id'])}/logs?stdout=1&stderr=1&tail={int(tail)}&timestamps={ts_flag}"
        if since is not None:
            path += f"&since={int(since)}"
        text = docker_client.request_text("GET", path)
        if text.strip():
            return text
        return "Minecraft Docker logs are empty.\n" if empty_message else ""
    except Exception as error:
        return f"Minecraft Docker logs unavailable: {error}\n"


def read_full_minecraft_log():
    return [line.rstrip() for line in read_minecraft_log_text().splitlines() if line.rstrip()]


def read_recent_minecraft_log():
    since = now_ts() - MINECRAFT_LOG_RECENT_SECONDS
    return [
        line.rstrip()
        for line in read_minecraft_log_text(tail=MINECRAFT_LOG_RECENT_TAIL, since=since).splitlines()
        if line.rstrip()
    ]


def read_history_minecraft_log():
    since = now_ts() - MINECRAFT_HISTORY_LOG_SECONDS
    return [
        line.rstrip()
        for line in read_minecraft_log_text(tail=MINECRAFT_HISTORY_LOG_TAIL, since=since, timestamps=True).splitlines()
        if line.rstrip()
    ]


def extract_player_event(line):
    joined = PLAYER_LOGIN_PATTERN.match(line)
    if joined:
        return joined.group("time"), joined.group("name"), "joined"

    left = PLAYER_LOGOUT_PATTERN.match(line)
    if left:
        return left.group("time"), left.group("name"), "left"

    connected = PLAYER_CONNECTED_PATTERN.match(line)
    if connected:
        return connected.group("time"), connected.group("name"), "connected"

    authme = AUTHME_PLAYER_PATTERN.match(line)
    if authme:
        return authme.group("time"), authme.group("name"), "authenticated"

    return None


def parse_docker_log_line(line):
    match = DOCKER_TS_PATTERN.match(line)
    if not match:
        return None, line
    raw_ts = match.group("ts")
    try:
        normalized = raw_ts.replace("Z", "+00:00")
        if "." in normalized:
            head, tail = normalized.split(".", 1)
            fraction, offset = tail.split("+", 1)
            normalized = f"{head}.{fraction[:6].ljust(6, '0')}+{offset}"
        event_ts = int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        event_ts = None
    return event_ts, match.group("line")


def format_event_time(event_ts, fallback):
    if event_ts:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event_ts))
    return fallback


def read_player_history(lines=None):
    if lines is None:
        lines = read_full_minecraft_log()

    players = {}

    for line in lines:
        event = extract_player_event(line)
        if not event:
            continue

        seen_at, name, action = event
        if action == "left":
            continue
        if name not in players:
            players[name] = {
                "name": name,
                "first_login": seen_at,
                "last_login": seen_at,
            }
        else:
            players[name]["last_login"] = seen_at

    return sorted(players.values(), key=lambda player: player["last_login"], reverse=True)


def run_minecraft_command(command):
    command = command.strip()
    if command.startswith("/"):
        command = command[1:].strip()
    if not command:
        raise ValueError("command is empty")
    if len(command) > 180:
        raise ValueError("command is too long")

    container = find_container_by_name(MINECRAFT_CONTAINER)
    if not container:
        raise FileNotFoundError("Minecraft container not found")
    if container.get("State") != "running":
        raise RuntimeError(f"Minecraft container is {container.get('State', 'unknown')}")

    try:
        output = run_container_exec(container["Id"], ["mc-send-to-console", command])
    except Exception:
        output = run_container_exec(container["Id"], ["rcon-cli", command])
    return {
        "ok": True,
        "command": command,
        "output": output.strip() or "Command sent.",
    }


def run_container_exec(container_id, command):
    exec_payload = {
        "AttachStdout": True,
        "AttachStderr": True,
        "Tty": False,
        "Cmd": command,
    }
    exec_result = docker_client.request("POST", f"/containers/{quote(container_id)}/exec", exec_payload)
    exec_id = exec_result.get("Id")
    if not exec_id:
        raise RuntimeError("Docker did not create exec session")
    return docker_client.request_text("POST", f"/exec/{quote(exec_id)}/start", {"Detach": False, "Tty": False})


def read_player_events(lines):
    events = []
    uuid_by_player = {}
    for raw_line in lines:
        event_ts, line = parse_docker_log_line(raw_line)
        uuid_match = PLAYER_UUID_PATTERN.search(line)
        if uuid_match:
            uuid_by_player[uuid_match.group("name")] = uuid_match.group("uuid")

        event = extract_player_event(line)
        if not event:
            continue
        log_time, player, action = event
        events.append(
            {
                "log_time": log_time,
                "player": player,
                "uuid": uuid_by_player.get(player),
                "action": action,
                "event_ts": event_ts,
                "raw_line": raw_line,
            }
        )
    return events


def store_player_events():
    observed = now_ts()
    lines = read_history_minecraft_log()
    events = read_player_events(lines)
    with open_db() as db:
        if lines:
            db.executemany(
                """
                INSERT OR IGNORE INTO minecraft_log_lines (raw_line, observed_ts)
                VALUES (?, ?)
                """,
                [(line, observed) for line in lines[-500:]],
            )

        for raw_line in lines:
            _, line = parse_docker_log_line(raw_line)
            uuid_match = PLAYER_UUID_PATTERN.search(line)
            if not uuid_match:
                continue
            player = uuid_match.group("name")
            player_uuid = uuid_match.group("uuid")
            existing = db.execute("SELECT first_seen_ts, first_seen_time FROM player_profiles WHERE player = ?", (player,)).fetchone()
            if existing:
                db.execute(
                    """
                    UPDATE player_profiles
                    SET uuid = ?
                    WHERE player = ?
                    """,
                    (player_uuid, player),
                )

        if not events:
            return

        for event in events:
            event_ts = event.get("event_ts") or observed
            event_time = format_event_time(event.get("event_ts"), event["log_time"])
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO player_events (observed_ts, log_time, player, action, raw_line)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_ts, event_time, event["player"], event["action"], event["raw_line"]),
            )
            if cursor.rowcount == 0:
                continue

            player = event["player"]
            existing = db.execute("SELECT last_action FROM player_profiles WHERE player = ?", (player,)).fetchone()
            join_delta = 1 if event["action"] == "joined" else 0
            leave_delta = 1 if event["action"] == "left" else 0
            if existing:
                db.execute(
                    """
                    UPDATE player_profiles
                    SET uuid = COALESCE(?, uuid),
                        first_seen_ts = CASE WHEN last_action = 'uuid' THEN ? ELSE first_seen_ts END,
                        first_seen_time = CASE WHEN last_action = 'uuid' THEN ? ELSE first_seen_time END,
                        last_seen_ts = ?,
                        last_seen_time = ?,
                        last_action = ?,
                        joins = joins + ?,
                        leaves = leaves + ?
                    WHERE player = ?
                    """,
                    (event.get("uuid"), event_ts, event_time, event_ts, event_time, event["action"], join_delta, leave_delta, player),
                )
            else:
                db.execute(
                    """
                    INSERT INTO player_profiles
                    (player, uuid, first_seen_ts, first_seen_time, last_seen_ts, last_seen_time, last_action, joins, leaves)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        player,
                        event.get("uuid"),
                        event_ts,
                        event_time,
                        event_ts,
                        event_time,
                        event["action"],
                        join_delta,
                        leave_delta,
                    ),
                )


def read_persisted_player_history():
    with open_db() as db:
        rows = db.execute(
            """
            SELECT
              player,
              uuid,
              first_seen_ts,
              first_seen_time,
              last_seen_ts,
              last_seen_time,
              last_action,
              joins,
              leaves
            FROM player_profiles
            ORDER BY last_seen_ts DESC, player ASC
            LIMIT 80
            """
        ).fetchall()
    return [
        {
            "name": row[0],
            "uuid": row[1] or "",
            "first_seen_ts": row[2],
            "first_login": row[3],
            "last_seen_ts": row[4],
            "last_login": row[5],
            "last_action": row[6],
            "joins": row[7],
            "leaves": row[8],
        }
        for row in rows
    ]


def read_stored_minecraft_logs(limit=500):
    with open_db() as db:
        rows = db.execute(
            """
            SELECT raw_line
            FROM minecraft_log_lines
            ORDER BY observed_ts DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row[0] for row in reversed(rows)]


def read_latest_minecraft_history():
    with open_db() as db:
        row = db.execute(
            """
            SELECT ts, reachable, online, max_players, version
            FROM minecraft_samples
            ORDER BY ts DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return {
            "reachable": False,
            "online": 0,
            "max": 0,
            "sample": [],
            "version": "unknown",
            "stale": True,
        }
    return {
        "ts": row[0],
        "reachable": bool(row[1]),
        "online": row[2],
        "max": row[3],
        "sample": [],
        "version": row[4],
        "stale": True,
    }


def store_sample(cpu, memory, disk, minecraft, docker):
    ts = now_ts()
    status = minecraft.get("status", {})
    containers = docker.get("containers", []) if docker.get("available") else []

    with open_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO vm_samples
            (ts, cpu_percent, memory_percent, memory_used_gib, disk_percent, disk_used_gib)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                cpu.get("used_percent", 0),
                memory.get("used_percent", 0),
                memory.get("used_gib", 0),
                disk.get("used_percent", 0),
                disk.get("used_gib", 0),
            ),
        )
        db.execute(
            """
            INSERT OR REPLACE INTO minecraft_samples
            (ts, reachable, online, max_players, version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ts,
                1 if status.get("reachable") else 0,
                status.get("online", 0),
                status.get("max", 0),
                status.get("version", "unknown"),
            ),
        )
        db.executemany(
            """
            INSERT INTO container_samples
            (ts, container_id, name, state, cpu_percent, memory_used_mib, memory_limit_mib,
             memory_percent, disk_rw_mib, disk_rootfs_mib, pids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ts,
                    item["id"],
                    item["name"],
                    item["state"],
                    item["cpu_percent"],
                    item["memory_used_mib"],
                    item["memory_limit_mib"],
                    item["memory_percent"],
                    item["disk_rw_mib"],
                    item["disk_rootfs_mib"],
                    item["pids"],
                )
                for item in containers
            ],
        )

def read_history_summary():
    with open_db() as db:
        vm_count = db.execute("SELECT COUNT(*) FROM vm_samples").fetchone()[0]
        container_count = db.execute("SELECT COUNT(*) FROM container_samples").fetchone()[0]
        player_count = db.execute("SELECT COUNT(*) FROM player_profiles").fetchone()[0]
        last_sample = db.execute("SELECT MAX(ts) FROM vm_samples").fetchone()[0]
    return {
        "retention_days": METRICS_RETENTION_DAYS,
        "vm_samples": vm_count,
        "container_samples": container_count,
        "players": player_count,
        "last_sample_ts": last_sample,
    }


def read_latest_container_history():
    with open_db() as db:
        rows = db.execute(
            """
            SELECT cs.ts, cs.container_id, cs.name, cs.state, cs.cpu_percent,
                   cs.memory_used_mib, cs.memory_limit_mib, cs.memory_percent,
                   cs.disk_rw_mib, cs.disk_rootfs_mib, cs.pids
            FROM container_samples cs
            INNER JOIN (
              SELECT name, MAX(ts) AS ts
              FROM container_samples
              GROUP BY name
            ) latest ON latest.name = cs.name AND latest.ts = cs.ts
            ORDER BY cs.name
            """
        ).fetchall()

    return [
        {
            "ts": row[0],
            "id": row[1],
            "name": row[2],
            "state": row[3],
            "status": f"last sampled at {time.strftime('%H:%M:%S', time.localtime(row[0]))}",
            "protected": row[2] in PROTECTED_CONTAINERS,
            "cpu_percent": row[4],
            "memory_used_mib": row[5],
            "memory_limit_mib": row[6],
            "memory_percent": row[7],
            "disk_rw_mib": row[8],
            "disk_rootfs_mib": row[9],
            "pids": row[10],
            "stale": True,
        }
        for row in rows
    ]


def read_backup_summary(limit=8):
    try:
        entries = []
        total_bytes = 0
        if not os.path.isdir(BACKUP_DIR):
            return {"available": False, "files": [], "total_mib": 0, "error": "backup directory not mounted"}

        for name in os.listdir(BACKUP_DIR):
            if not name.startswith("minecraft-world-") or not name.endswith(".tar.gz"):
                continue
            path = os.path.join(BACKUP_DIR, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            total_bytes += stat.st_size
            entries.append(
                {
                    "name": name,
                    "mtime": int(stat.st_mtime),
                    "size_mib": round(stat.st_size / (1024 ** 2), 1),
                }
            )

        entries.sort(key=lambda item: item["mtime"], reverse=True)
        return {
            "available": True,
            "files": entries[:limit],
            "count": len(entries),
            "total_mib": round(total_bytes / (1024 ** 2), 1),
        }
    except Exception as error:
        return {"available": False, "files": [], "total_mib": 0, "error": str(error)}


def create_minecraft_backup():
    if not BACKUP_LOCK.acquire(blocking=False):
        raise RuntimeError("backup already running")

    save_disabled = False
    try:
        if not os.path.isdir(MINECRAFT_DATA_DIR):
            raise FileNotFoundError("Minecraft data directory not mounted")

        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        filename = f"minecraft-world-{timestamp}.tar.gz"
        backup_path = os.path.join(BACKUP_DIR, filename)
        partial_path = f"{backup_path}.partial"

        container = find_container_by_name(MINECRAFT_CONTAINER)
        if container and container.get("State") == "running":
            try:
                run_container_exec(container["Id"], ["rcon-cli", "save-off"])
                save_disabled = True
                run_container_exec(container["Id"], ["rcon-cli", "save-all", "flush"])
            except Exception as error:
                raise RuntimeError(f"Minecraft save-off failed: {error}") from error

        with tarfile.open(partial_path, "w:gz") as archive:
            archive.add(MINECRAFT_DATA_DIR, arcname=".")
        os.replace(partial_path, backup_path)

        if save_disabled and container:
            run_container_exec(container["Id"], ["rcon-cli", "save-on"])
            save_disabled = False

        stat = os.stat(backup_path)
        log_event(f"minecraft backup created: {filename}")
        return {
            "ok": True,
            "file": filename,
            "size_mib": round(stat.st_size / (1024 ** 2), 1),
            "backups": read_backup_summary(),
        }
    except Exception:
        try:
            if "partial_path" in locals() and os.path.exists(partial_path):
                os.remove(partial_path)
        finally:
            raise
    finally:
        if save_disabled:
            try:
                container = find_container_by_name(MINECRAFT_CONTAINER)
                if container:
                    run_container_exec(container["Id"], ["rcon-cli", "save-on"])
            except Exception as error:
                log_event(f"minecraft backup save-on failed: {error}")
        BACKUP_LOCK.release()


def build_status_payload(store=False):
    cpu = read_cpu()
    memory = read_memory()
    disk = read_disk()
    minecraft_logs = read_recent_minecraft_log()
    if store:
        store_player_events()
    minecraft = {
        "status": query_minecraft_status(),
        "logs": minecraft_logs,
        "players": read_persisted_player_history() or read_player_history(minecraft_logs),
    }
    docker = read_container_stats()

    if store:
        store_sample(cpu, memory, disk, minecraft, docker)

    payload = {
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "docker": docker,
        "minecraft": minecraft,
        "backups": read_backup_summary(),
        "history": read_history_summary(),
    }
    return payload


def set_latest_payload(payload):
    global LATEST_PAYLOAD, LATEST_PAYLOAD_TS
    with PAYLOAD_LOCK:
        LATEST_PAYLOAD = payload
        LATEST_PAYLOAD_TS = now_ts()


def get_latest_payload(max_age=180):
    with PAYLOAD_LOCK:
        if LATEST_PAYLOAD and now_ts() - LATEST_PAYLOAD_TS <= max_age:
            return LATEST_PAYLOAD
    return None


def read_stream_minecraft_lines(tail=None, since=None):
    text = read_minecraft_log_text(
        tail=tail or MINECRAFT_LOG_STREAM_TAIL,
        since=since,
        timestamps=False,
        empty_message=False,
    )
    return [line.rstrip() for line in text.splitlines() if line.rstrip()]


def sampler_loop():
    while True:
        try:
            set_latest_payload(build_status_payload(store=True))
            prune_history()
        except Exception as error:
            log_event(f"sampler error: {error}")
        time.sleep(max(15, METRICS_SAMPLE_SECONDS))


class StatusHandler(BaseHTTPRequestHandler):
    def send_sse_event(self, event, payload):
        body = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def stream_minecraft_logs(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        seen = deque(maxlen=1200)
        cursor = max(0, now_ts() - 2)
        started_at = now_ts()

        initial_lines = read_stream_minecraft_lines(tail=MINECRAFT_LOG_STREAM_TAIL)
        for line in initial_lines:
            seen.append(line)
        self.send_sse_event("logs", {"mode": "replace", "lines": initial_lines})

        while now_ts() - started_at < MINECRAFT_LOG_STREAM_SECONDS:
            time.sleep(1.5)
            lines = read_stream_minecraft_lines(tail=MINECRAFT_LOG_STREAM_TAIL, since=max(0, cursor - 1))
            cursor = now_ts()
            fresh = []
            seen_set = set(seen)
            for line in lines:
                if line in seen_set:
                    continue
                seen.append(line)
                seen_set.add(line)
                fresh.append(line)
            if fresh:
                self.send_sse_event("logs", {"mode": "append", "lines": fresh})
            else:
                self.send_sse_event("ping", {"ts": now_ts()})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/docker/logs":
            query = parse_qs(parsed.query)
            name = str(query.get("container", [""])[0])
            try:
                body = read_container_log_text(name).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except PermissionError as error:
                self.send_error(403, str(error))
            except FileNotFoundError as error:
                self.send_error(404, str(error))
            except Exception as error:
                self.send_error(500, str(error))
            return

        if parsed.path == "/minecraft/logs":
            body = read_minecraft_log_text().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/minecraft/logs/stream":
            try:
                self.stream_minecraft_logs()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                log_event(f"minecraft log stream failed: {error}")
            return

        if parsed.path == "/history":
            query = parse_qs(parsed.query)
            limit = min(int(query.get("limit", ["120"])[0]), 500)
            with open_db() as db:
                vm_rows = db.execute(
                    "SELECT ts, cpu_percent, memory_percent, memory_used_gib, disk_percent, disk_used_gib FROM vm_samples ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            payload = {
                "vm": [
                    {
                        "ts": row[0],
                        "cpu_percent": row[1],
                        "memory_percent": row[2],
                        "memory_used_gib": row[3],
                        "disk_percent": row[4],
                        "disk_used_gib": row[5],
                    }
                    for row in reversed(vm_rows)
                ],
                "containers": read_latest_container_history(),
                "minecraft": {
                    "status": read_latest_minecraft_history(),
                    "logs": read_stored_minecraft_logs(),
                    "players": read_persisted_player_history(),
                },
                "backups": read_backup_summary(),
                "summary": read_history_summary(),
            }
            self.send_json(payload)
            return

        if parsed.path not in ("/api", "/health"):
            self.send_error(404)
            return

        if parsed.path == "/health":
            payload = {"ok": True}
        else:
            payload = get_latest_payload()
            if not payload:
                payload = build_status_payload(store=True)
                set_latest_payload(payload)

        self.send_json(payload)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/minecraft/backup":
            if self.headers.get("X-Northstar-Action") != "1":
                self.send_error(403)
                return

            try:
                result = create_minecraft_backup()
                set_latest_payload(build_status_payload(store=True))
                self.send_json(result)
            except FileNotFoundError as error:
                self.send_error(404, str(error))
            except Exception as error:
                self.send_error(500, str(error))
            return

        if parsed.path == "/minecraft/command":
            if self.headers.get("X-Northstar-Action") != "1":
                self.send_error(403)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = run_minecraft_command(str(payload.get("command", "")))
                log_event("minecraft command sent")
                self.send_json(result)
            except ValueError as error:
                self.send_error(400, str(error))
            except FileNotFoundError as error:
                self.send_error(404, str(error))
            except Exception as error:
                self.send_error(500, str(error))
            return

        if parsed.path != "/docker/action":
            self.send_error(404)
            return

        if self.headers.get("X-Northstar-Action") != "1":
            self.send_error(403)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            name = str(payload.get("container", ""))
            action = str(payload.get("action", ""))
            result = perform_container_action(name, action)
            log_event(f"docker action {action} requested for {name}")
            self.send_json(result)
        except PermissionError as error:
            self.send_error(403, str(error))
        except FileNotFoundError as error:
            self.send_error(404, str(error))
        except Exception as error:
            self.send_error(500, str(error))

    def send_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if self.path.startswith(("/api", "/health", "/docker/logs", "/minecraft/logs")):
            return
        log_event(format % args)


if __name__ == "__main__":
    init_db()
    log_event("northstar status service starting on :8080")
    threading.Thread(target=sampler_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", 8080), StatusHandler)
    server.serve_forever()
