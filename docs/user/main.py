from pathlib import Path

INDEX_ATTESTATIONS = """
!!! info

    Index attestations are currently under active development,
    and are not yet considered stable.
"""

PREVIEW_FEATURES = {
    "index-attestations": INDEX_ATTESTATIONS,
}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
