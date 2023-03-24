from pathlib import Path


OIDC_PUBLISHING = """
!!! info

    OpenID Connect publishing functionality is currently in closed beta.

    You can request access to the closed beta using
    [this form](https://forms.gle/XUsRT8KTKy66TuUp7).

    **NOTE**: Access to the OIDC beta is provided on a *per-user* basis: users
    can register OIDC publishers against projects once added to the beta, but
    other maintainers/owners of the project can't modify OIDC settings unless
    they're *also* in the beta.
"""

ORG_ACCOUNTS = """
!!! info

    Organization account features are currently in closed beta.

    Keep an eye on our [blog](https://blog.pypi.org) and
    [twitter](https://twitter.com/pypi)
    to be one of the first to know how you can begin using them.
"""

PREVIEW_FEATURES = {"oidc-publishing": OIDC_PUBLISHING, "org-accounts": ORG_ACCOUNTS}

_HERE = Path(__file__).parent.resolve()


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
