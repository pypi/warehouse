OIDC_PUBLISHING = """
!!! info

    OpenID Connect publishing functionality is currently in closed beta.

    You can register for the closed beta using
    [this form](https://forms.gle/XUsRT8KTKy66TuUp7).
"""

ORG_ACCOUNTS = """
!!! info

    Organization account features are currently in closed beta.

    Keep an eye on our [blog](https://blog.pypi.org) and
    [twitter](https://twitter.com/pypi)
    to be one of the first to know how you can begin using them.
"""

PREVIEW_FEATURES = {"oidc-publishing": OIDC_PUBLISHING, "org-accounts": ORG_ACCOUNTS}


def define_env(env):
    "Hook function"

    @env.macro
    def preview(preview_feature):
        return PREVIEW_FEATURES.get(preview_feature, "")
