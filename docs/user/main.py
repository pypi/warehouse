from pathlib import Path

ORG_ACCOUNTS = """
!!! info

    Organization account features are currently in closed beta.

    Keep an eye on our [blog](https://blog.pypi.org) and
    [twitter](https://twitter.com/pypi)
    to be one of the first to know how you can begin using them.
"""

INDEX_ATTESTATIONS = """
!!! info

    Index attestations are currently under active development,
    and are not yet considered stable.
"""

PREVIEW_FEATURES = {
    "org-accounts": ORG_ACCOUNTS,
    "index-attestations": INDEX_ATTESTATIONS,
}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
