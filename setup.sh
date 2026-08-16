#!/usr/bin/env bash
# Installs system-level dependencies for film_simulations_reader.
#
# Usage:
#   ./setup.sh          # full stack (PostgreSQL + RabbitMQ + Celery)
#   ./setup.sh lite     # lite install (SQLite, no broker/worker)
#   ./setup.sh full     # same as default
#   ./setup.sh docker   # containerised install: configure .env and the compose override
#
# Idempotent: skips anything already installed or running. Docker mode reads any existing
# configuration back as the defaults, so re-running it to change one answer is safe.
#
# Supports macOS (Homebrew) and Ubuntu/Debian (apt). Docker mode additionally runs anywhere
# with bash and Docker, because the container carries every dependency the other two
# modes install on the host.
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[setup]${NC} $*"; }
skip() { echo -e "${YELLOW}[skip] ${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

# ── Mode ───────────────────────────────────────────────────────────────────────
MODE="${1:-full}"
if [[ "$MODE" != "lite" && "$MODE" != "full" && "$MODE" != "docker" ]]; then
    die "Unknown mode '$MODE'. Use 'lite', 'full' or 'docker'."
fi

if [[ "$MODE" == "lite" ]]; then
    echo ""
    echo "  Lite install — SQLite, sequential processing."
    echo "  Installing: Python, libusb, exiftool."
    echo "  Skipping:   PostgreSQL, RabbitMQ."
    echo "  Run 'make setup-lite' after this script completes."
elif [[ "$MODE" == "docker" ]]; then
    echo ""
    echo "  Docker install — PostgreSQL + RabbitMQ + Celery, all in containers."
    echo "  Installing: nothing on this host; the image carries every dependency."
    echo "  Configuring: .env and docker-compose.override.yml, from your answers below."
else
    echo ""
    echo "  Full install — PostgreSQL + Celery, parallel processing."
    echo "  Installing: Python, libusb, exiftool, PostgreSQL, RabbitMQ."
    echo "  Run 'make setup-full' after this script completes."
fi
echo ""

# ── Detect OS ──────────────────────────────────────────────────────────────────
# Docker mode tolerates an unrecognised OS: it installs nothing on the host, so bash and
# Docker are the only requirements. That matters because a NAS or appliance OS is often
# neither macOS nor Ubuntu, and is exactly where the containerised install is most useful.
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ -f /etc/os-release ]] && grep -qi 'ubuntu\|debian' /etc/os-release; then
    OS="ubuntu"
else
    OS="other"
fi

if [[ "$OS" == "other" && "$MODE" != "docker" ]]; then
    die "Unsupported OS. The '$MODE' install supports macOS and Ubuntu/Debian."
fi
info "Detected OS: $OS"

# ── macOS helpers ──────────────────────────────────────────────────────────────
brew_install() {
    local pkg="$1"
    if brew list "$pkg" &>/dev/null; then
        skip "$pkg already installed"
    else
        info "Installing $pkg via Homebrew..."
        brew install "$pkg"
    fi
}

brew_start() {
    local svc="$1"
    if brew services list | awk '{print $1, $2}' | grep -q "^$svc started"; then
        skip "$svc service already running"
    else
        info "Starting $svc service..."
        brew services start "$svc"
    fi
}

# ── Ubuntu helpers ─────────────────────────────────────────────────────────────
apt_install() {
    local pkg="$1"
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
        skip "$pkg already installed"
    else
        info "Installing $pkg via apt..."
        sudo apt-get install -y "$pkg"
    fi
}

systemd_start() {
    local svc="$1"
    if systemctl is-active --quiet "$svc"; then
        skip "$svc already running"
    else
        info "Starting $svc..."
        sudo systemctl enable --now "$svc"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Docker mode
#
# Writes .env and docker-compose.override.yml from answers, then optionally starts the
# stack. Nothing else in this script runs afterwards: the image already carries Python,
# exiftool, PostgreSQL and RabbitMQ, so there is nothing to install on the host.
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "docker" ]]; then
    ENV_FILE=".env"
    OVERRIDE_FILE="docker-compose.override.yml"

    # Prompts read from the terminal rather than stdin so the script still works when piped.
    ask() {
        local __var="$1" prompt="$2" default="$3" reply=""
        if [[ -n "$default" ]]; then
            read -r -p "  $prompt [$default]: " reply </dev/tty || true
        else
            read -r -p "  $prompt: " reply </dev/tty || true
        fi
        printf -v "$__var" '%s' "${reply:-$default}"
    }

    confirm() {
        local reply=""
        read -r -p "  $1 [Y/n]: " reply </dev/tty || true
        [[ -z "$reply" || "$reply" =~ ^[Yy] ]]
    }

    # Existing answers become the defaults, so re-running to change one thing does not mean
    # retyping the rest.
    env_value() {
        [[ -f "$ENV_FILE" ]] || return 0
        grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-
    }

    # env_value succeeds even when the key is absent, so a `||` fallback would never fire.
    # This picks the fallback on empty output instead.
    env_default() {
        local value
        value="$(env_value "$1")"
        echo "${value:-$2}"
    }

    existing_photo_dirs() {
        [[ -f "$OVERRIDE_FILE" ]] || return 0
        grep -oE '^ +- [^:]+:[^:]+:ro$' "$OVERRIDE_FILE" 2>/dev/null \
            | sed -E 's/^ +- ([^:]+):.*/\1/' | awk '!seen[$0]++'
    }

    detect_lan_ip() {
        local ip=""
        if command -v ip &>/dev/null; then
            ip=$(ip -4 route get 1.1.1.1 2>/dev/null \
                 | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}')
        fi
        if [[ -z "$ip" ]] && command -v ipconfig &>/dev/null; then
            ip=$(ipconfig getifaddr en0 2>/dev/null || true)
        fi
        if [[ -z "$ip" ]] && command -v hostname &>/dev/null; then
            ip=$(hostname -I 2>/dev/null | awk '{print $1}')
        fi
        echo "${ip:-localhost}"
    }

    cpu_count() {
        if command -v nproc &>/dev/null; then
            nproc
        elif command -v sysctl &>/dev/null; then
            sysctl -n hw.ncpu 2>/dev/null || echo 2
        else
            echo 2
        fi
    }

    port_in_use() {
        if command -v ss &>/dev/null; then
            ss -tln 2>/dev/null | grep -q ":$1 "
        elif command -v lsof &>/dev/null; then
            lsof -iTCP:"$1" -sTCP:LISTEN &>/dev/null
        else
            return 1
        fi
    }

    # Generated rather than prompted. openssl is present on macOS and Linux alike;
    # /dev/urandom covers whatever is left, so the host never needs Python.
    generate_secret() {
        if command -v openssl &>/dev/null; then
            openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-50
        else
            head -c 64 /dev/urandom | base64 | tr -d '\n=+/' | cut -c1-50
        fi
    }

    # ── Docker itself ──────────────────────────────────────────────────────────
    info "Checking Docker..."
    if ! command -v docker &>/dev/null; then
        if [[ "$OS" == "ubuntu" ]]; then
            echo ""
            if confirm "Docker is not installed. Install docker.io and docker-compose-v2 now?"; then
                sudo apt-get update -qq
                apt_install docker.io
                apt_install docker-compose-v2
                if ! id -nG "$USER" | grep -qw docker; then
                    info "Adding $USER to the docker group..."
                    sudo usermod -aG docker "$USER"
                fi
                echo ""
                info "Docker installed. Log out and back in for the group change to apply,"
                info "then re-run './setup.sh docker'."
                exit 0
            fi
            die "Docker is required for this mode."
        elif [[ "$OS" == "macos" ]]; then
            die "Docker is required. Install Docker Desktop from https://docker.com/products/docker-desktop"
        else
            die "Docker is required. Install it from your platform's package manager, or from the
       container package your NAS provides."
        fi
    fi
    skip "docker $(docker --version | awk '{print $3}' | tr -d ,) present"

    if ! docker compose version &>/dev/null; then
        die "Docker Compose v2 is required ('docker compose', not 'docker-compose').
       On Ubuntu:  sudo apt install docker-compose-v2
       Elsewhere:  update Docker to a release that ships Compose v2."
    fi
    skip "compose $(docker compose version --short 2>/dev/null || echo v2) present"

    if ! docker info &>/dev/null; then
        die "Cannot reach the Docker daemon. Is it running, and is $USER in the docker group?
       Add yourself with:  sudo usermod -aG docker $USER   (then log out and back in)"
    fi

    # ── Questions ──────────────────────────────────────────────────────────────
    echo ""
    echo "  Answer the following. Defaults are in brackets; press enter to accept."
    echo ""

    [[ -f "$ENV_FILE" ]] && info "Reading existing $ENV_FILE for defaults"

    ask FILMCASE_HOST "Address you will browse to" "$(env_default FILMCASE_HOST "$(detect_lan_ip)")"

    ask HTTPS_PORT "HTTPS port" "$(env_default FILMCASE_HTTPS_PORT 8443)"
    if port_in_use "$HTTPS_PORT"; then
        echo ""
        skip "Something is already listening on port $HTTPS_PORT."
        confirm "Use it anyway?" || die "Re-run and choose a free port."
    fi

    ask PUID_ANSWER "User id to own the files" "$(env_default PUID "$(id -u)")"
    ask PGID_ANSWER "Group id to own the files" "$(env_default PGID "$(id -g)")"

    # Every worker process loads Django and Pillow, so the default stays modest: a NAS is
    # usually running other things, and oversubscribing a small CPU costs more than it wins.
    default_concurrency=$(cpu_count)
    [[ "$default_concurrency" -gt 4 ]] && default_concurrency=4
    ask CONCURRENCY "Celery worker processes" "$(env_default FILMCASE_WORKER_CONCURRENCY "$default_concurrency")"
    ask WEB_WORKERS "Web server processes" "$(env_default FILMCASE_WEB_WORKERS 2)"

    # ── Photo directories ──────────────────────────────────────────────────────
    echo ""
    echo "  Photo directories to import. They are mounted read-only, at the same path"
    echo "  inside the container, so the path you type is the path you enter on the"
    echo "  Library page. Enter one per line; blank line when done."
    echo ""

    PHOTO_DIRS=()
    while IFS= read -r existing; do
        if [[ -n "$existing" ]]; then
            PHOTO_DIRS+=("$existing")
            info "keeping $existing"
        fi
    done < <(existing_photo_dirs)

    while true; do
        ask photo_dir "Photo directory (blank to finish)" ""
        [[ -z "$photo_dir" ]] && break
        photo_dir="${photo_dir/#\~/$HOME}"
        if [[ ! -d "$photo_dir" ]]; then
            skip "not a directory: $photo_dir"
            continue
        fi
        photo_dir="$(cd "$photo_dir" && pwd)"
        if printf '%s\n' "${PHOTO_DIRS[@]:-}" | grep -qxF "$photo_dir"; then
            skip "already added: $photo_dir"
            continue
        fi
        PHOTO_DIRS+=("$photo_dir")
        info "added $photo_dir"
    done

    if [[ ${#PHOTO_DIRS[@]} -eq 0 ]]; then
        skip "No photo directories. Filmcase will start with an empty library, and you"
        skip "will need to re-run this to add one before anything can be imported."
    fi

    # ── Write the files ────────────────────────────────────────────────────────
    SECRET_KEY_VALUE="$(env_value FILMCASE_SECRET_KEY || true)"
    if [[ -z "$SECRET_KEY_VALUE" || "$SECRET_KEY_VALUE" == "change-me" ]]; then
        SECRET_KEY_VALUE="$(generate_secret)"
    fi
    DB_PASSWORD_VALUE="$(env_value FILMCASE_DB_PASSWORD || true)"
    [[ -z "$DB_PASSWORD_VALUE" ]] && DB_PASSWORD_VALUE="$(generate_secret)"

    cat > "$ENV_FILE" <<EOF
# Generated by ./setup.sh docker on $(date +%Y-%m-%d). Re-run it to change these.

FILMCASE_HOST=$FILMCASE_HOST
FILMCASE_HTTPS_PORT=$HTTPS_PORT

PUID=$PUID_ANSWER
PGID=$PGID_ANSWER

FILMCASE_WORKER_CONCURRENCY=$CONCURRENCY
FILMCASE_WEB_WORKERS=$WEB_WORKERS

FILMCASE_SECRET_KEY=$SECRET_KEY_VALUE
FILMCASE_DB_PASSWORD=$DB_PASSWORD_VALUE
EOF
    info "Wrote $ENV_FILE"

    {
        echo "# Generated by ./setup.sh docker on $(date +%Y-%m-%d). Re-run it to change these."
        echo "#"
        echo "# Photo directories are mounted at their host paths so the values stored in"
        echo "# LibraryFolder stay valid. Both services need them: the worker does the importing."
        echo ""
        echo "services:"
        for service in web celery_worker; do
            echo "  $service:"
            if [[ ${#PHOTO_DIRS[@]} -eq 0 ]]; then
                echo "    volumes: []"
            else
                echo "    volumes:"
                for photo_dir in "${PHOTO_DIRS[@]}"; do
                    echo "      - $photo_dir:$photo_dir:ro"
                done
            fi
            [[ "$service" == "web" ]] && echo ""
        done
    } > "$OVERRIDE_FILE"
    info "Wrote $OVERRIDE_FILE"

    # ── Summary ────────────────────────────────────────────────────────────────
    echo ""
    echo "  Host        https://$FILMCASE_HOST:$HTTPS_PORT"
    echo "  Owner       uid $PUID_ANSWER, gid $PGID_ANSWER"
    echo "  Processes   $WEB_WORKERS web, $CONCURRENCY worker"
    if [[ ${#PHOTO_DIRS[@]} -eq 0 ]]; then
        echo "  Photos      none configured"
    else
        for photo_dir in "${PHOTO_DIRS[@]}"; do
            echo "  Photos      $photo_dir (read-only)"
        done
    fi
    echo ""
    echo "  The certificate is self-signed, so your browser will warn once. That is"
    echo "  expected: accepting it is what makes camera access work from the browser."
    echo ""

    if confirm "Build and start now?"; then
        docker compose up -d --build
        echo ""
        info "Filmcase is starting at https://$FILMCASE_HOST:$HTTPS_PORT/"
        info "Follow the log with: docker compose logs -f web"
    else
        echo ""
        info "Start it whenever you like with: docker compose up -d --build"
    fi
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# 1. Python 3.11+
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Python 3.11+..."
if command -v python3 &>/dev/null && python3 -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    skip "Python $(python3 --version) already satisfies requirement"
else
    if [[ "$OS" == "macos" ]]; then
        brew_install python
    else
        sudo apt-get update -qq
        apt_install python3
        apt_install python3-pip
    fi
fi

# python3-venv is a separate package on Ubuntu/Debian and is required to create
# virtual environments regardless of whether Python itself needed installing.
if [[ "$OS" == "ubuntu" ]]; then
    apt_install python3-venv
fi

# ══════════════════════════════════════════════════════════════════════════════
# 2. libusb (camera USB communication)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking libusb..."
if [[ "$OS" == "macos" ]]; then
    brew_install libusb
else
    apt_install libusb-1.0-0
fi

# ══════════════════════════════════════════════════════════════════════════════
# 3. exiftool (required for image processing)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking exiftool..."
if command -v exiftool &>/dev/null; then
    skip "exiftool already installed"
elif [[ "$OS" == "macos" ]]; then
    brew_install exiftool
else
    apt_install libimage-exiftool-perl
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4. PostgreSQL                                              (full install only)
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "full" ]]; then
    info "Checking PostgreSQL..."
    if [[ "$OS" == "macos" ]]; then
        brew_install postgresql@16
        brew_start postgresql@16
        PSQL="psql postgres"
    else
        apt_install postgresql
        apt_install postgresql-contrib
        systemd_start postgresql
        PSQL="sudo -u postgres psql"
    fi

    DB_USER="fujifilm_recipes"
    DB_NAME="fujifilm_recipes"
    DB_PASS="fujifilm_recipes"

    info "Checking PostgreSQL user '$DB_USER'..."
    if $PSQL -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
        skip "PostgreSQL user '$DB_USER' already exists"
    else
        info "Creating PostgreSQL user '$DB_USER'..."
        $PSQL -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS' CREATEDB;"
    fi

    info "Checking PostgreSQL database '$DB_NAME'..."
    if $PSQL -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
        skip "PostgreSQL database '$DB_NAME' already exists"
    else
        info "Creating PostgreSQL database '$DB_NAME'..."
        $PSQL -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. RabbitMQ                                                (full install only)
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "full" ]]; then
    info "Checking RabbitMQ..."
    if [[ "$OS" == "macos" ]]; then
        brew_install rabbitmq
        brew_start rabbitmq
    else
        apt_install rabbitmq-server
        systemd_start rabbitmq-server
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
echo ""
info "All system dependencies are ready."
if [[ "$MODE" == "lite" ]]; then
    info "Run 'make setup-lite' to complete the project setup."
else
    info "Run 'make setup-full' to complete the project setup."
fi
