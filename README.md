# Camera RGB → MQTT – Home Assistant Add-on (v2)

Liest einen **RTSP-Kamerastream direkt** (kein HA-Umweg), berechnet den
Durchschnitts-RGB-Wert pro Frame und sendet ihn mit bis zu **15 fps** per MQTT.

---

## Warum RTSP statt `camera_proxy`?

| Methode | Erreichbare fps | Grund |
|---|---|---|
| HA `camera_proxy` API | 1–5 fps | HTTP-Overhead, HA cached den Frame |
| **RTSP direkt (OpenCV)** | **bis 30 fps** | Nativer H.264/H.265-Stream |

---

## Sensoren (automatisch via MQTT Discovery)

| Sensor | Beschreibung |
|---|---|
| `Camera RGB – Rot` | Durchschnittlicher Rotwert (0–255) |
| `Camera RGB – Grün` | Durchschnittlicher Grünwert (0–255) |
| `Camera RGB – Blau` | Durchschnittlicher Blauwert (0–255) |
| `Camera RGB – Hex` | Farbcode, z. B. `#A3C27F` |
| `Camera RGB – Helligkeit` | Wahrgenommene Helligkeit (0–255) |

---

## Installation

### Lokales Sideload (empfohlen zum Testen)

1. Ordner `camera-rgb-mqtt/` nach `/addons/camera-rgb-mqtt/` auf dem HA-Host kopieren  
   (via SSH Add-on oder Samba Add-on)
2. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories neu laden**
3. Add-on erscheint im Store unter „Lokale Add-ons"

---

## Konfiguration

```yaml
rtsp_url: "rtsp://192.168.1.100:554/stream"  # RTSP-URL deiner Kamera
target_fps: 15                                # Ziel-Framerate (max. = Kamera-fps)
mqtt_host: "core-mosquitto"                   # Bei Mosquitto Add-on: core-mosquitto
mqtt_port: 1883
mqtt_username: ""                             # Leer lassen wenn kein Auth nötig
mqtt_password: ""
mqtt_topic: "homeassistant/sensor/camera_rgb/state"
```

### RTSP-URL ermitteln

| Kamera | Typisches URL-Muster |
|---|---|
| Reolink | `rtsp://user:pass@IP:554/h264Preview_01_main` |
| Hikvision | `rtsp://user:pass@IP:554/Streaming/Channels/101` |
| Dahua | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Frigate (HA Add-on) | `rtsp://IP:8554/camera_name` |
| go2rtc (HA Add-on) | `rtsp://IP:8554/camera_name` |

---

## MQTT-Payload (Beispiel)

```json
{ "r": 142, "g": 98, "b": 61, "brightness": 107, "hex": "#8E623D" }
```

---

## Architektur

```
RTSP-Kamera
    │  H.264/H.265-Stream
    ▼
RTSPReader-Thread  ──────────────────────────────────────────┐
  cv2.VideoCapture (FFMPEG-Backend)                          │
  cap.set(BUFFERSIZE, 1) → minimale Latenz                   │
  Frame wird in self._frame (mit Lock) abgelegt              │
                                                             │
Hauptloop (15 fps-Takt)  ◄────── get_frame() ───────────────┘
  1. Frame auf 100×100 skalieren  (cv2.resize, INTER_AREA)
  2. NumPy-Mittelwert über alle Pixel  (mean axis 0,1)
  3. BGR → RGB konvertieren
  4. Helligkeit (BT.601), Hex-Code berechnen
  5. JSON serialisieren
  6. MQTT publish
  7. Präzises sleep bis zum nächsten Frame-Slot
```

---

## Dateistruktur

```
camera-rgb-mqtt/
├── config.yaml       # Add-on-Metadaten & Schema
├── Dockerfile        # OpenCV-headless + paho-mqtt + numpy
├── run.sh            # Liest HA-Optionen, startet Python
└── camera_rgb.py     # RTSP-Reader-Thread + RGB-Loop + MQTT
```

---

## Voraussetzungen

- Home Assistant OS oder Supervised
- Mosquitto Broker Add-on (oder externer MQTT-Broker)
- Kamera mit RTSP-Stream (praktisch jede IP-Kamera)
- **Kein** `homeassistant_api` nötig – das Add-on kommuniziert direkt mit der Kamera
