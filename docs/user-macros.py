from pathlib import Path

PREVIEW_FEATURES = {}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
