"""Pytest session setup shared by the whole suite.

Test hermeticity: the suite must NOT read the developer's real
``~/.config/getsubtitle/user_settings.toml``. Several commands derive
argparse defaults from that config (e.g. ``build_combine_parser`` reads
``[merge].reading`` for the ``--reading`` default). A developer whose
personal config sets, say, ``[merge] reading = true`` would otherwise see
~18 merge tests fail on output-filename assertions — purely an environment
artifact, not a real regression. CI on a clean machine wouldn't reproduce
it, which makes such failures confusing and machine-dependent.

This autouse, session-scoped fixture points ``GETSUBTITLE_CONFIG_PATH`` at
an empty config for the whole run. Tests that need specific settings still
set ``GETSUBTITLE_CONFIG_PATH`` themselves (per test, via monkeypatch),
which overrides this baseline for that test only and is restored afterward.
"""

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_user_config():
    tmpdir = tempfile.mkdtemp(prefix="getsubtitle-test-config-")
    empty_config = os.path.join(tmpdir, "user_settings.toml")
    open(empty_config, "w").close()  # exists + parses to {} (no settings)
    previous = os.environ.get("GETSUBTITLE_CONFIG_PATH")
    os.environ["GETSUBTITLE_CONFIG_PATH"] = empty_config
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GETSUBTITLE_CONFIG_PATH", None)
        else:
            os.environ["GETSUBTITLE_CONFIG_PATH"] = previous
