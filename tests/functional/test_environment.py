# SPDX-License-Identifier: Apache-2.0

import os

import platformdirs


def test_xdg_environment():
    # Backstop checks for Warehouse's (Dockerfile-configured) environment.
    # NOTE: We don't check the exact paths here, because they vary between
    # environments: they're in `$HOME` in local and CI builds, and in `/tmp`
    # when deployed.
    user_data = platformdirs.user_data_dir(ensure_exists=True)
    user_cache = platformdirs.user_cache_dir(ensure_exists=True)

    assert os.access(user_data, os.R_OK | os.W_OK)
    assert os.access(user_cache, os.R_OK | os.W_OK)
