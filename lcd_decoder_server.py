#!/usr/bin/env python3
"""Unified ST7565 LCD Display Analyzer Server.

Supports Display Variant 1 (Offset 3, XOR-4) and Display Variant 2 (Offset 0, Linear)
with runtime switching, persistent settings, and robust Saleae Logic USB auto-reconnection.
"""

from __future__ import annotations

import argparse
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, unquote, urlparse
import uuid
import zipfile

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
VARIANTS_PATH = CONFIG_DIR / "variants.json"
CALIBRATION_PATH = BASE_DIR / "calibrations" / "st7565_digits_16x28.json"
C_SOURCE = BASE_DIR / "st7565_trace_export.c"
CACHE = Path(tempfile.gettempdir()) / f"lcd_decoder_cache_{BASE_DIR.name}"
BINARY = BASE_DIR / "st7565_trace_export"
MIN_SAMPLE_RATE = 4_000_000
LIVE_BUFFER_DEFAULT = 1024
SETTINGS_LOCK = threading.RLock()


def live_command_name(value: int) -> str:
    if value & 0xF0 == 0xB0:
        return "Set page"
    if value & 0xF0 == 0x10:
        return "Column high"
    if value & 0xF0 == 0x00:
        return "Column low"
    return {
        0xE2: "Reset",
        0xAF: "Display on",
        0xAE: "Display off",
    }.get(value, "Command")


def scan_sigrok_devices() -> list[dict]:
    try:
        result = subprocess.run(
            ["sigrok-cli", "--scan"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not scan sigrok devices: {error}") from error
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    devices = []
    for line in output.splitlines():
        match = re.match(r"^(\S+)\s+-\s+(.+)$", line.strip())
        if not match:
            continue
        driver, label = match.groups()
        devices.append({
            "driver": driver,
            "label": label,
            "hardware": driver.split(":", 1)[0] != "demo",
        })
    if result.returncode and not devices:
        raise RuntimeError(output.strip() or "sigrok device scan failed")
    return devices


class LiveCapture:
    """Continuous sigrok capture with state-machine auto-reconnect and epoch tracking."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.events: deque[dict] = deque(maxlen=LIVE_BUFFER_DEFAULT)
        self.framebuffer = bytearray(132 * 8)
        self.buffer_base_framebuffer = bytearray(132 * 8)
        self.capture: subprocess.Popen | None = None
        self.decoder: subprocess.Popen | None = None
        self.running = False
        self.version = 0
        self.sequence = 0
        self.capture_epoch = uuid.uuid4().hex[:8]
        self.sample_rate = 4_000_000
        self.driver = "fx2lafw"
        self.buffer_size = LIVE_BUFFER_DEFAULT
        self.events_received = 0
        self.samples_received = 0
        self.commands = 0
        self.data = 0
        self.invalid_frames = 0
        self.ignored_bytes = 0
        self.unknown_commands = 0
        self.started_at = 0.0
        self.last_error = ""
        self.auto_reconnect = True
        self._supervisor_thread = threading.Thread(
            target=self._auto_reconnect_supervisor, daemon=True, name="LiveSupervisor"
        )
        self._supervisor_thread.start()

    def _auto_reconnect_supervisor(self) -> None:
        backoff = 1.5
        while True:
            time.sleep(backoff)
            with self.lock:
                should_reconnect = self.auto_reconnect and not self.running
                sample_rate = self.sample_rate or 4_000_000
                buffer_size = self.buffer_size or LIVE_BUFFER_DEFAULT
            if should_reconnect:
                try:
                    devices = scan_sigrok_devices()
                    matching = [d for d in devices if d.get("hardware")]
                    if matching:
                        driver = matching[0]["driver"]
                        sys.stderr.write(f"[LiveSupervisor] Found hardware {driver}, starting live stream...\n")
                        self.start(driver, sample_rate, buffer_size)
                        backoff = 2.0
                    else:
                        backoff = min(backoff * 1.5, 8.0)
                except Exception:
                    backoff = min(backoff * 1.5, 8.0)
            else:
                backoff = 2.0

    def _notify(self) -> None:
        self.version += 1
        self.changed.notify_all()

    def status(self) -> dict:
        with self.lock:
            return self._status_unlocked()

    def _status_unlocked(self) -> dict:
        return {
            "running": self.running,
            "driver": self.driver,
            "sampleRate": self.sample_rate,
            "bufferSize": self.buffer_size,
            "buffered": len(self.events),
            "eventsReceived": self.events_received,
            "samplesReceived": self.samples_received,
            "commands": self.commands,
            "data": self.data,
            "invalidFrames": self.invalid_frames,
            "ignoredBytes": self.ignored_bytes,
            "unknownCommands": self.unknown_commands,
            "startedAt": self.started_at,
            "lastError": self.last_error,
            "version": self.version,
            "captureEpoch": self.capture_epoch,
        }

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self._status_unlocked(),
                "framebuffer": list(self.framebuffer),
                "baseFramebuffer": list(self.buffer_base_framebuffer),
                "events": list(self.events),
                "sequence": self.sequence,
                "captureEpoch": self.capture_epoch,
            }

    def start(
        self,
        driver: str,
        sample_rate: int,
        buffer_size: int,
        initial_framebuffer: list[int] | None = None,
    ) -> dict:
        if sample_rate < MIN_SAMPLE_RATE:
            raise ValueError(
                f"Sample rate {sample_rate:,} Hz is below {MIN_SAMPLE_RATE:,} Hz"
            )
        if buffer_size not in (512, 1024):
            raise ValueError("Buffer size must be 512 or 1024")
        if initial_framebuffer is None:
            framebuffer = bytearray(132 * 8)
        elif (
            isinstance(initial_framebuffer, list)
            and len(initial_framebuffer) == 132 * 8
            and all(isinstance(value, int) and 0 <= value <= 255
                    for value in initial_framebuffer)
        ):
            framebuffer = bytearray(initial_framebuffer)
        else:
            raise ValueError("Initial framebuffer must contain 1056 bytes")
        if not re.fullmatch(r"[A-Za-z0-9_.:=-]+", driver):
            raise ValueError("Invalid sigrok driver")
        requested_base = driver.split(":", 1)[0]
        matching = []
        for attempt in range(3):
            devices = scan_sigrok_devices()
            matching = [
                device for device in devices
                if device["driver"] == driver
                or device["driver"].split(":", 1)[0] == requested_base
            ]
            if any(device["hardware"] for device in matching):
                break
            if attempt < 2:
                time.sleep(0.75)
        if not matching or not any(device["hardware"] for device in matching):
            raise ValueError(
                f"No {requested_base} logic analyzer is connected. "
                "Connect it and rescan before starting Live mode."
            )
        driver = matching[0]["driver"]
        self.stop()
        self.auto_reconnect = True
        compile_decoder()
        capture_command = [
            "sigrok-cli",
            "--driver", driver,
            "--config", f"samplerate={sample_rate}",
            "--channels", "D0,D1,D2,D3,D4,D5,D6,D7",
            "--continuous",
            "-O", "binary",
        ]
        try:
            capture = subprocess.Popen(
                capture_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            assert capture.stdout is not None
            decoder = subprocess.Popen(
                [str(BINARY), "--stream", str(sample_rate)],
                stdin=capture.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            capture.stdout.close()
        except (OSError, subprocess.SubprocessError):
            if "capture" in locals() and capture.poll() is None:
                capture.kill()
            raise
        with self.lock:
            self.events = deque(maxlen=buffer_size)
            self.framebuffer = framebuffer
            self.buffer_base_framebuffer = bytearray(framebuffer)
            self.capture = capture
            self.decoder = decoder
            self.running = True
            self.sequence = 0
            self.capture_epoch = uuid.uuid4().hex[:8]
            self.sample_rate = sample_rate
            self.driver = driver
            self.buffer_size = buffer_size
            self.events_received = 0
            self.samples_received = 0
            self.commands = 0
            self.data = 0
            self.invalid_frames = 0
            self.ignored_bytes = 0
            self.unknown_commands = 0
            self.started_at = time.time()
            self.last_error = ""
            self._notify()
        threading.Thread(
            target=self._read_decoder_output,
            args=(decoder, capture),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._monitor_process,
            args=(capture, "sigrok-cli"),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._monitor_process,
            args=(decoder, "st7565_trace_export"),
            daemon=True,
        ).start()
        return self.status()

    def _read_decoder_output(
        self,
        decoder: subprocess.Popen,
        capture: subprocess.Popen,
    ) -> None:
        assert decoder.stdout is not None
        for raw_line in decoder.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                self._handle_metadata(line)
                continue
            parts = line.split(",")
            if len(parts) != 7:
                continue
            try:
                kind, sample, sample_end, page, column, value, flags = (
                    int(parts[0]),
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                    int(parts[5]),
                    int(parts[6]),
                )
            except ValueError:
                continue
            event = {
                "kind": kind,
                "sample": sample,
                "sampleEnd": sample_end,
                "page": page,
                "column": column,
                "value": value,
                "flags": flags,
            }
            if kind == 0:
                event["name"] = live_command_name(value)
            with self.lock:
                if self.decoder is not decoder:
                    return
                self.sequence += 1
                event["seq"] = self.sequence
                if len(self.events) == self.events.maxlen:
                    oldest = self.events[0]
                    self._apply_event_to_framebuffer(
                        self.buffer_base_framebuffer, oldest)
                self.events.append(event)
                self.events_received += 1
                self.samples_received = max(self.samples_received, sample_end)
                if kind == 1:
                    self.data += 1
                elif kind == 0:
                    self.commands += 1
                self._apply_event_to_framebuffer(self.framebuffer, event)
                self._notify()
        with self.lock:
            if self.decoder is decoder:
                self.running = False
                self._notify()

    def _handle_metadata(self, line: str) -> None:
        match = re.match(r"^#\s*([A-Za-z0-9_]+)=(.+)$", line)
        if not match:
            return
        key, raw_value = match.groups()
        try:
            value = int(raw_value)
        except ValueError:
            return
        with self.lock:
            if key == "invalid_frames":
                self.invalid_frames = value
            elif key == "ignored_bytes":
                self.ignored_bytes = value
            elif key == "unknown_commands":
                self.unknown_commands = value
            self._notify()

    def _monitor_process(self, process: subprocess.Popen, label: str) -> None:
        returncode = process.wait()
        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read() or ""
        with self.lock:
            if process in (self.capture, self.decoder):
                self.running = False
                if returncode and not self.last_error:
                    self.last_error = f"{label} exited with code {returncode}: {stderr.strip()}"
                self._notify()

    def _apply_event_to_framebuffer(
        self,
        framebuffer: bytearray,
        event: dict,
    ) -> None:
        if event["kind"] == 1:
            page = event["page"]
            column = event["column"]
            if 0 <= page < 8 and 0 <= column < 132:
                framebuffer[page * 132 + column] = event["value"]
        elif event["value"] == 0xE2:
            framebuffer[:] = b"\0" * len(framebuffer)

    def stop(self, user_initiated: bool = False) -> dict:
        with self.lock:
            if user_initiated:
                self.auto_reconnect = False
            capture = self.capture
            decoder = self.decoder
            self.capture = None
            self.decoder = None
            self.running = False
            self._notify()
        for process in (capture, decoder):
            if process is None:
                continue
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        return self.status()


LIVE = LiveCapture()


def load_project_settings() -> dict:
    with SETTINGS_LOCK:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        variants_data = json.loads(VARIANTS_PATH.read_text(encoding="utf-8")) if VARIANTS_PATH.exists() else {}
        calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8")) if CALIBRATION_PATH.exists() else {}
    return {
        "settings": settings,
        "variants": variants_data.get("variants", {}),
        "activeVariant": settings.get("activeVariant", "v2"),
        "templates": calibration.get("symbols", {}),
    }


def save_project_variant(payload: dict) -> dict:
    variant_id = payload.get("variant", "").lower().strip()
    if variant_id not in ("v1", "v2"):
        raise ValueError(f"Invalid variant id '{variant_id}'. Expected 'v1' or 'v2'.")
    with SETTINGS_LOCK:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        variants_data = json.loads(VARIANTS_PATH.read_text(encoding="utf-8")) if VARIANTS_PATH.exists() else {}
        v_info = variants_data.get("variants", {}).get(variant_id, {})
        settings["activeVariant"] = variant_id
        if "visibleColumnStart" in v_info:
            settings.setdefault("display", {})["visibleColumnStart"] = v_info["visibleColumnStart"]
        if "pageMapping" in v_info:
            settings.setdefault("display", {})["pageMapping"] = v_info["pageMapping"]
        if "colors" in v_info:
            settings.setdefault("display", {})["colors"] = v_info["colors"]
        if "activeColorPreset" in v_info:
            settings.setdefault("display", {})["activeColorPreset"] = v_info["activeColorPreset"]
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return {
        "success": True,
        "activeVariant": variant_id,
        "settings": settings,
    }


def save_project_recognition(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Recognition settings must be a JSON object")
    raw_templates = payload.get("templates", {})
    if not isinstance(raw_templates, dict):
        raise ValueError("Invalid recognition templates")
    with SETTINGS_LOCK:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8")) if CALIBRATION_PATH.exists() else {}
        calibration["symbols"] = raw_templates
        CALIBRATION_PATH.write_text(json.dumps(calibration, indent=2), encoding="utf-8")
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return {"success": True}


def save_display_colors(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Display colors must be a JSON object")
    colors = payload.get("colors")
    active_preset = payload.get("activeColorPreset")
    with SETTINGS_LOCK:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        display = settings.setdefault("display", {})
        if isinstance(colors, dict):
            display["colors"] = colors
        if isinstance(active_preset, str) and active_preset:
            display["activeColorPreset"] = active_preset
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return {"success": True, "display": display}


def compile_decoder() -> None:
    if BINARY.exists() and BINARY.stat().st_mtime_ns >= C_SOURCE.stat().st_mtime_ns:
        return
    subprocess.run(
        ["gcc", "-O2", "-Wall", "-Wextra", "-o", str(BINARY), str(C_SOURCE)],
        check=True,
        capture_output=True,
        text=True,
    )


class Handler(SimpleHTTPRequestHandler):
    """Custom request handler with SSE and REST endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_sse_event(self, event: str, payload: object) -> None:
        body = json.dumps(payload, separators=(",", ":"))
        self.wfile.write(f"event: {event}\ndata: {body}\n\n".encode())
        self.wfile.flush()

    def stream_live_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        snapshot = LIVE.snapshot()
        last_sequence = snapshot["sequence"]
        last_version = snapshot["status"]["version"]
        try:
            self.send_sse_event("snapshot", snapshot)
            while True:
                with LIVE.changed:
                    LIVE.changed.wait_for(
                        lambda: LIVE.version != last_version,
                        timeout=15,
                    )
                    status = LIVE._status_unlocked()
                    current_version = LIVE.version
                    events = [
                        event for event in LIVE.events
                        if event["seq"] > last_sequence
                    ]
                    first_sequence = LIVE.events[0]["seq"] if LIVE.events else None
                    fell_behind = (
                        first_sequence is not None
                        and last_sequence < first_sequence - 1
                    )
                    if fell_behind:
                        payload = {
                            "status": status,
                            "framebuffer": list(LIVE.framebuffer),
                            "baseFramebuffer": list(LIVE.buffer_base_framebuffer),
                            "events": list(LIVE.events),
                            "sequence": LIVE.sequence,
                            "captureEpoch": LIVE.capture_epoch,
                        }
                    else:
                        payload = {
                            "status": status,
                            "events": events,
                            "sequence": LIVE.sequence,
                            "captureEpoch": LIVE.capture_epoch,
                        }
                    last_sequence = LIVE.sequence
                    last_version = current_version
                if fell_behind:
                    self.send_sse_event("snapshot", payload)
                elif events or current_version != snapshot["status"]["version"]:
                    self.send_sse_event("events", payload)
                else:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                snapshot["status"]["version"] = current_version
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/lcd_decoder_light.html"):
            html_path = STATIC_DIR / "lcd_decoder_light.html"
            if html_path.exists():
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(html_path.stat().st_size))
                self.end_headers()
                with html_path.open("rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
        if parsed.path in ("/lcd_decoder_worker.js", "/static/lcd_decoder_worker.js"):
            js_path = STATIC_DIR / "lcd_decoder_worker.js"
            if js_path.exists():
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(js_path.stat().st_size))
                self.end_headers()
                with js_path.open("rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return
        if parsed.path in ("/lcd_trace.js", "/static/lcd_trace.js"):
            js_path = STATIC_DIR / "lcd_trace.js"
            if js_path.exists():
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", str(js_path.stat().st_size))
                self.end_headers()
                with js_path.open("rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                return

        if parsed.path == "/api/settings":
            try:
                self.send_json(load_project_settings())
            except Exception as error:
                self.send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/variants":
            try:
                variants = json.loads(VARIANTS_PATH.read_text(encoding="utf-8")) if VARIANTS_PATH.exists() else {}
                self.send_json(variants)
            except Exception as error:
                self.send_json({"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/live/devices":
            try:
                self.send_json({"devices": scan_sigrok_devices()})
            except RuntimeError as error:
                self.send_json({"error": str(error)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if parsed.path == "/api/live/status":
            self.send_json(LIVE.status())
            return
        if parsed.path == "/api/live/snapshot":
            self.send_json(LIVE.snapshot())
            return
        if parsed.path == "/api/live/events":
            self.stream_live_events()
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        valid_paths = (
            "/api/live/start",
            "/api/live/stop",
            "/api/settings/variant",
            "/api/settings/recognition",
            "/api/settings/display-colors",
        )
        if parsed.path not in valid_paths:
            self.send_json({"error": "Unknown API endpoint"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_048_576:
                raise ValueError("Request body is too large")
            payload = json.loads(self.rfile.read(length) or b"{}")

            if parsed.path == "/api/settings/variant":
                self.send_json(save_project_variant(payload))
                return
            if parsed.path == "/api/settings/recognition":
                self.send_json(save_project_recognition(payload))
                return
            if parsed.path == "/api/settings/display-colors":
                self.send_json(save_display_colors(payload))
                return
            if parsed.path == "/api/live/start":
                status = LIVE.start(
                    str(payload.get("driver", "fx2lafw")),
                    int(payload.get("sampleRate", 4_000_000)),
                    int(payload.get("bufferSize", LIVE_BUFFER_DEFAULT)),
                    payload.get("framebuffer"),
                )
            else:
                status = LIVE.stop(user_initiated=True)
            self.send_json(status)
        except Exception as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)


class DecoderHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--variant", choices=["v1", "v2"], help="Force active display variant")
    args = parser.parse_args()

    compile_decoder()

    if args.variant:
        save_project_variant({"variant": args.variant})
        print(f"[Init] Variant forced via CLI: {args.variant}")

    server = DecoderHTTPServer((args.host, args.port), Handler)
    print(f"ST7565 LCD Decoder listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LIVE.stop(user_initiated=True)
        server.server_close()


if __name__ == "__main__":
    main()
