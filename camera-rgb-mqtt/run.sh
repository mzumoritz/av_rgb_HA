#!/usr/bin/with-contenv bashio

bashio::log.info "Starte Camera RGB → MQTT (RTSP-Modus, 15 fps)..."

export RTSP_URL=$(bashio::config 'rtsp_url')
export TARGET_FPS=$(bashio::config 'target_fps')
export MQTT_HOST=$(bashio::config 'mqtt_host')
export MQTT_PORT=$(bashio::config 'mqtt_port')
export MQTT_USERNAME=$(bashio::config 'mqtt_username')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
export MQTT_TOPIC=$(bashio::config 'mqtt_topic')

bashio::log.info "RTSP-URL:   ${RTSP_URL}"
bashio::log.info "Ziel-FPS:   ${TARGET_FPS}"
bashio::log.info "MQTT:       ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "Topic:      ${MQTT_TOPIC}"

python3 /camera_rgb.py
