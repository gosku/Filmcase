from src.domain.settings import operations as domain_operations
from src.domain.settings.dataclasses import AppSettings


def update_app_settings(*, values: AppSettings) -> None:
    """
    Persist new values for every user-editable application setting.
    """
    domain_operations.update_app_settings(values=values)
