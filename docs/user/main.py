from pathlib import Path


EXAMPLE = """
!!! info

    The example feature is currently in closed beta
    and may not be available for your user yet.
"""

PREVIEW_FEATURES = {"example": EXAMPLE}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
