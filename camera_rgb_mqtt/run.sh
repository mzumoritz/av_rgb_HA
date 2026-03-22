#!/bin/bash

echo "[INFO] Starte Camera RGB → MQTT..."

OPTIONS_FILE="/data/options.json"

export RTSP_URL=$(jq -r '.rtsp_url' $OPTIONS_FILE)
export TARGET_FPS=$(jq -r '.target_fps' $OPTIONS_FILE)
export MQTT_HOST=$(jq -r '.mqtt_host' $OPTIONS_FILE)
export MQTT_PORT=$(jq -r '.mqtt_port' $OPTIONS_FILE)
export MQTT_USERNAME=$(jq -r '.mqtt_username' $OPTIONS_FILE)
export MQTT_PASSWORD=$(jq -r '.mqtt_password' $OPTIONS_FILE)
export MQTT_TOPIC=$(jq -r '.mqtt_topic' $OPTIONS_FILE)

echo "[INFO] RTSP-URL:  $RTSP_URL"
echo "[INFO] Ziel-FPS:  $TARGET_FPS"
echo "[INFO] MQTT:      $MQTT_HOST:$MQTT_PORT"
echo "[INFO] Topic:     $MQTT_TOPIC"

python3 /camera_rgb.py