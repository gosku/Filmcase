#!/usr/bin/env bash
#
# Container entrypoint. Prepares the writable volumes and the TLS certificate, then hands
# off to either the web server or a Celery worker.
#
# Usage (as the container command):
#   web      start gunicorn over HTTPS, after applying migrations
#   worker   start a Celery worker
#   <other>  run the given command verbatim, as the unprivileged user
#
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
FILMCASE_HOST="${FILMCASE_HOST:-localhost}"
FILMCASE_HTTPS_PORT="${FILMCASE_HTTPS_PORT:-8443}"

CERT_DIR="${FILMCASE_CERT_DIR:-/certs}"
CERT_FILE="$CERT_DIR/filmcase.crt"
KEY_FILE="$CERT_DIR/filmcase.key"

log() { echo "[entrypoint] $*"; }

# Docker creates named volumes owned by root, so ownership is fixed here while still root,
# before dropping to the account that actually runs the app.
#
# The small directories are always chowned recursively. They hold a handful of files, and
# changing PUID between runs otherwise leaves a root-owned events.jsonl or key file that the
# app can no longer open, which kills it at startup before anything is logged.
#
# The bulk directories are only chowned recursively when the directory itself has the wrong
# owner, which is the boot after a PUID change. A populated thumbnail cache can hold tens of
# thousands of files, and paying for that walk on every boot would cost minutes for nothing.
prepare_directories() {
    for dir in "$CERT_DIR" /app/logs; do
        mkdir -p "$dir"
        chown -R "$PUID:$PGID" "$dir"
    done

    for dir in /app/thumbnail_cache /app/recipe_cards; do
        mkdir -p "$dir"
        if [ "$(stat -c '%u:%g' "$dir" 2>/dev/null)" != "$PUID:$PGID" ]; then
            log "Fixing ownership of $dir for $PUID:$PGID"
            chown -R "$PUID:$PGID" "$dir"
        fi
    done
}

# A self-signed certificate is enough to reach a secure context, which is what WebUSB and
# the other powerful browser APIs actually test for: the check is on the origin's scheme,
# not on whether the chain is trusted. Browsers still show a full-page interstitial that
# has to be accepted once per browser, which is the documented cost of not owning a domain.
#
# The address users type must appear in the subjectAltName. Modern browsers ignore CN
# entirely, and an IP needs an IP: SAN rather than a DNS: one.
generate_certificate() {
    if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
        log "Reusing the certificate in $CERT_DIR"
        return
    fi

    local san
    if echo "$FILMCASE_HOST" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
        san="IP:$FILMCASE_HOST"
    else
        san="DNS:$FILMCASE_HOST"
    fi

    log "Generating a self-signed certificate for $FILMCASE_HOST ($san)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/CN=$FILMCASE_HOST" \
        -addext "subjectAltName=$san" \
        >/dev/null 2>&1

    chown "$PUID:$PGID" "$CERT_FILE" "$KEY_FILE"
    chmod 640 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
}

# Compose may pin the container to a specific account with `user:`, in which case there are
# no privileges to drop and nothing to chown. Run the command directly in that case.
run_as_app_user() {
    if [ "$(id -u)" = "0" ]; then
        exec gosu "$PUID:$PGID" "$@"
    fi
    exec "$@"
}

if [ "$(id -u)" = "0" ]; then
    prepare_directories
    generate_certificate
fi

case "${1:-web}" in
    web)
        log "Applying migrations"
        if [ "$(id -u)" = "0" ]; then
            gosu "$PUID:$PGID" python manage.py migrate --noinput
        else
            python manage.py migrate --noinput
        fi

        log "Starting gunicorn on https://$FILMCASE_HOST:$FILMCASE_HTTPS_PORT/"
        run_as_app_user gunicorn src.config.wsgi:application \
            --bind "0.0.0.0:$FILMCASE_HTTPS_PORT" \
            --certfile "$CERT_FILE" \
            --keyfile "$KEY_FILE" \
            --workers "${FILMCASE_WEB_WORKERS:-3}" \
            --timeout "${FILMCASE_WEB_TIMEOUT:-120}" \
            --access-logfile -
        ;;
    worker)
        log "Starting Celery worker"
        run_as_app_user celery -A src.config worker \
            --loglevel=info \
            --concurrency="${FILMCASE_WORKER_CONCURRENCY:-8}"
        ;;
    *)
        run_as_app_user "$@"
        ;;
esac
