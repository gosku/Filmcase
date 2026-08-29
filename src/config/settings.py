from dotenv import load_dotenv
from envparse import Env
from kombu import Queue
from pathlib import Path

import os
import structlog

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Defaults to the developer's personal, gitignored config. Override to read a different file,
# or os.devnull to ignore it entirely and run purely on the defaults declared below.
load_dotenv(os.environ.get("FILMCASE_ENV_FILE", BASE_DIR / "src/config/env"))

env = Env()

SECRET_KEY: str = env.str("SECRET_KEY", default="django-insecure-filmcase-dev-key")

DEBUG: bool = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = ["*"]

# The address the app is reached at. It has to match what users type, because it is written
# into the container's self-signed certificate as a subjectAltName and reused below as the
# trusted CSRF origin. A native install on the default runserver never leaves localhost, so
# that is the default.
FILMCASE_HOST: str = env.str("FILMCASE_HOST", default="localhost")
FILMCASE_HTTPS_PORT: int = env.int("FILMCASE_HTTPS_PORT", default=8443)

# Django rejects unsafe-method requests whose Origin is not listed here, and an HTTPS origin
# never matches by accident: reaching the app on any address other than FILMCASE_HOST fails
# every POST. Derived so there is one knob rather than two, and overridable outright for
# installs reachable under several names.
CSRF_TRUSTED_ORIGINS: list[str] = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[f"https://{FILMCASE_HOST}:{FILMCASE_HTTPS_PORT}"],
)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "constance",
    "src.data",
    "src.interfaces",
]

DB_ENGINE: str = env.str("DB_ENGINE", default="django.db.backends.postgresql")
DB_NAME: str = env.str("DB_NAME", default="fujifilm_recipes")
DB_USER: str = env.str("DB_USER", default="fujifilm_recipes")
DB_PASSWORD: str = env.str("DB_PASSWORD", default="fujifilm_recipes")
DB_HOST: str = env.str("DB_HOST", default="127.0.0.1")
DB_PORT: str = env.str("DB_PORT", default="5432")

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
    }
}

if DB_ENGINE.endswith("sqlite3"):
    # Lite mode runs SQLite with a background sync thread writing while the web
    # request threads read. WAL lets readers proceed alongside the single writer;
    # the busy timeout makes a colliding writer wait rather than raise "database
    # is locked". journal_mode is persistent on the file (idempotent to re-set).
    DATABASES["default"]["OPTIONS"] = {
        "timeout": 5,  # SQLite busy_timeout, applied per connection
        "init_command": "PRAGMA journal_mode=WAL;",
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PTP_DEVICE: str = env.str("PTP_DEVICE", default="src.domain.camera.ptp_usb_device.PTPUSBDevice")  # dotted import path to the PTP device implementation; swap for a stub/mock in tests

# Which machine the camera is plugged into. "server" talks to it from the Django process
# over PyUSB, so the camera must be attached to whatever runs Filmcase. "browser" talks to
# it from the user's own machine over WebUSB, which is what makes a headless install (a NAS,
# a container on another host) usable. WebUSB needs a secure context, so browser mode only
# works over HTTPS or localhost, and only on Chromium browsers.
CAMERA_TRANSPORT: str = env.str("CAMERA_TRANSPORT", default="server")  # "server": camera attached to the Filmcase host (PyUSB); "browser": camera attached to the user's machine (WebUSB)

STATIC_FILES_DIR = BASE_DIR / "src/interfaces/static"  # directory served at /static/
GALLERY_PAGE_SIZE: int = env.int("GALLERY_PAGE_SIZE", default=24)  # number of images shown per page in the gallery view
RECIPE_EXPLORER_PAGE_SIZE: int = env.int("RECIPE_EXPLORER_PAGE_SIZE", default=24)  # number of recipes shown per page in the recipe explorer
IMAGE_MAX_RATING: int = env.int("IMAGE_MAX_RATING", default=5)  # maximum star rating a user can assign to an image (1–N)
RECIPE_GRAPH_MAX_DISTANCE: int = env.int("RECIPE_GRAPH_MAX_DISTANCE", default=7)  # maximum Hamming distance for an edge to appear in the recipe relationship graph
RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY: int = env.int("RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY", default=20)  # % opacity of the Aperture card's darkening scrim at the top (0–100)
RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY: int = env.int("RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY", default=60)  # % opacity of the Aperture card's darkening scrim at the bottom (0–100)
CAMERA_VERIFY_WRITES: bool = env.bool("CAMERA_VERIFY_WRITES", default=False)  # set to False to skip read-back verification after writing

# Camera I/O policy — timing (seconds) and retry behaviour.
# Camera I/O timing and retry — consumed directly from settings across the camera layer.
CAMERA_POST_READ_DELAY_S:   float = env.float("CAMERA_POST_READ_DELAY_S",   default=0.05)   # pause after each property read
CAMERA_PRE_WRITE_DELAY_S:   float = env.float("CAMERA_PRE_WRITE_DELAY_S",   default=0.05)   # pause before each property write
CAMERA_POST_WRITE_DELAY_S:  float = env.float("CAMERA_POST_WRITE_DELAY_S",  default=0.05)   # pause after each property write
CAMERA_POST_CURSOR_DELAY_S: float = env.float("CAMERA_POST_CURSOR_DELAY_S", default=0.05)   # pause after positioning slot cursor
CAMERA_INTER_SLOT_DELAY_S:  float = env.float("CAMERA_INTER_SLOT_DELAY_S",  default=0.05)   # pause between slot cursor changes
CAMERA_MAX_RETRIES:         int   = env.int(  "CAMERA_MAX_RETRIES",          default=3)      # attempts per operation before giving up
CAMERA_RETRY_BACKOFF_S:     float = env.float("CAMERA_RETRY_BACKOFF_S",     default=0.15)   # base back-off; doubles each retry (0.15 s, 0.30 s, …)
CAMERA_USB_TIMEOUT_MS:      int   = env.int(  "CAMERA_USB_TIMEOUT_MS",      default=1500)   # how long one USB transfer may take before the camera is treated as unresponsive

THUMBNAIL_CACHE_DIR = BASE_DIR / "thumbnail_cache"  # filesystem directory where generated thumbnails are cached
RECIPE_CARDS_DIR: Path = Path(env.str("RECIPE_CARDS_DIR", default=str(BASE_DIR / "recipe_cards")))  # filesystem directory where generated recipe card images are stored

# Thumbnail widths that are generated and cached, as a comma-separated list in the env file
# (THUMBNAIL_WIDTHS=600,1200). A cache key is derived from the image path, so removing an image has
# to clear every width: a later file reusing that path (Fujifilm filenames wrap around from
# DSCF9999 to DSCF0001) would otherwise be served the previous image's thumbnail.
THUMBNAIL_WIDTHS: tuple[int, ...] = tuple(env.list("THUMBNAIL_WIDTHS", subcast=int, default=[600]))

# Library sync removes catalog entries whose files have disappeared. A sync that finds most of a
# folder's images missing is far more likely to be an unmounted drive or an unreadable directory
# than a real deletion, so a prune above this share of the folder's catalogued images can be
# reported instead of applied.
#
# Shipped disabled, because the only way past a tripped guard is
# `sync_library --force-prune` and the web interface offers no equivalent. A guard that fires
# during a path change from the Library page leaves the gallery stale with no way to resolve it
# from the page that caused it. Until forcing a sync is reachable from the interface, an
# unexplained stale gallery is the worse failure: nothing is deleted from disk either way.
#
# To enable, set both to real thresholds, e.g. 0.5 and 20. Both must be exceeded before the guard
# engages, so ordinary small cleanups are applied without a warning.
LIBRARY_PRUNE_GUARD_FRACTION: float = env.float("LIBRARY_PRUNE_GUARD_FRACTION", default=1.0)
LIBRARY_PRUNE_GUARD_MIN_IMAGES: int = env.int("LIBRARY_PRUNE_GUARD_MIN_IMAGES", default=9999999)


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "src.interfaces.camera.context_processors.camera_transport",
            ],
        },
    },
]

ROOT_URLCONF = "src.config.urls"

USE_TZ = True
TIME_ZONE = "UTC"

# Celery
CELERY_BROKER_URL: str = env.str("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND: str = env.str("CELERY_RESULT_BACKEND", default="rpc://")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
PROCESS_IMAGE_QUEUE: str = env.str("PROCESS_IMAGE_QUEUE", default="process-image")  # Celery queue name for image-processing tasks

# Library sync hands image processing to the worker in batches, so a large import costs one broker
# message per batch rather than one per file. Larger batches make dispatch faster; smaller ones
# spread the work more evenly across worker processes and lose less if a single batch dies.
SYNC_IMAGE_BATCH_SIZE: int = env.int("SYNC_IMAGE_BATCH_SIZE", default=100)
USE_ASYNC_TASKS: bool = env.bool("USE_ASYNC_TASKS", default=True)  # True: enqueue Celery tasks (full stack); False: run sequentially (SQLite / lite install)

CELERY_TASK_QUEUES: tuple[Queue, ...] = (Queue(PROCESS_IMAGE_QUEUE),)

# Dynamic settings (django-constance)
#
# The runtime-changeable settings above are also registered with constance so a
# user can edit them from the settings page and have the change take effect
# immediately, with no restart. Each env-read value above becomes that key's
# constance default: with no saved value constance returns the env default, and
# once the page is saved the database value wins and the env var is no longer
# consulted. Reads go through src.domain.settings.queries, never config directly.
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
# Left at None (the default) on purpose: with no cache every process reads the
# current database value on each access, so a change on the settings page reaches
# the web workers and the Celery worker on their next operation without a restart.
CONSTANCE_DATABASE_CACHE_BACKEND = None

# THUMBNAIL_WIDTHS is a tuple, which constance cannot store, so it is held as the
# same comma-separated string the env file uses (e.g. "600,1200") and parsed back
# to a tuple by src.domain.settings.queries.get_thumbnail_widths.
_THUMBNAIL_WIDTHS_DEFAULT = ",".join(str(width) for width in THUMBNAIL_WIDTHS)

CONSTANCE_CONFIG: dict[str, tuple[object, str, type]] = {
    "CAMERA_TRANSPORT": (CAMERA_TRANSPORT, "Which machine drives the camera: 'server' (attached to the Filmcase host, PyUSB) or 'browser' (attached to your machine, WebUSB). Browser mode needs an HTTPS or localhost page on a Chromium browser; server mode needs the camera plugged into the host.", str),
    "CAMERA_VERIFY_WRITES": (CAMERA_VERIFY_WRITES, "Read each recipe value back after writing it to the camera to confirm it landed.", bool),
    "CAMERA_POST_READ_DELAY_S": (CAMERA_POST_READ_DELAY_S, "Pause in seconds after each property read from the camera.", float),
    "CAMERA_PRE_WRITE_DELAY_S": (CAMERA_PRE_WRITE_DELAY_S, "Pause in seconds before each property write to the camera.", float),
    "CAMERA_POST_WRITE_DELAY_S": (CAMERA_POST_WRITE_DELAY_S, "Pause in seconds after each property write to the camera.", float),
    "CAMERA_POST_CURSOR_DELAY_S": (CAMERA_POST_CURSOR_DELAY_S, "Pause in seconds after positioning the recipe-slot cursor.", float),
    "CAMERA_INTER_SLOT_DELAY_S": (CAMERA_INTER_SLOT_DELAY_S, "Pause in seconds between moving the cursor from one slot to the next.", float),
    "CAMERA_MAX_RETRIES": (CAMERA_MAX_RETRIES, "How many times a camera operation is attempted before giving up.", int),
    "CAMERA_RETRY_BACKOFF_S": (CAMERA_RETRY_BACKOFF_S, "Base back-off in seconds between camera retries; it doubles each attempt.", float),
    "CAMERA_USB_TIMEOUT_MS": (CAMERA_USB_TIMEOUT_MS, "How long in milliseconds one USB transfer may take before the camera is treated as unresponsive.", int),
    "RECIPE_EXPLORER_PAGE_SIZE": (RECIPE_EXPLORER_PAGE_SIZE, "Number of recipes shown per page in the recipe explorer.", int),
    "RECIPE_GRAPH_MAX_DISTANCE": (RECIPE_GRAPH_MAX_DISTANCE, "Maximum difference between two recipes for them to be linked in the recipe graph. Higher values draw more connections.", int),
    "RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY": (RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY, "Opacity percentage (0-100) of the darkening gradient at the top of the Aperture recipe card.", int),
    "RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY": (RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY, "Opacity percentage (0-100) of the darkening gradient at the bottom of the Aperture recipe card.", int),
    "GALLERY_PAGE_SIZE": (GALLERY_PAGE_SIZE, "Number of images shown per page in the gallery.", int),
    "IMAGE_MAX_RATING": (IMAGE_MAX_RATING, "Highest star rating that can be given to an image.", int),
    "THUMBNAIL_WIDTHS": (_THUMBNAIL_WIDTHS_DEFAULT, "Comma-separated thumbnail widths in pixels to generate and cache (e.g. '600,1200'). Changing this does not regenerate or clear thumbnails already on disk: existing images keep their current widths until the generate_thumbnails command is run again.", str),
    "LIBRARY_PRUNE_GUARD_FRACTION": (LIBRARY_PRUNE_GUARD_FRACTION, "A sync that finds more than this share (0-1) of a folder's images missing reports the removal instead of applying it, guarding against an unmounted drive. 1.0 disables the guard.", float),
    "LIBRARY_PRUNE_GUARD_MIN_IMAGES": (LIBRARY_PRUNE_GUARD_MIN_IMAGES, "The prune guard only engages once at least this many images are missing (paired with the fraction above; both must be exceeded). A very high value disables the guard.", int),
    "SYNC_IMAGE_BATCH_SIZE": (SYNC_IMAGE_BATCH_SIZE, "How many images are handed to the worker per batch during a library sync.", int),
}

CONSTANCE_CONFIG_FIELDSETS: dict[str, tuple[str, ...]] = {
    "Recipes": (
        "RECIPE_EXPLORER_PAGE_SIZE",
        "RECIPE_GRAPH_MAX_DISTANCE",
        "RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY",
        "RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY",
    ),
    "Images": (
        "GALLERY_PAGE_SIZE",
        "IMAGE_MAX_RATING",
        "THUMBNAIL_WIDTHS",
    ),
    "Library": (
        "LIBRARY_PRUNE_GUARD_FRACTION",
        "LIBRARY_PRUNE_GUARD_MIN_IMAGES",
        "SYNC_IMAGE_BATCH_SIZE",
    ),
    "Camera": (
        "CAMERA_TRANSPORT",
        "CAMERA_VERIFY_WRITES",
        "CAMERA_POST_READ_DELAY_S",
        "CAMERA_PRE_WRITE_DELAY_S",
        "CAMERA_POST_WRITE_DELAY_S",
        "CAMERA_POST_CURSOR_DELAY_S",
        "CAMERA_INTER_SLOT_DELAY_S",
        "CAMERA_MAX_RETRIES",
        "CAMERA_RETRY_BACKOFF_S",
        "CAMERA_USB_TIMEOUT_MS",
    ),
}

# Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(),
        },
        "json": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
        },
        "traceback": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "events.jsonl",
            "formatter": "json",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
        # Plain stdlib formatting rather than the structlog renderer, so an exception's
        # traceback reaches the container log verbatim.
        "traceback_console": {
            "class": "logging.StreamHandler",
            "formatter": "traceback",
        },
    },
    "loggers": {
        "events": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "camera.events": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        # Django's own default sends unhandled view exceptions to a console handler gated on
        # DEBUG, and to mail_admins, which needs email configured. With DEBUG off and no
        # ADMINS, as in the container, a 500 is logged nowhere at all and the browser shows
        # only Django's stock error page. Route it somewhere it can actually be read.
        "django.request": {
            "handlers": ["file", "traceback_console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
)
