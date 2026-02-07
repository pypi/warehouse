# Secret reporting API

!!! warning "Not publicly available"

    Note that this API is only available on a case-by-case basis. Please
    contact admin@pypi.org if you would like to integrate with this API.

Third parties integrate with PyPI to find, identify and revoke API tokens that
are accidentally made public. The following partners currently report publicly
exposed API tokens to PyPI:

* https://github.com
* https://deps.dev

All PyPI users that use API tokens are opted into this by default, and no
action is necessary to benefit from this.

This API is for third parties who may find PyPI API tokens and wish to
report them to PyPI.

## Detecting the PyPI secret format

A PyPI API token is a string consisting of a prefix (``pypi``), a separator
(`-`) and a string representing a Macaroon `base64` serialized with
[PyMacaroon]:

    pypi-[A-Za-z0-9-_]{85,}

The `base64` string will not be shorter than 85 characters. A token can be
arbitrarily long because we may add arbitrary caveats to the serialized
Macaroon.

## Integrating

PyPI has adopted the [GitHub secret scanning reporting pattern].

### Public key identifier & signature

PyPI expects every request to this API to include two headers:

* A header containing a public key identifier
* A header containing a signature of the raw message body using this key

The names of these headers can be arbitrary and should be provided to PyPI at
integration time. They will be verified for every request.

PyPI assumes that the signature is an ECDSA signature, and that the digest is
SHA-256.

### Public key verification

PyPI expects to be able to verify the public key used to sign the request at a
URL provided at integration time. This URL structure is arbitrary but should
exist at a trusted domain.

Integrating parties should be prepared to provide P-256/384/521 keys, and use
SHA-256 only (not SHA-384 or SHA-512, despite those being common with P-384 and
P-521 respectively).

The response from a GET request to this URL should return a JSON document with
the following example structure:

```json
{
  "public_keys": [
    {
      "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a",
      "key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqUq\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n-----END PUBLIC KEY-----\n",
      "is_current": false
    },
    {
      "key_identifier": "bcb53661c06b4728e59d897fb6165d5c9cda0fd9cdf9d09ead458168deb7518c",
      "key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEYAGMWO8XgCamYKMJS6jc/qgvSlAd\nAjPuDPRcXU22YxgBrz+zoN19MzuRyW87qEt9/AmtoNP5GrobzUvQSyJFVw==\n-----END PUBLIC KEY-----\n",
      "is_current": true
    }
  ]
}
```

Note that more providing more than one key is not necessary. PyPI will not
accept responses for keys that are not marked as current at the time of
disclosure.

## Routes

### Reporting a secret

Route: `POST /_/secrets/disclose-token`

Accepts a report of one or more arbitrary API tokens, with details on where it
was located. The message body is a JSON array that contains one or more
objects, with each object representing a single secret match.

The keys for each secret match are:

* `token`: The value of the secret match (required)
* `type`: The type of token found (required)
* `url`: The public URL where the match was found (required)

Currently the only valid value for `type` is `"pypi_api_token"`

Additional fields may be provided but will be ignored.

Example request:

```http
POST /_/secrets/disclose-token HTTP/1.1
Host: pypi.org
Some-Public-Key-Identifier: ...
Some-Public-Key-Signature: ...

[
  {
    "token": "pypi-NMIfyYncKcRALEXAMPLE...",
    "type": "pypi_api_token",
    "url": "https://github.com/octocat/Hello-World/blob/12345600b9cbe38a219f39a9941c9319b600c002/foo/bar.txt",
  }
]
```

Status codes:

* `204 No Content` - We acknowledge the request but won't comment on the outcome.
* `400 Bad Request` - The request was in some way malformed and we are unable
   to process the report. The response body will contain a more detailed error
   message. The token was not disclosed and should be re-submitted.

[PyMacaroon]: https://pymacaroons.readthedocs.io/
[GitHub secret scanning reporting pattern]: https://docs.github.com/en/code-security/secret-scanning/secret-scanning-partnership-program/secret-scanning-partner-program
