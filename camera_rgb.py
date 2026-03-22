#!/usr/bin/env python3
"""
Camera RGB → MQTT Add-on  (v2 – RTSP direkt via OpenCV)
Liest den RTSP-Stream einer Kamera, berechnet den Durchschnitts-RGB-Wert
und sendet ihn mit bis zu 15 fps per MQTT an Home Assistant.

Warum OpenCV statt HA camera_proxy?
  - camera_proxy gibt nur ~1–5 fps (gecachter Snapshot-Endpunkt)
  - OpenCV greift native auf den H.264/H.265-Stream zu → echte 15–30 fps möglich
"""

import os
import json
import time
import signal
import sys
import logging
import threading

import cv2
import numpy as np
import paho.mqtt.client as mqtt

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------
# Konfiguration aus Umgebungsvariablen (gesetzt von run.sh)
# ---------------------------------------------------------
RTSP_URL     = os.environ.get("RTSP_URL",     "rtsp://192.168.1.100:554/stream")
TARGET_FPS   = int(os.environ.get("TARGET_FPS", 15))
MQTT_HOST    = os.environ.get("MQTT_HOST",    "core-mosquitto")
MQTT_PORT    = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USERNAME= os.environ.get("MQTT_USERNAME","")
MQTT_PASSWORD= os.environ.get("MQTT_PASSWORD","")
MQTT_TOPIC   = os.environ.get("MQTT_TOPIC",   "homeassistant/sensor/camera_rgb/state")

# Ziel-Frameinterval in Sekunden (z.B. 1/15 ≈ 66,7 ms)
FRAME_INTERVAL = 1.0 / max(1, TARGET_FPS)

DEVICE_ID        = "camera_rgb_addon"
DISCOVERY_PREFIX = "homeassistant"

# ---------------------------------------------------------
# MQTT Discovery
# ---------------------------------------------------------
DISCOVERY_SENSORS = [
    {
        "suffix": "r",
        "name":   "Camera RGB – Rot",
        "icon":   "mdi:palette",
        "value_template": "{{ value_json.r }}",
    },
    {
        "suffix": "g",
        "name":   "Camera RGB – Grün",
        "icon":   "mdi:palette",
        "value_template": "{{ value_json.g }}",
    },
    {
        "suffix": "b",
        "name":   "Camera RGB – Blau",
        "icon":   "mdi:palette",
        "value_template": "{{ value_json.b }}",
    },
    {
        "suffix": "hex",
        "name":   "Camera RGB – Hex",
        "icon":   "mdi:eyedropper-variant",
        "value_template": "{{ value_json.hex }}",
    },
    {
        "suffix": "brightness",
        "name":   "Camera RGB – Helligkeit",
        "icon":   "mdi:brightness-6",
        "value_template": "{{ value_json.brightness }}",
    },
]


def publish_discovery(client: mqtt.Client) -> None:
    for sensor in DISCOVERY_SENSORS:
        uid          = f"{DEVICE_ID}_{sensor['suffix']}"
        config_topic = f"{DISCOVERY_PREFIX}/sensor/{uid}/config"
        payload = {
            "name":           sensor["name"],
            "unique_id":      uid,
            "state_topic":    MQTT_TOPIC,
            "value_template": sensor["value_template"],
            "icon":           sensor["icon"],
            "device": {
                "identifiers":  [DEVICE_ID],
                "name":         "Camera RGB Add-on",
                "model":        "Camera RGB → MQTT v2",
                "manufacturer": "HA Add-on",
            },
        }
        client.publish(config_topic, json.dumps(payload), retain=True)
    log.info("MQTT Discovery-Nachrichten gesendet.")


# ---------------------------------------------------------
# MQTT-Client
# ---------------------------------------------------------
def build_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(client_id=DEVICE_ID, clean_session=True)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    def on_connect(c, userdata, flags, rc):
        if rc == 0:
            log.info(f"MQTT verbunden mit {MQTT_HOST}:{MQTT_PORT}")
            publish_discovery(c)
        else:
            log.error(f"MQTT-Verbindungsfehler, Code: {rc}")

    def on_disconnect(c, userdata, rc):
        if rc != 0:
            log.warning(f"MQTT getrennt (rc={rc}), reconnect läuft…")

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    return client


# ---------------------------------------------------------
# RGB-Berechnung mit NumPy (sehr schnell, <1 ms)
# ---------------------------------------------------------
def calculate_average_rgb(frame_bgr: np.ndarray) -> dict:
    """
    frame_bgr: OpenCV-Frame im BGR-Format (H×W×3, uint8)
    Gibt R, G, B (0–255), Helligkeit und Hex-String zurück.
    """
    # Auf 100×100 verkleinern, danach Durchschnitt über alle Pixel
    small = cv2.resize(frame_bgr, (100, 100), interpolation=cv2.INTER_AREA)
    # NumPy-Mittelwert über H und W → Ergebnis: [B_avg, G_avg, R_avg]
    mean_bgr = small.mean(axis=(0, 1))

    b = int(round(mean_bgr[0]))
    g = int(round(mean_bgr[1]))
    r = int(round(mean_bgr[2]))

    # Wahrgenommene Helligkeit (ITU-R BT.601)
    brightness = int(round(0.299 * r + 0.587 * g + 0.114 * b))
    hex_color  = f"#{r:02X}{g:02X}{b:02X}"

    return {"r": r, "g": g, "b": b, "brightness": brightness, "hex": hex_color}


# ---------------------------------------------------------
# RTSP-Reader-Thread
# Liest Frames im Hintergrund, sodass cv2.read() nie blockiert.
# Ohne diesen Thread würde der Hauptloop den internen Frame-Buffer
# nicht schnell genug leeren → wachsende Latenz.
# ---------------------------------------------------------
class RTSPReader:
    def __init__(self, url: str):
        self.url    = url
        self._frame = None
        self._lock  = threading.Lock()
        self._stop  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _run(self):
        cap = None
        while not self._stop.is_set():
            if cap is None or not cap.isOpened():
                log.info(f"Verbinde mit RTSP-Stream: {self.url}")
                # FFMPEG als Backend – stabiler für RTSP als GStreamer
                cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimaler Buffer → geringe Latenz
                if not cap.isOpened():
                    log.warning("RTSP-Verbindung fehlgeschlagen, erneuter Versuch in 5 s…")
                    time.sleep(5)
                    cap = None
                    continue
                log.info("RTSP-Stream verbunden.")

            ok, frame = cap.read()
            if not ok:
                log.warning("Frame-Lesefehler, reconnect…")
                cap.release()
                cap = None
                time.sleep(2)
                continue

            with self._lock:
                self._frame = frame

        if cap and cap.isOpened():
            cap.release()
        log.info("RTSP-Reader-Thread beendet.")


# ---------------------------------------------------------
# Graceful Shutdown
# ---------------------------------------------------------
_running = True

def _shutdown(sig, frame):
    global _running
    log.info("Beende Add-on…")
    _running = False

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)


# ---------------------------------------------------------
# Hauptschleife
# ---------------------------------------------------------
def main():
    log.info(f"Ziel: {TARGET_FPS} fps  →  Frameinterval: {FRAME_INTERVAL*1000:.1f} ms")

    # MQTT starten
    mqtt_client = build_mqtt_client()
    mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()

    # RTSP-Reader im Hintergrund starten
    reader = RTSPReader(RTSP_URL)
    reader.start()

    # Warte kurz, bis der erste Frame da ist
    time.sleep(2)

    frame_count   = 0
    error_count   = 0
    last_fps_log  = time.monotonic()

    while _running:
        t_start = time.monotonic()

        frame = reader.get_frame()

        if frame is None:
            # Noch kein Frame → kurz warten
            time.sleep(0.05)
            continue

        try:
            rgb_data = calculate_average_rgb(frame)
            payload  = json.dumps(rgb_data)
            result   = mqtt_client.publish(MQTT_TOPIC, payload, retain=False)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                frame_count += 1
            else:
                log.warning(f"MQTT publish fehlgeschlagen (rc={result.rc})")
                error_count += 1

        except Exception as exc:
            log.error(f"Fehler bei RGB-Verarbeitung: {exc}")
            error_count += 1

        # FPS-Log alle 10 Sekunden
        now = time.monotonic()
        if now - last_fps_log >= 10.0:
            elapsed    = now - last_fps_log
            actual_fps = frame_count / elapsed
            log.info(
                f"fps: {actual_fps:.1f}  |  Fehler: {error_count}  |  "
                f"Letzter Wert: R:{rgb_data['r']} G:{rgb_data['g']} "
                f"B:{rgb_data['b']}  {rgb_data['hex']}"
            )
            frame_count  = 0
            error_count  = 0
            last_fps_log = now

        # Präzises Throttling: verbleibende Zeit bis zum nächsten Frame schlafen
        elapsed = time.monotonic() - t_start
        sleep_time = FRAME_INTERVAL - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Aufräumen
    reader.stop()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    log.info("Add-on sauber beendet.")


if __name__ == "__main__":
    main()
