"""Project-local Python startup customizations.

This file is automatically imported by Python (via the `site` module) when the
repository root is on `sys.path` (which is typical when running from this
workspace).

We use it to keep test runs deterministic by disabling auto-loading of external
pytest plugins that may be present in the environment but are not required for
this project.
"""

from __future__ import annotations

import os
import sys


def _running_pytest() -> bool:
    argv = " ".join(sys.argv).lower()
    return "pytest" in argv


if _running_pytest():
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
