---
title: Publishing with a Trusted Publisher
---

# Publishing with a Trusted Publisher

Once you have a trusted publisher configured on PyPI (whether "pending" or
"normal"), you can publish through it on the associated platform. The tabs
below describe the setup process for each supported trusted publisher.

=== "GitHub Actions"

    ## The easy way

    You can use the PyPA's
    [`pypi-publish`](https://github.com/marketplace/actions/pypi-publish)
    action to publish your packages.

    This looks *almost* exactly the same as normal, except that you don't
    need any explicit usernames, passwords, or API tokens: GitHub's OIDC identity provider
    will take care of everything for you:

    ```yaml
    jobs:
      pypi-publish:
        name: upload release to PyPI
        runs-on: ubuntu-latest
        # Specifying a GitHub environment is optional, but strongly encouraged
        environment: release
        permissions:
          # IMPORTANT: this permission is mandatory for trusted publishing
          id-token: write
        steps:
          # retrieve your distributions here

          - name: Publish package distributions to PyPI
            uses: pypa/gh-action-pypi-publish@release/v1
    ```

    If you're moving away from a password or API token-based authentication
    flow, your diff might look like this:

    ```diff
    jobs:
      pypi-publish:
        name: upload release to PyPI
        runs-on: ubuntu-latest
    +    # Specifying a GitHub environment is optional, but strongly encouraged
    +    environment: release
    +    permissions:
    +      # IMPORTANT: this permission is mandatory for trusted publishing
    +      id-token: write
        steps:
          # retrieve your distributions here

          - name: Publish package distributions to PyPI
            uses: pypa/gh-action-pypi-publish@release/v1
    -        with:
    -          username: __token__
    -          password: ${{ secrets.PYPI_TOKEN }}
    ```

    Note the `id-token: write` permission: you **must** provide this permission
    at either the job level (**strongly recommended**) or workflow level
    (**discouraged**). Without it, the publishing action
    won't have sufficient permissions to identify itself to PyPI.

    !!! note

        Using the permission at the job level is **strongly** encouraged, as
        it reduces unnecessary credential exposure.

    ### Publishing to indices other than PyPI
    The PyPA's [`pypi-publish`](https://github.com/marketplace/actions/pypi-publish)
    action also supports trusted publishing with other (non-PyPI) indices, provided
    they have trusted publishing enabled (and you've configured your trusted
    publisher on them). For example, here's how you can use trusted publishing on
    [TestPyPI](https://test.pypi.org):

    ```yaml
    - name: Publish package distributions to TestPyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        repository-url: https://test.pypi.org/legacy/
    ```

    ## The manual way

    !!! warning

        **STOP! You probably don't need this section; it exists only to provide some
        internal details about how GitHub Actions and PyPI coordinate using OIDC.
        If you're an ordinary user, it is strongly recommended that you use the PyPA's
        [`pypi-publish`](https://github.com/marketplace/actions/pypi-publish)
        action instead.**

    !!! warning

        Many of the details described below are implementation-specific,
        and are not subject to either a standardization process or
        compatibility guarantees. They are not part of a public interface,
        and may be changed at any time. For a stable public interface,
        you **must** use the `pypi-publish` action.

    The process for using an OIDC publisher is:

    1. Retrieve an *OIDC token* from the OIDC *identity provider*;
    2. Submit that token to PyPI, which will return a short-lived API key;
    3. Use that API key as you normally would (e.g. with `twine`)

    GitHub is currently the only OIDC identity provider supported, so we'll use it
    for examples below.

    All code below assumes that it's being run in a GitHub Actions
    workflow runner with `id-token: write` permissions. That permission is
    **critical**; without it, GitHub Actions will refuse to give you an OIDC token.

    First, let's grab the OIDC token from GitHub Actions:

    ```bash
    resp=$(curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=pypi")
    ```

    **NOTE**: `audience=pypi` is only correct for PyPI. For TestPyPI, the correct
    audience is `testpypi`. More generally, you can access any instance's expected
    OIDC audience via the `{index}/_/oidc/audience` endpoint:

    ```console
    $ curl https://pypi.org/_/oidc/audience
    {"audience":"pypi"}
    ```

    The response to this will be a JSON blob, which contains the OIDC token.
    We can pull it out using `jq`:

    ```bash
    oidc_token=$(jq '.value' <<< "${resp}")
    ```

    Finally, we can submit that token to PyPI and get a short-lived API token
    back:

    ```bash
    resp=$(curl -X POST https://pypi.org/_/oidc/mint-token -d "{\"token\": \"${oidc_token}\"}")
    api_token=$(jq '.token' <<< "${resp}")

    # tell GitHub Actions to mask the token in any console logs,
    # to avoid leaking it
    echo "::add-mask::${api_token}"
    ```

    This API token can be fed into `twine` or any other uploading client:

    ```bash
    TWINE_USERNAME=__token__ TWINE_PASSWORD="${api_token}" twine upload dist/*
    ```

    This can all be tied together into a single GitHub Actions workflow:

    ```yaml
    on:
      release:
        types:
          - published

    name: release

    jobs:
      pypi:
        name: upload release to PyPI
        runs-on: ubuntu-latest
        permissions:
          id-token: write
        steps:
          - uses: actions/checkout@v3

          - uses: actions/setup-python@v4
            with:
              python-version: "3.x"

          - name: deps
            run: python -m pip install -U build

          - name: build
            run: python -m build

          - name: mint API token
            id: mint-token
            run: |
              # retrieve the ambient OIDC token
              resp=$(curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
                "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=pypi")
              oidc_token=$(jq -r '.value' <<< "${resp}")

              # exchange the OIDC token for an API token
              resp=$(curl -X POST https://pypi.org/_/oidc/mint-token -d "{\"token\": \"${oidc_token}\"}")
              api_token=$(jq -r '.token' <<< "${resp}")

              # mask the newly minted API token, so that we don't accidentally leak it
              echo "::add-mask::${api_token}"

              # see the next step in the workflow for an example of using this step output
              echo "api-token=${api_token}" >> "${GITHUB_OUTPUT}"

          - name: publish
            # gh-action-pypi-publish uses TWINE_PASSWORD automatically
            uses: pypa/gh-action-pypi-publish@release/v1
            with:
              password: ${{ steps.mint-token.outputs.api-token }}
    ```
