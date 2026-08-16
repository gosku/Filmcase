FROM python:3.12-slim

# exiftool is not optional: the import pipeline shells out to it for every recipe field
# (src/domain/images/queries.py), so without it the container cannot do the one thing it
# exists for. libusb only matters when a camera is passed through to the container, which
# a NAS install never does; it is kept because it costs ~100KB and keeps the desktop
# passthrough deployment working. openssl generates the self-signed certificate on first
# run, and gosu drops privileges once the entrypoint has fixed ownership on the volumes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libimage-exiftool-perl \
        libusb-1.0-0 \
        openssl \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# settings.py reads src/config/env unless told otherwise, and that file is the developer's
# personal configuration. Pointing at os.devnull is the documented way to ignore it and run
# purely on environment variables, which is what compose supplies.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FILMCASE_ENV_FILE=/dev/null \
    DJANGO_SETTINGS_MODULE=src.config.settings

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8443

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
