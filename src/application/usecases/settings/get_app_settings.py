from src.domain.settings import queries as domain_queries
from src.domain.settings.dataclasses import AppSettings


def get_app_settings() -> AppSettings:
    """
    Return the current values of every user-editable application setting.
    """
    return domain_queries.get_app_settings()
