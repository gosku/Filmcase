"""
Keep the test suite off the developer's personal src/config/env file.

src/config/env is gitignored, so CI never has one and always runs on the defaults declared
in settings.py. If the suite read it too, a locally tuned setting would silently change what
the tests assert against, producing failures that reproduce on one machine but not on CI.

Pointing FILMCASE_ENV_FILE at os.devnull makes settings.py read an empty file, so every
setting falls back to its declared default.

This has to be a `-p` plugin rather than a conftest.py hook. pytest-django sets Django up in
`pytest_load_initial_conftests`, the same hook that loads the root conftest, and it wins that
race — so by the time conftest.py runs, settings.py has already been imported and the env file
already read. Plugins named with `-p` in pytest.ini are imported during preparse, before any of
that, which is early enough.

Real environment variables still take precedence, because load_dotenv does not override them.
A contributor whose database differs from the defaults can still use e.g. `DB_PORT=5433 pytest`.
"""

import os

os.environ["FILMCASE_ENV_FILE"] = os.devnull
