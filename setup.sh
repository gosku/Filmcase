#!/usr/bin/env bash
# Installs all system-level dependencies for film_simulations_reader.
# Idempotent: skips anything that is already installed or running.
# Supports macOS (Homebrew) and Ubuntu/Debian (apt).
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[setup]${NC} $*"; }
skip() { echo -e "${YELLOW}[skip] ${NC} $*"; }
die()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

# ── Detect OS ──────────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ -f /etc/os-release ]] && grep -qi 'ubuntu\|debian' /etc/os-release; then
    OS="ubuntu"
else
    die "Unsupported OS. This script supports macOS and Ubuntu/Debian."
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
        apt_install python3-venv
    fi
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
# 3. PostgreSQL
# ══════════════════════════════════════════════════════════════════════════════
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
    $PSQL -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
fi

info "Checking PostgreSQL database '$DB_NAME'..."
if $PSQL -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
    skip "PostgreSQL database '$DB_NAME' already exists"
else
    info "Creating PostgreSQL database '$DB_NAME'..."
    $PSQL -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4. Memcached
# ══════════════════════════════════════════════════════════════════════════════
info "Checking Memcached..."
if [[ "$OS" == "macos" ]]; then
    brew_install memcached
    brew_start memcached
else
    apt_install memcached
    systemd_start memcached
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. RabbitMQ (optional — only needed for async image processing)
# ══════════════════════════════════════════════════════════════════════════════
info "Checking RabbitMQ..."
if [[ "$OS" == "macos" ]]; then
    brew_install rabbitmq
    brew_start rabbitmq
else
    apt_install rabbitmq-server
    systemd_start rabbitmq-server
fi

echo ""
info "All system dependencies are ready."
info "Run 'make setup' to complete the project setup."
