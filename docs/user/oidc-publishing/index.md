---
title: Getting started
---

{{ preview('oidc-publishing') }}

# Publishing to PyPI with OpenID Connect

## Confirming that you're in the beta

Before we do anything else: let's confirm that you're actually in the OIDC
beta! You can do this by [logging into PyPI](https://pypi.org/account/login/)
and clicking on "Account settings" in the dropdown under your profile:

{{ image('dropdown.png') }}

On the "Account settings" page, you should see a right-side menu that
contains a "Publishing" link:

{{ image('publishing-link.png') }}

If you see that link and can click on it, then you're in the beta group!

## Quick background: OIDC publishing

OIDC publishing is a mechanism for uploading packages to PyPI, *complementing*
existing methods (username/password combinations, API tokens).

You don't need to understand OIDC to use OIDC publishing with PyPI, but here's
the TL;DR:

1. Certain CI services (like GitHub Actions) are OIDC *providers*, meaning that
   they can issue short-lived credentials ("OIDC tokens") that a third party
   can **strongly** verify came from the CI service (as well as which user,
   repository, etc. actually executed);
1. Projects on PyPI can be configured to trust a particular configuration on
   a particular CI service, making that configuration an OIDC publisher
   for that project;
1. Release automation (like GitHub Actions) can submit an OIDC token
   to PyPI. The token will be matched against configurations trusted by
   different projects; if any projects trust the token's configuration,
   then PyPI will mint a *short lived API token* for those projects and
   return it.
1. The short-lived API token behaves exactly like a normal project-scoped API
   token, except that it's only valid for 15 minutes from time of creation
   (enough time for the CI to use it to upload packages).

This confers significant usability and security advantages when compared
to PyPI's traditional authentication methods:

* Usability: with OIDC publishing, users no longer need to manually create
  API tokens on PyPI and copy-paste them into their CI provider. The only
  manual step is configuring the OIDC provider on PyPI.
* Security: PyPI's normal API tokens are long-lived, meaning that an attacker
  who compromises a package's release can use it until its legitimate user
  notices and manually revokes it. Similarly, uploading with a password means
  that an attacker can upload to *any* project associated with the account.
  OIDC publishing avoids both of these problems: the tokens minted expire
  automatically, and are scoped down to only the packages that they're
  authorized to upload to.

## Adding an OIDC publisher to a PyPI project

Adding an OIDC publisher to a PyPI project only requires a single setup step.

On the "Your projects" page, click "Manage" on any project you'd like to
configure:

{{ image('manage-link.png') }}

Then, click on "Publishing" in the project's sidebar:

{{ image('project-publishing-link.png') }}

That link will take you to the OIDC publisher configuration page for the project:

{{ image('project-publishing.png') }}

To enable an OIDC publisher, you need to tell PyPI how to trust it. For
GitHub Actions (the only currently supported provider), you do this by
providing the repository owner's name, the repository's name, and the
filename of the GitHub Actions workflow that's authorized to upload to
PyPI.

For example, if you have a project at `https://github.com/pypa/pip-audit`
that uses a publishing workflow defined in `.github/workflows/release.yml`,
then you'd do the following:

{{ image('project-publishing-form.png') }}

Once you click "Add", your OIDC publisher will be registered and will appear
at the top of the page:

{{ image('project-publisher-registered.png') }}

From this point onwards, the `release.yml` workflow on `pypa/pip-audit` will
be able to mint short-lived API tokens for the PyPI project you've registered
it against.

An OIDC publisher can be registered against multiple PyPI projects (e.g. for a
multi-project repository), and a single PyPI project can have multiple OIDC
publishers (e.g. for multiple workflows on different architectures, OSes).

## Creating a PyPI project through OIDC

OIDC publishing is not just for pre-existing PyPI projects: you can also use
it to *create* a PyPI project!

This again reduces the number of steps needed to set up a fully automated PyPI
publishing workflow: rather than having to manually upload a first release
to "prime" the project on PyPI, you can configure a "pending" OIDC publisher
that will *create* the project when used for the first time. "Pending"
publishers are converted into "normal" publishers on first use, meaning that
no further configuration is required.

The process for configuring a "pending" publisher are similar to those for
a normal publisher, except that the page is under your account sidebar
instead of any project's sidebar (since the project doesn't exist yet):

{{ image('publishing-link.png') }}

Clicking on "publishing" will bring you to a familiar looking form:

{{ image('pending-publisher-form.png') }}

This form behaves the same as with a "normal" OIDC publisher, except that you
also need to provide the name of the PyPI project that will be created.

For example, if you have a repository at `https://github.com/example/awesome`
with a release workflow at `release.yml` and you'd like to publish it to
PyPI as `pyawesome`, you'd do the following:

{{ image('pending-publisher-form-filled.png') }}

Clicking "Add" will register the "pending" publisher, and show it to you:

{{ image('pending-publisher-registered.png') }}

From this point on, the "pending" publisher can be used exactly like a
"normal" OIDC publisher. Using it will convert it into a "normal" OIDC
publisher.

## Actually using an OIDC publisher

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

## Troubleshooting

Here's a quick enumeration of errors you might see from the `mint-token`
endpoint:

* `not-enabled`: this indicates that PyPI's backend has
  disabled OIDC entirely. You should not see this message during normal
  operation for the duration of the OIDC beta, **unless** PyPI's admins
  have decided to disable OIDC support.
* `invalid-payload`: the OIDC token payload submitted to the `mint-token`
  endpoint is not formatted correctly. The payload **must** be a JSON serialized
  object, with the following layout:

  ```json
  {
    "token": "oidc-token-here"
  }
  ```

  No other layouts are supported.
* `invalid-token`: the OIDC token itself is either formatted incorrectly,
  has an invalid signature, is expired, etc. This encompasses pretty much
  any failure mode that can occur with an OIDC token (which is just a JWT)
  *before* it's actually matched against a publisher.
* `invalid-pending-publisher` and `invalid-publisher`: the OIDC token itself
  is well-formed (and has a valid signature), but doesn't match any known
  (pending) OIDC publisher. This likely indicates a mismatch between the
  OIDC publisher specified in the user/project settings and the claims
  represented in the actual OIDC token. Check for typos!

## Security model and considerations

### Security model

GitHub Actions' own security model for OpenID Connect tokens is a little subtle:

* Any workflow defined in a repository can request an OIDC token,
 *with any audience*, **so long as it has the `id-token: write` permission**.

* The claims defined in an OIDC token are *bound to the workflow*, meaning
  that a workflow defined at `foo.yml` in `org/repo` **cannot impersonate**
  a workflow defined at `bar.yml` in `org/repo`. However, if `foo.yml` is
  *renamed* to `bar.yml`, then the *new* `bar.yml` will be indistinguishable
  from the old `bar.yml` **except** for claims that reflect the repository's
  state (e.g. `git` ref, branch, etc.).

* *Generally speaking*, "third party" events **cannot** request an OIDC
  token: even if they can trigger the workflow that requests the token,
  the actual token retrieval step will fail. For example: PRs issued from forks
  of a repository **cannot** access the OIDC tokens in the "upstream"
  repository's workflows.

  * The exception to this is `pull_request_target` events, which are
    **[fundamentally dangerous] by design** and should not be used without
    careful consideration.

### Considerations

While more secure than passwords and long-lived API tokens, OIDC publishing
is not a panacea. In particular:

* Short-lived API tokens are still sensitive material, and should not be
  disclosed (ideally not at all, but certainly not before they expire).

* OIDC tokens themselves are sensitive material, and should not be disclosed.
  OIDC tokens are also short-lived, but an attacker who successfully intercepts
  one can mint API tokens against it for as long as it lives.

* Configuring an OIDC publisher means establishing trust in a particular piece
  of external state; that state **must not** be controllable by untrusted
  parties. In particular, for OIDC publishing with GitHub Actions, you **must**:

  * Trust the correct username and repository: if you trust a repository
    other than one you control and trust, that repository can upload to your
    PyPI project.

  * Trust the correct workflow: you shouldn't trust every workflow
    to upload to PyPI; instead, you should isolate responsibility to the
    smallest (and least-privileged) possible separate workflow. We recommend
    naming this workflow `release.yml`.

  * Take care when merging third-party changes to your code: if you trust
    `release.yml`, then you must make sure that third-party changes to that
    workflow (or code that runs within that workflow) are not malicious.

PyPI has protections in place to make some attacks against OIDC more difficult
(like account resurrection attacks). However, like all forms of authentication,
the end user is **fundamentally responsible** for applying it correctly.

In addition to the requirements above, you can do the following to
"ratchet down" the scope of your OIDC publishing workflows:

* **Use per-job permissions**: The `permissions` key can be defined on the
  workflow level or the job level; the job level is **always more secure**
  because it limits the number of jobs that receive elevated `GITHUB_TOKEN`
  credentials.

* **[Use a dedicated environment]**: GitHub Actions supports "environments,"
  which can be used to isolate secrets to specific workflows. OIDC publishing
  doesn't use any pre-configured secrets, but a dedicated `publish` or `deploy`
  environment is a general best practice.

  Dedicated environments allow for additional protections like
  [required reviewers], which can be used to require manual approval for a
  workflow using the environment.

  For example, here is how `pypa/pip-audit`'s `release` environment
  restricts reviews to members of the maintenance and admin teams:

  {{ image('required-reviewers.png') }}

* **[Use tag protection rules]**: if you use a tag-based publishing workflow
  (e.g. triggering on tags pushed), then you can limit tag creation and
  modification to maintainers and higher (or custom roles) for any tags
  that match your release pattern. For example, `v*` will prevent
  non-maintainers from creating or modifying tags that match version
  strings like `v1.2.3`.

* **Limit the scope of your publishing job**: your publishing job should
  (ideally) have only two steps:

  1. Retrieve the publishable distribution files from **a separate
    build job**;

  2. Publish the distributions using `pypa/gh-action-pypi-publish@release/v1`.

  By using a separate build job, you keep the number of steps that can
  access the OIDC token to a bare minimum. This prevents both accidental
  and malicious disclosure.

[fundamentally dangerous]: https://securitylab.github.com/research/github-actions-preventing-pwn-requests/

[Use a dedicated environment]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment

[Use tag protection rules]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules

[required reviewers]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#required-reviewers
