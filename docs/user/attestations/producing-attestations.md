# Producing attestations

<!--[[ preview('index-attestations') ]]-->

PyPI allows attestations to be attached to individual *release files*
(source and binary distributions within a release) at upload time.

Attestations are currently only supported when uploading with
[Trusted Publishing], and currently only with GitHub-based Trusted Publishers.
Support for other Trusted Publishers is planned. See
[#17001](https://github.com/pypi/warehouse/issues/17001) for additional
information.

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

[Trusted Publishing]: /trusted-publishers/

[gh-action-pypi-publish]: https://github.com/pypa/gh-action-pypi-publish

[publish attestation]: /attestations/publish/v1

[official workflows described above]: #the-easy-way

[pypi-attestations]: https://github.com/trailofbits/pypi-attestations

[ambient identity]: https://github.com/sigstore/sigstore-python#signing-with-ambient-credentials

[pypi-attestations' documentation]: https://trailofbits.github.io/pypi-attestations/pypi_attestations.html

[Sigstore bundles]: https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_bundle.proto

[actions-attest]: https://github.com/actions/attest

[twine]: https://github.com/pypa/twine

[legacy upload API documentation]: https://warehouse.pypa.io/api-reference/legacy.html#upload-api
