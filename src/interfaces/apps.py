from django.apps import AppConfig


class InterfacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.interfaces"
    label = "interfaces"

    def ready(self):
        import structlog
        from django.conf import settings

        settings.LOG_DIR.mkdir(exist_ok=True)
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
