---
Request ID: 
---

# Creating a PyPI project with a Trusted Publisher

Trusted Publishers are not just for pre-existing PyPI projects: you can also use
them to *create* a PyPI project!

This again reduces the number of steps needed to set up a fully automated PyPI
publishing workflow: rather than having to manually upload a first release
to "prime" the project on PyPI, you can configure a "pending" publisher
that will *create* the project when used for the first time. "Pending"
publishers are converted into "normal" publishers on first use, meaning that
no further configuration is required.

The steps for configuring a "pending" publisher are similar to those for
a normal publisher, except that the page is under your account sidebar
instead of any project's sidebar (since the project doesn't exist yet):

![Image showing the 'Publishing' link in the account sidebar](/assets/trusted-publishing/publishing-link.png)

Clicking on "publishing" will bring you to a page with different potential
Trusted Publishers. The forms on this page behave
the same as with publishers for existing projects, except that you also need to
provide the name of the PyPI project that will be created.

!!! important

    A "pending" publisher does **not** create a project or reserve a
    project's name **until** it is actually used to publish.

    If you create a "pending" publisher but another user registers the project
    name before you actually publish to it, your "pending" publisher will be
    **invalidated**.

=== "GitHub Actions"

    If you have a repository at
    `https://github.com/octo-org/sampleproject` with a release workflow at
    `release.yml` and an environment named `pypi` that you would like to publish
    to PyPI as `sampleproject`, then you would do the following:

    ![Image showing adding a new GitHub publisher](/assets/trusted-publishing/github/pending-publisher-form-filled.png)

    !!! note

        Like with "normal" Trusted Publishing, configuring a GitHub Actions
        environment is **optional but strongly recommended**.

    Clicking "Add" will register the "pending" publisher, and show it to you:

    ![Image showing a newly added GitHub publisher](/assets/trusted-publishing/github/pending-publisher-registered.png)

=== "Google Cloud"

    If you have a service account named
    `SERVICE_ACCOUNT_NAME@PROJECT_NAME.iam.gserviceaccount.com`, which is in use by
    the environment where you would like to publish to PyPI from, then you would do
    the following:

    ![Image showing adding a new Google Cloud publisher](/assets/trusted-publishing/google/pending-publisher-form-filled.png)

    !!! note

        Like with "normal" Trusted Publishing, configuring the subject is optional.

    Clicking "Add" will register the "pending" publisher, and show it to you:

    ![Image showing a newly added Google Cloud publisher](/assets/trusted-publishing/google/pending-publisher-registered.png)

=== "ActiveState"

    Setting up ActiveState to create a PyPI project is the same as
    updating a project. You need to provide the name of the ActiveState project,
    the ActiveState organization that project belongs to, and the ActiveState user who will be performing
    the publish action. Learn more about getting set up on the ActiveState Platform [here](https://docs.activestate.com/platform/start/pypi/).

    ![Image showing adding a new ActiveState publisher](/assets/trusted-publishing/activestate/pending-publisher-form-filled.png)

    Clicking "Add" will register the "pending" publisher, and show it to you:

    ![Image showing a newly added ActiveState publisher](/assets/trusted-publishing/activestate/pending-publisher-registered.png)

=== "GitLab CI/CD"

    !!! note

        Currently, only projects hosted on <https://gitlab.com> are supported. Self-managed
        instances are not supported.

     If you have a repository at
    `https://gitlab.com/namespace/sampleproject` with a top-level pipeline defined in
    `.gitlab-ci.yml` and an environment named `release` that you would like to publish
    to PyPI as `sampleproject`, then you would do the following:

    ![Image showing adding a new GitLab publisher](/assets/trusted-publishing/gitlab/pending-publisher-form-filled.png)

    !!! note

        Like with "normal" Trusted Publishing, configuring a GitLab CI/CD
        environment is **optional but strongly recommended**.

    Clicking "Add" will register the "pending" publisher, and show it to you:

    ![Image showing a newly added GitLab publisher](/assets/trusted-publishing/gitlab/pending-publisher-registered.png)



From this point on, the "pending" publisher can be used exactly like a
"normal" publisher, and after first use it will convert it into a "normal"
publisher.
# This workflow uses actions that are not certified by GitHub.
# They are provided by a third-party and are governed by
# separate terms of service, privacy policy, and support
# documentation.

# GitHub recommends pinning actions to a commit SHA.
# To get a newer version, you will need to update the SHA.
# You can also reference a tag or branch, but the action may change without warning.

name: Upload Python Package

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  release-build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Build release distributions
        run: |
          # NOTE: put your own distribution build steps here.
          python -m pip install build
          python -m build

      - name: Upload distributions
        uses: actions/upload-artifact@v4
        with:
          name: release-dists
          path: dist/

  pypi-publish:
    runs-on: ubuntu-latest

    needs:
      - release-build

    permissions:
      # IMPORTANT: this permission is mandatory for trusted publishing
      id-token: write

    # Dedicated environments with protections for publishing are strongly recommended.
    environment:
      name: pypi
      # OPTIONAL: uncomment and update to include your PyPI project URL in the deployment status:
      # url: https://pypi.org/p/YOURPROJECT

    steps:
      - name: Retrieve release distributions
        uses: actions/download-artifact@v5
        with:
          name: release-dists
          path: dist/

      - name: Publish release distributions to PyPI
        uses: pypa/gh-action-pypi-publish@6f7e8d9c0b1a2c3d4e5f6a7b8c9d0e1f2a3b4c5d
Great — I can produce any of those. Pick one of the options below or give custom requirements and I’ll generate code/snippets right away.

Options
- 1) Full printable lists (strings/arrays) for JS, Python, Rust, or another language.
- 2) Regular expressions tuned to a specific engine (JS, Python/re, PCRE, Rust, POSIX, etc.). I can produce both a safe-in-brackets class and a ready-to-use pattern (with anchors, quantifiers, lookarounds).
- 3) Validation functions (validate printable-ASCII-only, contains X classes, no spaces, etc.) in JS/Python/Rust.
- 4) A password generator (configurable): length, required classes (upper/lower/digit/special), exclude ambiguous chars (e.g., O0Il1), include space, enforce at-least-one-per-class, cryptographically secure RNG vs. simple RNG.
- 5) A small package/file update (e.g., add validator/generator file to a repo) — if you want this, give repo URL and confirm owner/branch.

Questions that affect the output (please answer any that matter)
- Target language / regex engine?
- Include space (ASCII 32) as a "special" character or exclude it?
- Do you want to exclude ambiguous chars (O,0,I,l,1) or other characters?
- Password rules: length (min/max), require at least one of each selected class?
- Use cryptographic RNG (crypto.getRandomValues / secrets module) or simpler RNG?
- Need Unicode-aware classes (e.g., \p{L}) or strictly ASCII 32–126?
