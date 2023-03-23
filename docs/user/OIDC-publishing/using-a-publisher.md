---
title: Actually using an OIDC publisher
---

# Actually using an OIDC publisher

### The easy way

Once you have an OIDC publisher configured, you can use the
[`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)
action to publish your packages.

This looks *almost* exactly the same as normal, except that you don't
need any explicit usernames, passwords, or API tokens: GitHub's OIDC provider
will take care of everything for you:

```yaml
jobs:
  pypi-publish:
    name: upload release to PyPI
    runs-on: ubuntu-latest
    permissions:
      # IMPORTANT: this permission is mandatory for OIDC publishing
      id-token: write
    steps:
      # retrieve your distributions here

      - name: Publish package distributions to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

Note the `id-token: write` permission: you **must** provide this permission
at either the job or workflow level. Without it, the publishing action
won't have sufficient permissions to grab an OIDC credential. Using the
permission at the job level is **strongly** encouraged, as it reduces
unnecessary credential exposure.

The `gh-action-pypi-publish` action also supports OIDC publishing with
other (non-PyPI) indices, provided they have OIDC enabled (and you've
configured your OIDC publisher on them). For example,
here's how you can publish to [TestPyPI](https://test.pypi.org) using OIDC:

```yaml
- name: Publish package distributions to TestPyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    repository-url: https://test.pypi.org/legacy/
```

### The manual way

**STOP! You probably don't need this section; it exists only to provide some
internal details about how GitHub Actions and PyPI coordinate using OIDC.
If you're a beta user, you should use the `pypa/gh-action-pypi-publish`
action instead.**

As described above, the process for using an OIDC publisher is:

1. Retrieve an *OIDC token* from the OIDC *provider*;
2. Submit that token to PyPI, which will return a short-lived API key;
3. Use that API key as you normally would (e.g. with `twine`)

GitHub is currently the only OIDC provider supported, so we'll use it for
examples below.

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
resp=$(curl -X POST https://pypi.org/_/oidc/github/mint-token -d "{\"token\": \"${oidc_token}\"}")
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
        run: |
          # retrieve the ambient OIDC token
          resp=$(curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=pypi")
          oidc_token=$(jq '.value' <<< "${resp}")

          # exchange the OIDC token for an API token
          resp=$(curl -X POST https://pypi.org/_/oidc/github/mint-token -d "{\"token\": \"${oidc_token}\"}")
          api_token=$(jq '.token' <<< "${resp}")

          # export the API token as TWINE_PASSWORD
          echo "TWINE_PASSWORD=${api_token}" >> "${GITHUB_ENV}"


      - name: publish
        # gh-action-pypi-publish uses TWINE_PASSWORD automatically
        uses: pypa/gh-action-pypi-publish@release/v1
```
