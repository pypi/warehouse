# Upload API

The API endpoint served at <https://upload.pypi.org/legacy/>
is Warehouse's emulation of the legacy PyPI upload API. This is the endpoint
that tools such as [twine] use to [upload distributions to PyPI].

[twine]: https://twine.readthedocs.io/

[upload distributions to PyPI]: https://packaging.python.org/guides/distributing-packages-using-setuptools/#uploading-your-project-to-pypi

## Routes

### Upload a file

!!! important

    Releases on PyPI are created by uploading one file at a time.

    The first file uploaded of a new version creates a release for that version,
    and populates its metadata.

Route: `POST upload.pypi.org/legacy/`

The upload API can be used to upload artifacts by sending a `multipart/form-data`
POST request with the following fields:

- `:action` set to `file_upload`
- `protocol_version` set to `1`
- `content` with the file to be uploaded and the proper filename
  (i.e. `my_foo_bar-4.2-cp36-cp36m-manylinux1_x86_64.whl`)
- One of the following hash digests:
    - `md5_digest` set to the md5 hash of the uploaded file in urlsafe base64
  with no padding
    - `sha256_digest` set to the SHA2-256 hash in hexadecimal
    - `blake2_256_digest` set to the Blake2b 256-bit hash in hexadecimal
- `filetype` set to the type of the artifact, i.e. `bdist_wheel`
  or `sdist`
- When used with `bdist_wheel` for `filetype`, `pyversion` must be set to
  a specific release, i.e. `cp36`, when used with `sdist` it must be set to
  `source`
- `metadata_version`, `name` and `version` set according to the
  [Core metadata specifications]
- `attestations` can be set to a JSON array of [attestation objects].
  PyPI will reject the upload if it can't verify each of the
  supplied attestations.
- You can set any other field from the [Core metadata specifications]
  All fields need to be renamed to lowercase and hyphens need to replaced
  by underscores. So instead of "`Description-Content-Type`" the field must be
  named "`description_content_type`". Note that adding a field
  "`Description-Content-Type`" will not raise an error but will be silently
  ignored.

[attestation objects]: ./integrity.md#concepts

[Core metadata specifications]: https://packaging.python.org/specifications/core-metadata
