"""
Guard the test suite against reading the developer's personal src/config/env.

That file is gitignored, so CI never has one and always runs on the defaults declared
in settings.py. If the suite reads it too, a locally tuned setting silently changes what
the tests assert against, producing failures that reproduce on one machine and not on CI.
"""

import os

from django.conf import settings


class TestPersonalEnvIsolation:
    def test_env_file_is_redirected_before_settings_are_imported(self) -> None:
        # settings.py reads whatever FILMCASE_ENV_FILE points at. The -p plugin in pytest.ini
        # aims it at os.devnull, and must be imported before pytest-django sets Django up;
        # a conftest.py hook runs too late. If this is unset the plugin stopped loading.
        assert os.environ.get("FILMCASE_ENV_FILE") == os.devnull

    def test_settings_match_the_declared_defaults(self) -> None:
        # A representative setting that a developer is likely to tune locally. It must hold
        # the settings.py default, not whatever src/config/env happens to say. This is the
        # assertion that actually fails if the flag is set too late to matter.
        assert settings.IMAGE_MAX_RATING == 5
