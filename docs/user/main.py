# SPDX-License-Identifier: Apache-2.0

import logging

from pathlib import Path

# This module is also loaded as an MkDocs hook (see `hooks` in
# mkdocs-user-docs.yml) so this runs before the macros plugin starts, hiding
# its unconditional INFO-level setup chatter while keeping warnings.
logging.getLogger("mkdocs.plugins.mkdocs_macros").setLevel(logging.WARNING)

PREVIEW_FEATURES = {}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
