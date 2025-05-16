# SPDX-License-Identifier: Apache-2.0

# Site customization shim to enable multiprocess coverage collection in tests.
# See: https://coverage.readthedocs.io/en/latest/subprocess.html

try:
    import coverage

    coverage.process_startup()
except ImportError:
    pass
