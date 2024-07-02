---
title: Publishing with a Trusted Publisher
---

# Publishing with a Trusted Publisher

Once you have a trusted publisher configured on PyPI (whether "pending" or
"normal"), you can publish through it on the associated platform. The tabs
below describe the setup process for each supported trusted publisher.

=== "GitHub Actions"

    <h3>The easy way</h3>

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

    <h3>Publishing to indices other than PyPI</h3>
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

    <h3>The manual way</h3>

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

    All code below assumes that it's being run in a GitHub Actions
    workflow runner with `id-token: write` permissions. That permission is
    **critical**; without it, GitHub Actions will refuse to give you an OIDC token.

    First, let's grab the OIDC token from GitHub Actions:

    ```bash
    resp=$(curl -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=pypi")
    ```

    !!! note

        Using `audience=pypi` is only correct for PyPI. For TestPyPI, the correct
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
    api_token=$(jq -r '.token' <<< "${resp}")

    # tell GitHub Actions to mask the token in any console logs,
    # to avoid leaking it
    echo "::add-mask::${api_token}"
    ```

    This API token can be fed into `twine` or any other uploading client:

    ```bash
    TWINE_USERNAME=__token__ TWINE_PASSWORD=${api_token} twine upload dist/*
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

=== "Google Cloud"

    You can use the <https://pypi.org/project/id/> tool to automatically detect
    and produce OIDC credentials on Google Cloud services.

    First, ensure that `id` and `twine` are installed in the environment you
    plan to publish from:

    ```
    python -m pip install -U id twine
    ```

    If you're unsure what the email address is for the service account your
    service is using, you can verify it with:

    ```
    python -m id pypi -d | jq 'select(.email) | .email'
    ```

    Generate an OIDC token from within the environment and store it. The
    audience should be either `pypi` or `testpypi` depending on which index you are
    publishing to:

    ```
    oidc_token=$(python -m id pypi)
    ```

    !!! note
        `pypi` is only correct for PyPI. For TestPyPI, the correct
        audience is `testpypi`. More generally, you can access any instance's expected
        OIDC audience via the `{index}/_/oidc/audience` endpoint:

        ```console
        $ curl https://pypi.org/_/oidc/audience
        {"audience":"pypi"}
        ```

    Finally, we can submit that token to PyPI and get a short-lived API token
    back:

    ```bash
    resp=$(curl -X POST https://pypi.org/_/oidc/mint-token -d "{\"token\": \"${oidc_token}\"}")
    api_token=$(jq -r '.token' <<< "${resp}")
    ```

    !!! note

        This is the URL for PyPI. For TestPyPI, the correct
        domain should be is `test.pypi.org`.

    This API token can be fed into `twine` or any other uploading client:

    ```bash
    TWINE_USERNAME=__token__ TWINE_PASSWORD=${api_token} twine upload dist/*
    ```

=== "ActiveState"

    ActiveState's Platform works as a zero-config CI solution for your
    dependencies to automatically build cross-platform wheels of your PyPI
    projects. Once you're set up on the Platform and have linked your PyPI project,
    you're ready to publish. For more information on getting started with
    ActiveState, go [here](https://docs.activestate.com/platform/start/pypi/). To
    begin:

    Publish your package to ActiveState's catalog. This will allow
    ActiveState's Platform to build it for you.

    1. Run the following command using the State Tool CLI:
        ```
        state publish \
          --namespace private/ORGNAME \
          --name PKG_NAME PKG_FILENAME \
          --depend "builder/python-module-builder@>=0" \
          --depend "language/python@>=3" \
          --depend "language/python/setuptools@>=43.0.0" \
          --depend "language/python/wheel@>=0"
        ```
        Replace the placeholder values in the block above with your ActiveState
        organization name--this will usually be `USERNAME-org` (ORGNAME), package name
        (PKG_NAME), and the filename of your sdist or source tarball (PKG_FILENAME) and
        run the command. Take note of the TIMESTAMP in the output.

    !!! note
        The namespace must start with `private/` followed by your
        organization name. You can also append additional 'folder' names if desired.

    2. After publishing your package to ActiveState, you'll need to create a
        build script file (`buildscript.as`) to build it into a wheel and publish it to
        PyPI. An example script is shown below. Create a new build script file in the
        same folder as your `activestate.yaml` file and name it `buildscript.as`. Paste
        the code below, substituting the placeholder values with those from your
        project: the timestamp of the package you just published (PUBLISHED_TIMESTAMP),
        the name of the namespace (ie. folder where you published the ingredient, which
        will look something like `private/USERNAME-org`) (NAMESPACE), the name of your
        package (PKG_NAME) and the version (VERSION) you're publishing. Save the
        changes to the file.
        ```python
        at_time = "PUBLISHED_TIMESTAMP"

        publish_receipt = pypi_publisher(
          attempt = 1,
          audience = "testpypi",
          pypi_uri = "test.pypi.org",
          src = wheels
        )
        runtime = state_tool_artifacts(
          build_flags = [
          ],
          src = sources
        )
        sources = solve(
          at_time = at_time,
          platforms = [
            "7c998ec2-7491-4e75-be4d-8885800ef5f2"
          ],
          requirements = [
            Req(namespace = "language", name = "python", version = Eq(value="3.10.13")),
            Req(namespace = "NAMESPACE", name = "PKG_NAME", version = Eq(value="VERSION"))
          ],
          solver_version = null
        )
        wheel_srcs = select_ingredient(
          namespace = "NAMESPACE",
          name = "PKG_NAME",
          src = sources
        )
        wheels = make_wheel(
          at_time = at_time,
          python_version = "3.10.13",
          src = wheel_srcs
        )

        main = runtime
        ```
    3. Then, "commit" this build script to the system by running `state commit`
    in your terminal. Now you're ready to publish to PyPI!
    4. To publish your wheel to PyPI, run: `state eval publish_receipt`.
    That's it!

    You have successfully published a Python wheel using the ActiveState Platform.

    !!! note
        Buildscript tips:

        You can leave `pypi_uri` and `audience` fields blank to publish
        directly to the main PyPI repository.

        If you experience a network timeout or another transient error, you can
        increment the `attempt` parameter to retry.

        The strings after `platforms = [` are the UUIDs of the supported
        platforms you want to build a wheel for. A list of all supported platforms can
        be found
        [here](https://docs.activestate.com/platform/updates/supported-platforms).
        Select all applicable to your project from the list provided.

    !!! note
        If you want to test your wheel before publishing it, you follow these
        steps before running `state eval publish_receipt`:
        1. To build your wheel on its own, run `state eval wheels`
        2. After building your wheel, run `state builds --all` to view all of
          the builds available. Take note of the `HASH_ID` of your new wheel.
        3. Run `state builds dl <HASH_ID>` to download and test the wheel you've built.

=== "GitLab CI/CD"

    This is an example GitLab workflow that builds and publishes a package to PyPI
    using Trusted Publishing. The key differences with a normal workflow are in the
    deployment step (`publish-job`):

    - The keyword
      [`id_tokens`](https://docs.gitlab.com/ee/ci/yaml/index.html#id_tokens) is used
      to request an OIDC token from GitLab with name `PYPI_ID_TOKEN` and audience
      `pypi`.
    - This OIDC token is extracted from the CI/CD environment using the
      [`id`](https://pypi.org/project/id/) package.
    - The OIDC token is then sent to PyPI in exchange for a PyPI API token, which
      is then used to publish the package using `twine`.

    ```yaml
    build-job:
      stage: build
      image: python:3-bookworm
      script:
        - python -m pip install -U build
        - cd python_pkg && python -m build
      artifacts:
        paths:
          - "python_pkg/dist/"

    publish-job:
      stage: deploy
      image: python:3-bookworm
      dependencies:
        - build-job
      id_tokens:
        PYPI_ID_TOKEN:
          # Use "testpypi" if uploading to TestPyPI
          aud: pypi
      script:
        # Install dependencies
        - apt update && apt install -y jq
        - python -m pip install -U twine id

        # Retrieve the OIDC token from GitLab CI/CD, and exchange it for a PyPI API token
        - oidc_token=$(python -m id PYPI)
        # Replace "https://pypi.org/*" with "https://test.pypi.org/*" if uploading to TestPyPI
        - resp=$(curl -X POST https://pypi.org/_/oidc/mint-token -d "{\"token\":\"${oidc_token}\"}")
        - api_token=$(jq --raw-output '.token' <<< "${resp}")

        # Upload to PyPI authenticating via the newly-minted token
        # Add "--repository testpypi" if uploading to TestPyPI
        - twine upload -u __token__ -p "${api_token}" python_pkg/dist/*
    ```
