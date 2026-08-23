# Manual Installation

Filmcase's `./setup.sh` and `make` targets install everything for you; the
[README](../README.md#installation) covers the Lite, Full, and Docker paths. Follow this
guide only if you would rather install the dependencies and set up the project by hand.

## Installing dependencies

### Python & pip

Python 3.11+ is required.

- **macOS:** `brew install python`
- **Ubuntu:** `sudo apt install python3 python3-pip python3-venv`

### libusb (for camera USB communication)

- **macOS:** `brew install libusb`
- **Ubuntu:** `sudo apt install libusb-1.0-0`

### PostgreSQL (full install only)

- **macOS:**

  ```bash
  brew install postgresql@16
  brew services start postgresql@16
  ```

  Then create the database and user:

  ```bash
  psql postgres
  ```

  ```sql
  CREATE USER fujifilm_recipes WITH PASSWORD 'fujifilm_recipes';
  CREATE DATABASE fujifilm_recipes OWNER fujifilm_recipes;
  \q
  ```

- **Ubuntu:**
  ```bash
  sudo apt install postgresql postgresql-contrib
  sudo systemctl start postgresql
  sudo -u postgres psql
  ```
  ```sql
  CREATE USER fujifilm_recipes WITH PASSWORD 'fujifilm_recipes';
  CREATE DATABASE fujifilm_recipes OWNER fujifilm_recipes;
  \q
  ```

### exiftool (required for image processing with `process_images`)

- **macOS:** `brew install exiftool`
- **Ubuntu:** `sudo apt install libimage-exiftool-perl`

### RabbitMQ (full install only)

- **macOS:** `brew install rabbitmq && brew services start rabbitmq`
- **Ubuntu:** `sudo apt install rabbitmq-server && sudo systemctl start rabbitmq-server`

## Project setup

1. **Clone the repository:**

   ```bash
   git clone <repo-url>
   cd filmcase
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Generate the settings file** (choose one):

   ```bash
   make env       # full stack defaults (PostgreSQL, Celery)
   make env-lite  # SQLite, sequential processing
   ```

5. **Apply migrations:**
   ```bash
   python manage.py migrate
   ```
