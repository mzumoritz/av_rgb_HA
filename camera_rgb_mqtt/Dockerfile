FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
        jq \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir \
        opencv-python-headless==4.9.0.80 \
        paho-mqtt==1.6.1 \
        numpy==1.26.4

COPY camera_rgb.py /
COPY run.sh /

RUN chmod +x /run.sh

CMD ["/run.sh"]