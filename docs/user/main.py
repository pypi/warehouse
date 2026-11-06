# SPDX-License-Identifier: Apache-2.0

PREVIEW_FEATURES = {}


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
