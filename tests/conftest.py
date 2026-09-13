"""Test-session environment, set before any test module imports the backend.

The local .env holds the deployed Space's operator password, because
scripts/live_api_check.py and scripts/deploy_space.py read it from there.
backend.config loads .env on import, and every test client then demanded that
bearer token: 70 API tests failed with 401 on a machine that had deployed.
Deleting the line is not a fix either -- deploy_space.py mints a new password
and pushes it to the Space when the line is missing.

The .env loader never overwrites a variable that is already set, so setting
these empty here keeps the suite hermetic without touching anyone's .env. A
test that needs a token still sets one with monkeypatch.
"""

import os

os.environ["DESK_ACCESS_TOKEN"] = ""
# The suite never contacts a live model; a real inference token in .env must
# not change that.
os.environ["HF_TOKEN"] = ""
