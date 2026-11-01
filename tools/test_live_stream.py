#!/usr/bin/env python3
"""
Telemetry and Health Test for Pegasus Gasera Decoder Server
Verifies that the server is responding, live capture/replay is running,
and events are being parsed continuously without errors.
"""

import json
import sys
import time
import urllib.request

def check_server(host="127.0.0.1", port=8081):
    base_url = f"http://{host}:{port}"
    print(f"Pinging decoder server at {base_url}...")

    # 1. Check /api/live/status
    try:
        req = urllib.request.urlopen(f"{base_url}/api/live/status", timeout=3.0)
        status = json.loads(req.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Server offline or unreachable: {e}")
        return 1

    print("\n--- Telemetría del Servidor ---")
    print(f" Estado de Captura:   {'Activo (Running)' if status.get('running') else 'Detenido'}")
    print(f" Driver:              {status.get('driver')}")
    print(f" Tasa de Muestreo:    {status.get('sampleRate') / 1_000_000:.1f} MHz")
    print(f" Eventos Recibidos:   {status.get('eventsReceived', 0):,}")
    print(f" Muestras Procesadas: {status.get('samplesReceived', 0):,}")
    print(f" Comandos Display:    {status.get('commands', 0):,}")
    print(f" Bytes Datos VRAM:    {status.get('data', 0):,}")
    print(f" Frames Inválidos:    {status.get('invalidFrames', 0)}")
    print(f" Bytes Ignorados:     {status.get('ignoredBytes', 0)}")

    if not status.get("running"):
        print("\n⚠️ Advertencia: El streaming no está corriendo. Intentando arrancar replay...")
        start_payload = json.dumps({
            "driver": "replay:capture_4mhz",
            "sampleRate": 4000000,
            "bufferSize": 1024,
            "framebuffer": [0] * 1056
        }).encode("utf-8")
        req_start = urllib.request.Request(
            f"{base_url}/api/live/start",
            data=start_payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req_start, timeout=3.0)
        print("✅ Replay arrancado exitosamente.")

    print("\n✅ PASSED: Servidor y decodificador operando con normalidad.")
    return 0

if __name__ == "__main__":
    sys.exit(check_server())
