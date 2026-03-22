ARG BUILD_FROM
FROM $BUILD_FROM

# System-Abhängigkeiten für OpenCV (headless reicht, kein Display nötig)
RUN apk add --no-cache \
    ffmpeg \
    libstdc++ \
    libgomp \
    && pip3 install --no-cache-dir \
        opencv-python-headless==4.9.0.80 \
        paho-mqtt==1.6.1 \
        numpy==1.26.4

COPY camera_rgb.py /
COPY run.sh /

RUN chmod +x /run.sh

CMD ["/run.sh"]
