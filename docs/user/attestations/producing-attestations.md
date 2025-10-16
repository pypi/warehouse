# Producing attestations

<!--[[ preview('index-attestations') ]]-->

PyPI allows attestations to be attached to individual *release files*
(source and binary distributions within a release) at upload time.

## Prerequisites

Before uploading attestations to the index, please:

* Review the [Linux Foundation Immutable Record notice], which applies to the
  public transparency log.
* Set up [Trusted Publishing] with a supported CI/CD provider. Supported
  providers are listed below with instructions for each.

    !!! note

        Support for other Trusted Publishers is planned.
        See #17001 for additional information.

## Producing attestations

=== "GitHub Actions"

    <h3>The easy way</h3>

    If you publish to PyPI with [`pypa/gh-action-pypi-publish`][gh-action-pypi-publish]
    (the official PyPA action), attestations are generated and uploaded automatically
    by default, with no additional configuration necessary.

    <h3>The manual way</h3>

    !!! warning

        **STOP! You probably don't need this section; it exists only to provide
        some internal details about how attestation generation and uploading
        work. If you're an ordinary user, it is strongly recommended that
        you use one of the [official workflows described above].**

    <h4>Producing attestations</h4>

    !!! important

        Producing attestations manually does **not** bypass PyPI's current
        restrictions on supported attesting identities (i.e., Trusted Publishers).
        The examples below can be used to sign with a Trusted Publisher *or*
        with other identities, but PyPI will reject non-Trusted Publisher attestations
        at upload time.

    <h5>Using `pypi-attestations`</h5>

    [`pypi-attestations`][pypi-attestations] is a convenience library and CLI
    for generating and interacting with attestation objects. You can use
    either interface to produce attestations.

    For example, to generate attestations for all distributions in `dist/`:

    ```bash
    python -m pip install pypi-attestations
    python -m pypi_attestations sign dist/*
    ```

    If the above is run within a GitHub Actions workflow with `id-token: write`
    enabled (i.e., the ordinary context for Trusted Publishing), it will use
    the [ambient identity] of the GitHub Actions workflow that invoked it.

    If run locally, it will prompt you to perform an OAuth flow for identity
    establishment and will use the resulting identity.

    See [pypi-attestations' documentation] for usage as a Python library.

    <h5>Converting from Sigstore bundles</h5>

    Attestations are functionally (but not structurally) compatible with
    [Sigstore bundles], meaning that any system that can produce Sigstore
    bundles can be adapted to produce attestations.

    For example, GitHub's [`actions/attest`][actions-attest] can be used to produce
    Sigstore bundles with PyPI's [publish attestation] marker:

    ```yaml
    - name: attest
      uses: actions/attest@v1
      with:
        # Attest to every distribution
        subject-path: dist/*
        predicate-type: 'https://docs.pypi.org/attestations/publish/v1'
        predicate: '{}'
    ```

    Once generated, each Sigstore bundle can be converted into an equivalent
    attestation either in the same workflow or offline, using APIs
    from `sigstore-python` and `pypi-attestation`:

    ```python
    from pypi_attestations import Attestation
    from sigstore.models import Bundle

    raw_bundle = "..." # read the bundle's JSON
    bundle = Bundle.from_json(raw_bundle)
    attestation = Attestation.from_bundle(bundle)

    print(attestation.model_dump_json())
    ```

    <h4>Uploading attestations</h4>

    Attestations are uploaded to PyPI as part of the normal file upload flow.

    If you're using [`twine`][twine], you can upload any adjacent attestations
    with their associated files by passing `--attestations` to `twine upload`:

    ```bash
    twine upload --attestations dist/*
    ```

    See PyPI's [legacy upload API documentation] for adding attestations to a file
    upload at the upload API level.


=== "GitLab CI/CD"

    First, a GitLab workflow that uses Trusted Publishing to upload should already be
    set up. See [here][GitLab Trusted Publishing] for the instructions.

    Once that workflow exists, one can generate the attestations by adding an extra job
    in the workflow that runs after building, but before publishing:

    ```yaml
    generate-pypi-attestations:
      stage: build
      image: python:3-bookworm
      needs:
      - job: build-job
        artifacts: true
      id_tokens:
        SIGSTORE_ID_TOKEN:
          aud: sigstore
      script:
        - python -m pip install -U pypi-attestations
        - python -m pypi_attestations sign python_pkg/dist/*
      artifacts:
        paths:
          - "python_pkg/dist/"
    ```

    The entire workflow, with the three jobs (build, generate attestations, and
    publish) will look like this:

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

    generate-pypi-attestations:
      stage: build
      image: python:3-bookworm
      needs:
      - job: build-job
        artifacts: true
      id_tokens:
        SIGSTORE_ID_TOKEN:
          aud: sigstore
      script:
        - python -m pip install -U pypi-attestations
        - python -m pypi_attestations sign python_pkg/dist/*
      artifacts:
        paths:
          - "python_pkg/dist/"

    publish-job:
      stage: deploy
      image: python:3-bookworm
      dependencies:
        - build-job
        - generate-pypi-attestations
      id_tokens:
        PYPI_ID_TOKEN:
          # Use "testpypi" if uploading to TestPyPI
          aud: pypi
      script:
        # Install dependencies
        - python -m pip install -U twine

        # Upload to PyPI using Trusted Publishing, including the generated attestations
        # Add "--repository testpypi" if uploading to TestPyPI
        - twine upload  --attestations python_pkg/dist/*
    ```

    Note how, compared with the [Trusted Publishing workflow][GitLab Trusted Publishing], it has the
    following changes:

    - There is a new job called `generate-pypi-attestations` to generate the attestations and store
      them as artifacts
    - The publish job now also depends on `generate-pypi-attestations`, since it needs to download the
      generated attestations from it.
    - The publish job now calls `twine` passing the `--attestations` flag, to enable attestation upload.

=== "Google Cloud"

    [`pypi-attestations`][pypi-attestations] is a convenience library and CLI
    for generating and interacting with attestation objects. You can use
    either interface to produce attestations.

    For example, to generate attestations for all distributions in `dist/`:

    ```bash
    python -m pip install pypi-attestations
    python -m pypi_attestations sign dist/*
    ```

    If the above is run within a Google Cloud service with a [workload identity]
    (such as Cloud Build, Compute Engine, etc.), it will use the [ambient
    identity] of the service that invoked it.

    See [pypi-attestations' documentation] for usage as a Python library.


[Trusted Publishing]: /trusted-publishers/

[gh-action-pypi-publish]: https://github.com/pypa/gh-action-pypi-publish

[publish attestation]: /attestations/publish/v1

[official workflows described above]: #the-easy-way

[pypi-attestations]: https://github.com/pypi/pypi-attestations

[ambient identity]: https://github.com/sigstore/sigstore-python#signing-with-ambient-credentials

[pypi-attestations' documentation]: https://pypi.github.io/pypi-attestations/pypi_attestations.html

[Sigstore bundles]: https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_bundle.proto

[actions-attest]: https://github.com/actions/attest

[twine]: https://github.com/pypa/twine

[legacy upload API documentation]: /api/upload

[GitLab Trusted Publishing]: /trusted-publishers/using-a-publisher/#gitlab-cicd
[Linux Foundation Immutable Record notice]: https://lfprojects.org/policies/hosted-project-tools-immutable-records/
[workload identity]: https://cloud.google.com/iam/docs/workload-identity-federation
