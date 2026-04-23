from dotenv import load_dotenv
from envparse import Env
from kombu import Queue
from pathlib import Path

import structlog

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / "src/config/env")

env = Env()

SECRET_KEY: str = env.str("SECRET_KEY", default="django-insecure-film-simulations-reader-dev-key")

DEBUG: bool = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "src.data",
    "src.interfaces",
]

DB_ENGINE: str = env.str("DB_ENGINE", default="django.db.backends.postgresql")
DB_NAME: str = env.str("DB_NAME", default="fujifilm_recipes")
DB_USER: str = env.str("DB_USER", default="fujifilm_recipes")
DB_PASSWORD: str = env.str("DB_PASSWORD", default="fujifilm_recipes")
DB_HOST: str = env.str("DB_HOST", default="127.0.0.1")
DB_PORT: str = env.str("DB_PORT", default="5432")

DATABASES = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PTP_DEVICE: str = env.str("PTP_DEVICE", default="src.domain.camera.ptp_usb_device.PTPUSBDevice")  # dotted import path to the PTP device implementation; swap for a stub/mock in tests

STATIC_FILES_DIR = BASE_DIR / "src/interfaces/static"  # directory served at /static/
GALLERY_PAGE_SIZE: int = env.int("GALLERY_PAGE_SIZE", default=24)  # number of images shown per page in the gallery view
RECIPE_EXPLORER_PAGE_SIZE: int = env.int("RECIPE_EXPLORER_PAGE_SIZE", default=24)  # number of recipes shown per page in the recipe explorer
IMAGE_MAX_RATING: int = env.int("IMAGE_MAX_RATING", default=5)  # maximum star rating a user can assign to an image (1–N)
RECIPE_GRAPH_MAX_DISTANCE: int = env.int("RECIPE_GRAPH_MAX_DISTANCE", default=7)  # maximum Hamming distance for an edge to appear in the recipe relationship graph
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

THUMBNAIL_CACHE_DIR = BASE_DIR / "thumbnail_cache"  # filesystem directory where generated thumbnails are cached
RECIPE_CARDS_DIR: Path = Path(env.str("RECIPE_CARDS_DIR", default=str(BASE_DIR / "recipe_cards")))  # filesystem directory where generated recipe card images are stored


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
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
USE_ASYNC_TASKS: bool = env.bool("USE_ASYNC_TASKS", default=True)  # True: enqueue Celery tasks (full stack); False: run sequentially (SQLite / lite install)

CELERY_TASK_QUEUES: tuple[Queue, ...] = (Queue(PROCESS_IMAGE_QUEUE),)

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
