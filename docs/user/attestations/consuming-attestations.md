# Consuming attestations

PyPI makes a file's attestations available via the simple index (HTML)
and simple JSON APIs.

For a full API reference, see the [Integrity API documentation].

## Internals

Since a distribution file can have multiple attestations, and PyPI serves
these attestations as a single JSON file, this JSON file groups the
attestations into a single [provenance object]. This object contains
bundles of attestations grouped by the Trusted Publisher identity used
to sign them.

To manually verify a PyPI artifact against its provenance object,
the [`pypi-attestations`][pypi-attestations] CLI tool can be used:

```bash
export WHEEL_DIRECT_URL=https://files.pythonhosted.org/packages/d7/73/c16e5f3f0d37c60947e70865c255a58dc408780a6474de0523afd0ec553a/sampleproject-4.0.0-py3-none-any.whl

pypi-attestations verify pypi --repository https://github.com/pypa/sampleproject $WHEEL_DIRECT_URL
```

This downloads the wheel from PyPI and its corresponding provenance JSON
(using the Integrity API), checks that the Trusted Publishers specified
in the provenance match the `--repository` argument passed by the user,
and finally cryptographically verifies the wheel against the included
attestations.


[Integrity API documentation]: /api/integrity/
[provenance object]: https://packaging.python.org/en/latest/specifications/index-hosted-attestations/#provenance-objects
[pypi-attestations]: https://pypi.org/project/pypi-attestations/

