Internals and Technical Details for PEP 740 on PyPI
===================================================

This page documents some of the internals and technical details behind
PyPI's implementation of :pep:`740`.

.. important::

  If you're a user of PyPI, you probably want the `attestation user docs`_
  instead.

Signing identities
------------------

A signing identity is a stable, human-readable identifier associated with a
public key. This identifier is used to perform semantic mappings for the
purpose of verification, e.g. to say "Alice signed for ``foo``," rather than
"Key ``0x1234...`` signed for ``foo``."

In traditional signing schemes, this is typically a "key identifier,"
such as a truncated hash of the key itself. In X.509-based PKIs it can be
the certificate's subject or other identifying material (such as a domain
name or email address).

As specified in PEP 740, signing identities for attestations are
*Trusted Publisher* identities. In practice, this means that the identity
expected to sign a distribution's attestation is expected to match the
Trusted Publisher that published the package.

For example, for a GitHub-based Trusted Publisher, the identity might be
``https://github.com/pypa/sampleproject/blob/main/.github/workflows/release.yml``,
i.e. ``pypa/sampleproject`` on GitHub, publishing from a workflow defined
on the ``main`` branch in the file ``release.yml``.

Attestation types
-----------------

The "scope" of the signing identity varies with the different attestation
types that can be uploaded to PyPI.

PyPI Publish Attestation
^^^^^^^^^^^^^^^^^^^^^^^^

A `PyPI Publish Attestation`_ is intended to
attest to the Trusted Publisher itself. Therefore, the identity used
is exactly the identity of the Trusted Publisher itself.

For example, using the GitHub-based Trusted Publisher above, the
expected signing identity will be **exactly**
``https://github.com/pypa/sampleproject/blob/main/.github/workflows/release.yml``.

SLSA Provenance
^^^^^^^^^^^^^^^

`SLSA Provenance`_ is intended to more generally trace a software artifact back
to its source.

Because of this, the identity used to verify a SLSA Provenance attestation
is slightly looser than for a PyPI Publish Attestation: any
identity under ``https://github.com/pypa/sampleproject`` is accepted, not just
ones corresponding to the ``release.yml`` workflow.

This is intended to reflect common CI/CD pipeline patterns: ``release.yml``
is not itself necessarily responsible for producing the distribution that
gets published, and so SLSA Provenance can't be assumed to be tightly bound to
it.

Consequently, downstream consumers/verifiers of SLSA Provenance attestations
may wish to further evaluate the attestation payload and signing identity
on a local policy basis.

Attestation object internals
----------------------------

This section is intended as a high-level walkthrough of a :pep:`740`
attestation object.

First: here is our contrived attestation object, which we've pulled
from a release of ``sampleproject``:

.. code-block:: bash

  http GET https://pypi.org/integrity/sampleproject/v4.0.0/sampleproject-4.0.0-py3-none-any.whl/provenance Accept:application/json \
    | jq '.attestation_bundles[0].attestations[0]'

yields:

.. code-block:: json

  {
    "envelope": {
      "signature": "MEQCIHAIF5F/e7GC6Ks9xmhP4JZcIOhLiX+tPXlD7wTPsCSVAiAPYs6cCAXYMZ3FqSlxfQ3Fx1GyrzqHawW+TaBUgRHu8A==",
      "statement": "eyJfdHlwZSI6Imh0dHBzOi8vaW4tdG90by5pby9TdGF0ZW1lbnQvdjEiLCJzdWJqZWN0IjpbeyJuYW1lIjoic2FtcGxlcHJvamVjdC00LjAuMC1weTMtbm9uZS1hbnkud2hsIiwiZGlnZXN0Ijp7InNoYTI1NiI6ImMyM2U0NDdlYTkwZDc5NmQxZTY0NWMzNWM0YjJkZTEyNTA0MGFkZDEyYTg0NTgyNTU0NmY5MWM5M2YzOTFiNmIifX1dLCJwcmVkaWNhdGVUeXBlIjoiaHR0cHM6Ly9kb2NzLnB5cGkub3JnL2F0dGVzdGF0aW9ucy9wdWJsaXNoL3YxIiwicHJlZGljYXRlIjpudWxsfQ=="
    },
    "verification_material": {
      "certificate": "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",
      "transparency_entries": [
        {
          "canonicalizedBody": "eyJhcGlWZXJzaW9uIjoiMC4wLjEiLCJraW5kIjoiZHNzZSIsInNwZWMiOnsiZW52ZWxvcGVIYXNoIjp7ImFsZ29yaXRobSI6InNoYTI1NiIsInZhbHVlIjoiMDMyYzUwMGI4MjYzY2U0ZDg2ZTA4ZWEzMWEyZDY4NzZjZGI5YjQ5Yzg4MDUyZGM2OTYxNTk4NmQxMzQ0NzY4MyJ9LCJwYXlsb2FkSGFzaCI6eyJhbGdvcml0aG0iOiJzaGEyNTYiLCJ2YWx1ZSI6IjE3NTYxNzdmZDZlZTI1YjQxMjM4NjdmN2MyZTkyMzRlYWQ0NDU1MGRiYmRiMjU5Yjk0ZTllYjRiNzVmZDRkNWQifSwic2lnbmF0dXJlcyI6W3sic2lnbmF0dXJlIjoiTUVRQ0lIQUlGNUYvZTdHQzZLczl4bWhQNEpaY0lPaExpWCt0UFhsRDd3VFBzQ1NWQWlBUFlzNmNDQVhZTVozRnFTbHhmUTNGeDFHeXJ6cUhhd1crVGFCVWdSSHU4QT09IiwidmVyaWZpZXIiOiJMUzB0TFMxQ1JVZEpUaUJEUlZKVVNVWkpRMEZVUlMwdExTMHRDazFKU1VkdlZFTkRRbWxwWjBGM1NVSkJaMGxVUm1GcEsxQkVTMkZyTVhoQk1VaE1jVEJ0YzJ0eGFFUldOWHBCUzBKblozRm9hMnBQVUZGUlJFRjZRVE1LVFZKVmQwVjNXVVJXVVZGTFJYZDRlbUZYWkhwa1J6bDVXbE0xYTFwWVdYaElha0ZqUW1kT1ZrSkJUVlJHV0U1d1dqTk9NR0l6U214TVYyeDFaRWRXZVFwaVYxWnJZVmRHTUZwVVFXVkdkekI1VGtSRmVFMUVXWGxOYWswelRVUmtZVVozTUhsT1JFVjRUVVJaZVUxcVVUTk5SR1JoVFVGQmQxZFVRVlJDWjJOeENtaHJhazlRVVVsQ1FtZG5jV2hyYWs5UVVVMUNRbmRPUTBGQlVtSjRNVVp6WlRKTWJqQXdUMjQxWVVaaFRDdHNTRTVIUmxsTVlYRmxTMFJrZFhCc1drUUtVRXBUSzNjeVVHcFpaazVRVERCbkwyNDBjMFJYUlZGR1dtWjVTVVY0UlZkTGRXeGFNa2RMVG5wQll6QXJVMjFWYnpSSlJsTkVRME5DVlZGM1JHZFpSQXBXVWpCUVFWRklMMEpCVVVSQloyVkJUVUpOUjBFeFZXUktVVkZOVFVGdlIwTkRjMGRCVVZWR1FuZE5SRTFDTUVkQk1WVmtSR2RSVjBKQ1ZDOTFVMFZKQ2xodFVYcDFVbXR3Y0ZkWWNsUkxWbXRtV2taS1lucEJaa0puVGxaSVUwMUZSMFJCVjJkQ1ZHWXdLMjVRVm1sUlVteDJiVzh5VDJ0dlZtRk1SMHhvYUdzS1VIcENhRUpuVGxaSVVrVkNRV1k0UlZaNlFsWm9iRTV2WkVoU2QyTjZiM1pNTW1Sd1pFZG9NVmxwTldwaU1qQjJZMGhzZDFsVE9YcFpWekYzWWtkV2R3cGpiVGx4V2xkT01FeDVOVzVoV0ZKdlpGZEpkbVF5T1hsaE1scHpZak5rZWt3elNteGlSMVpvWXpKVmRXVlhNWE5SU0Vwc1dtNU5kbUZIVm1oYVNFMTJDbUpYUm5CaWFrRTFRbWR2Y2tKblJVVkJXVTh2VFVGRlFrSkRkRzlrU0ZKM1kzcHZka3d6VW5aaE1sWjFURzFHYW1SSGJIWmliazExV2pKc01HRklWbWtLWkZoT2JHTnRUblppYmxKc1ltNVJkVmt5T1hSTlFrbEhRMmx6UjBGUlVVSm5OemgzUVZGSlJVSklRakZqTW1kM1RtZFpTMHQzV1VKQ1FVZEVkbnBCUWdwQmQxRnZUbXBKZUZwVVVUVk9lbEpxV1ZSSk1Wa3lWVEZOZWtVelRucE9hMXBYV1RGUFJGcHBXVlJPYkZwRWFHeE9lazB5V1dwT2JWbDZRVlpDWjI5eUNrSm5SVVZCV1U4dlRVRkZSVUpCWkZOYVYzaHNXVmhPYkUxRFFVZERhWE5IUVZGUlFtYzNPSGRCVVZWRlJXNUNOV05IUlhaak1rWjBZMGQ0YkdOSVNuWUtZVzFXYW1SRVFXUkNaMjl5UW1kRlJVRlpUeTlOUVVWSFFrRTVlVnBYV25wTU1taHNXVmRTZWt3eU1XaGhWelIzVDNkWlMwdDNXVUpDUVVkRWRucEJRZ3BEUVZGMFJFTjBiMlJJVW5kamVtOTJURE5TZG1FeVZuVk1iVVpxWkVkc2RtSnVUWFZhTW13d1lVaFdhV1JZVG14amJVNTJZbTVTYkdKdVVYVlpNamwwQ2sxSFRVZERhWE5IUVZGUlFtYzNPSGRCVVd0RlZsRjRWR0ZJVWpCalNFMDJUSGs1Ym1GWVVtOWtWMGwxV1RJNWRFd3pRalZqUjBWMll6SkdkR05IZUd3S1kwaEtkbUZ0Vm1wa1F6aDFXakpzTUdGSVZtbE1NMlIyWTIxMGJXSkhPVE5qZVRsNVdsZDRiRmxZVG14TWJteDBZa1ZDZVZwWFducE1NbWhzV1ZkU2VncE1NakZvWVZjMGQwOUJXVXRMZDFsQ1FrRkhSSFo2UVVKRFoxRnhSRU5uTWsxcVJteE9SR3N6VGtkT2FFMXFWbXBhVkZWNlRWUmpNMDB5VW14YWFsVTBDazV0U21oTk1sWnJUMGRWTTAxNldtbE5NbHBxVFVJd1IwTnBjMGRCVVZGQ1p6YzRkMEZSYzBWRWQzZE9XakpzTUdGSVZtbE1WMmgyWXpOU2JGcEVRVEVLUW1kdmNrSm5SVVZCV1U4dlRVRkZUVUpEWTAxS1YyZ3daRWhDZWs5cE9IWmFNbXd3WVVoV2FVeHRUblppVXpsM1pWaENhRXd6VG1oaVdFSnpXbGhDZVFwaU1uQnNXVE5SZDA5QldVdExkMWxDUWtGSFJIWjZRVUpFVVZGeFJFTm5NazFxUm14T1JHc3pUa2RPYUUxcVZtcGFWRlY2VFZSak0wMHlVbXhhYWxVMENrNXRTbWhOTWxaclQwZFZNMDE2V21sTk1scHFUVUk0UjBOcGMwZEJVVkZDWnpjNGQwRlJORVZGVVhkUVkyMVdiV041T1c5YVYwWnJZM2s1ZEZsWGJIVUtUVUpuUjBOcGMwZEJVVkZDWnpjNGQwRlJPRVZEWjNkSlRWUlJORTlVYXpGUFZGbDNTbmRaUzB0M1dVSkNRVWRFZG5wQlFrVkJVVnBFUW1SdlpFaFNkd3BqZW05MlRESmtjR1JIYURGWmFUVnFZakl3ZG1OSWJIZFpWRUZYUW1kdmNrSm5SVVZCV1U4dlRVRkZVa0pCWjAxQ2Fsa3dUbnBCZVU1VVFtcENaMjl5Q2tKblJVVkJXVTh2VFVGRlUwSkdWVTFWTW1nd1pFaENlazlwT0haYU1td3dZVWhXYVV4dFRuWmlVemwzWlZoQ2FFd3pUbWhpV0VKeldsaENlV0l5Y0d3S1dUTlJka3h0WkhCa1IyZ3hXV2s1TTJJelNuSmFiWGgyWkROTmRtTnRWbk5hVjBaNldsTTFOV0pYZUVGamJWWnRZM2s1YjFwWFJtdGplVGwwV1Zkc2RRcE5SR2RIUTJselIwRlJVVUpuTnpoM1FWSk5SVXRuZDI5T2FrbDRXbFJSTlU1NlVtcFpWRWt4V1RKVk1VMTZSVE5PZWs1cldsZFpNVTlFV21sWlZFNXNDbHBFYUd4T2VrMHlXV3BPYlZsNlFWVkNaMjl5UW1kRlJVRlpUeTlOUVVWVlFrRlpUVUpJUWpGak1tZDNWMUZaUzB0M1dVSkNRVWRFZG5wQlFrWlJVa3dLUkVWc2IyUklVbmRqZW05MlRESmtjR1JIYURGWmFUVnFZakl3ZG1OSWJIZFpVemw2V1ZjeGQySkhWbmRqYlRseFdsZE9NRXd5Um1wa1IyeDJZbTVOZGdwamJsWjFZM2s0ZUUxVVkzaE5la0Y2VDBSck5FMVRPV2hrU0ZKc1lsaENNR041T0hoTlFsbEhRMmx6UjBGUlVVSm5OemgzUVZKWlJVTkJkMGRqU0ZacENtSkhiR3BOU1VkTFFtZHZja0puUlVWQlpGbzFRV2RSUTBKSWQwVmxaMEkwUVVoWlFUTlVNSGRoYzJKSVJWUktha2RTTkdOdFYyTXpRWEZLUzFoeWFtVUtVRXN6TDJnMGNIbG5Remh3TjI4MFFVRkJSMVJCTlM5WU5VRkJRVUpCVFVGU2VrSkdRV2xCTm01WlN6QkhlSEZXZWtwMWRISnFjbGxCTVdKQlNVdElWUXBxUjNKelNFMU1jazlLVkZSRlZXbEZVa0ZKYUVGS1dtOTBRVlJ1VTNkc1MzUTNRek5hZDJoNE0yWmpVM0pvUjJaUFlXdFViRTB5ZHlzNGNXMXNkR05xQ2sxQmIwZERRM0ZIVTAwME9VSkJUVVJCTW1OQlRVZFJRMDFDSzJsc2MxQm5lVFI1YmxWSE9VZDBjVVJGUW5GWE9DdGFjV3BZTmt4d2RYaFJjV3BEY2pjS2N6UjVkSGwwTW5Cd1JtUm5hbkpIY2tjeFJGazBibE5hZEZGSmQySnNjbWR4T1hRNWFYcEJUVlJyU21WeGFGRkNjekpQVldsNVNVcGFhWEJqWlVRMWRncEJRVVV2VG1ablpDODVkVXN3VFZwQlNFWnpUR2RoYkhGUFFtdzRDaTB0TFMwdFJVNUVJRU5GVWxSSlJrbERRVlJGTFMwdExTMEsifV19fQ==",
          "inclusionPromise": {
            "signedEntryTimestamp": "MEQCIF/N/GzwLypgHSlaRpDtl6oTZ4cmviE++Z+aY5ksSWKWAiAlenzSiy6/zvFAo44EJSvvXPp8P+YiKZUxhaQPoVP5Wg=="
          },
          "inclusionProof": {
            "checkpoint": {
              "envelope": "rekor.sigstore.dev - 1193050959916656506\n25232885\nwfIuS5NLOf+4rU8wVjPaezQYEVVpf3aF1G/BfRYMXew=\n\n— rekor.sigstore.dev wNI9ajBFAiAj+8BDcU0CKq9AJ1uOND6fCQ/ugLsk1xnSz0IpXoaE+AIhALUXqsTZ40Mt2X30WNlk6baivF1KA4V4rrjbPNVo9eFC\n"
            },
            "hashes": [
              "4bt58suSLj7v+PP3+G6iSxOJV7xu75I78Fh9SZAVbho=",
              "VzJk3yFgaaO7bC/HxvHYPX2g22PiTWKDf0afdGrvceY=",
              "nLzU/ukEW1eoGR2I2UulWDBG6VLtYrA7rNJnei8kH8s=",
              "S182UV88MERSxCgUSBcfhCHJDuyUrAIs/fFmCbpjWgg=",
              "PWqRmPYAwa1fq6R1qSrYlOxCtiKnFZq9hnNt7XwCIA8=",
              "KHxYP0XNSf1yKjp+xY/5Kkckw0Yweyjx9Z6qn2+pnZM=",
              "8/b9kmTAbALhl4EaKIH4uMXhES9ILB0XQkuH44FltJY=",
              "mXfX9NDkaWje6HpniWis2CBELUGjv8LiW2jeMOclCs0=",
              "jRPOva2IEma7ZE7mPN3xHtEnXtMF/HNvrmbC5TKTy14=",
              "s8vUdxeRlxXWTCMdSLhiSzRiYM3eGsVvrm+5HWkTNBc=",
              "4lUF0YOu9XkIDXKXA0wMSzd6VeDY3TZAgmoOeWmS2+Y=",
              "gf+9m552B3PnkWnO0o4KdVvjcT3WVHLrCbf1DoVYKFw="
            ],
            "logIndex": "25232882",
            "rootHash": "wfIuS5NLOf+4rU8wVjPaezQYEVVpf3aF1G/BfRYMXew=",
            "treeSize": "25232885"
          },
          "integratedTime": "1730932628",
          "kindVersion": {
            "kind": "dsse",
            "version": "0.0.1"
          },
          "logId": {
            "keyId": "wNI9atQGlz+VWfO6LRygH4QUfY/8W4RFwiT5i5WRgB0="
          },
          "logIndex": "147137144"
        }
      ]
    },
    "version": 1
  }


Verification material
^^^^^^^^^^^^^^^^^^^^^

The ``verification_material`` conveys the materials used the verify the
attestation.

The ``certificate`` is the most relevant field: it's a base64-encoded DER X.509
certificate, which we can inspect as follows:

.. code-block:: bash

  # put the JSON above in /tmp/attestation.json
  jq -r .verification_material.certificate < /tmp/attestation.json \
    | base64 -d \
    | openssl x509 -inform DER -text -noout

producing (abbreviated for clarity):

.. code-block::

  Certificate:
      Data:
          Version: 3 (0x2)
          Serial Number:
              15:a8:be:3c:32:9a:93:5c:40:d4:72:ea:d2:6b:24:aa:10:d5:e7
          Signature Algorithm: ecdsa-with-SHA384
          Issuer: O=sigstore.dev, CN=sigstore-intermediate
          Validity
              Not Before: Nov  6 22:37:07 2024 GMT
              Not After : Nov  6 22:47:07 2024 GMT
          Subject:
          Subject Public Key Info:
              Public Key Algorithm: id-ecPublicKey
                  Public-Key: (256 bit)
                  pub:
                      ...
                  ASN1 OID: prime256v1
                  NIST CURVE: P-256
          X509v3 extensions:
              X509v3 Key Usage: critical
                  Digital Signature
              X509v3 Extended Key Usage:
                  Code Signing
              X509v3 Subject Key Identifier:
                  FF:B9:21:08:5E:64:33:B9:19:29:A5:65:EB:4C:A5:64:7D:91:49:6F
              X509v3 Authority Key Identifier:
                  DF:D3:E9:CF:56:24:11:96:F9:A8:D8:E9:28:55:A2:C6:2E:18:64:3F
              X509v3 Subject Alternative Name: critical
                  URI:https://github.com/pypa/sampleproject/.github/workflows/release.yml@refs/heads/main
              1.3.6.1.4.1.57264.1.1:
                  https://token.actions.githubusercontent.com
      Signature Algorithm: ecdsa-with-SHA384
      Signature Value:
          30:64:02:30:1f:a2:96:c3:e0:cb:8c:a7:50:6f:46:b6:a0:c4:
          06:a5:bc:f9:9a:a3:5f:a2:e9:bb:14:2a:8c:2a:fb:b3:8c:ad:
          ca:dd:a9:a4:57:60:8e:b1:ab:1b:50:d8:e2:74:99:b5:02:30:
          6e:5a:e0:ab:db:7d:8b:30:0c:4e:42:5e:aa:14:01:b3:63:94:
          8b:22:09:66:2a:5c:78:3e:6f:00:01:3f:35:f8:1d:ff:db:8a:
          d0:c6:40:1c:5b:0b:81:a9:6a:38:19:7c



In this case, we can see that the certificate binds a public key
to an identity (``https://github.com/pypa/sampleproject/.github/workflows/release.yml@refs/heads/main``),
which is verified against the project's registered Trusted Publishers
at upload time.

Envelope
^^^^^^^^

The ``envelope`` key contains two components:

* The ``statement``, which contains the core, signed-over in-toto Statement:

  .. code-block:: bash

    jq -r .envelope.statement < /tmp/attestation.json | base64 -d | jq

  yielding:

  .. code-block:: json

    {
      "_type": "https://in-toto.io/Statement/v1",
      "subject": [
        {
          "name": "sampleproject-4.0.0-py3-none-any.whl",
          "digest": {
            "sha256": "c23e447ea90d796d1e645c35c4b2de125040add12a845825546f91c93f391b6b"
          }
        }
      ],
      "predicateType": "https://docs.pypi.org/attestations/publish/v1",
      "predicate": null
    }


* The ``signature``, which contains the base64-encoded signature over
  ``statement``.

  The ``signature`` can be verified using the public key bound within
  ``verification_material.certificate``, fully linking the attestation back to
  the identity that produced it.

  The signing process itself is not "bare": instead of directly signing over
  ``statement``, the payload is computed using the `DSSE PAE encoding`_:

  .. code-block::

    SIGNATURE = Sign(PAE(UTF8(PAYLOAD_TYPE), SERIALIZED_BODY))

  where:

  * ``PAYLOAD_TYPE`` is fixed as ``application/vnd.in-toto+json``
  * ``SERIALIZED_BODY`` is the JSON-encoded ``statement``, per above
  * ``PAE`` is the "pre-authentication encoding", defined as:

    .. code-block::

      PAE(type, body) = "DSSEv1" + SP + LEN(type) + SP + type + SP + LEN(body) + SP + body
      +               = concatenation
      SP              = ASCII space [0x20]
      "DSSEv1"        = ASCII [0x44, 0x53, 0x53, 0x45, 0x76, 0x31]
      LEN(s)          = ASCII decimal encoding of the byte length of s, with no leading zeros

  Thus, the actual signed-over payload roughly resembles:

  .. code-block::

    DSSEv1 28 application/vnd.in-toto+json 272 {"_type":"https://in-toto.io/Statement/v1","subject":[{"name":"pypi_attestation_models-0.0.4a2.tar.gz","digest":{"sha256":"c9709ce6fd5b67b59b4a28758cf14d3f411803c4b89b6068b1f1a8e4ee94c8ef"}}],"predicateType":"https://docs.pypi.org/attestations/publish/v1","predicate":{}}

"Why is the ``predicate`` empty?"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You may have noticed that the in-toto Statement above contains a
predicate of type ``https://docs.pypi.org/attestations/publish/v1``, but with an
empty ``predicate`` body (``{}``).

This is intentional! A publish attestation **does not require** a custom
predicate, since all of the state associated with a Trusted Publisher
is fully encapsulated in the ``verification_material.certificate`` being
used to verify the ``envelope.statement``'s signature.

Verifying an attestation object
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Attestation object verification is described at a high level in :pep:`740`.

.. warning::

  Users are **strongly discouraged** from implementing the steps below in an
  ad-hoc manner, since they involve error-prone X.509 and transparency log
  operations. Instead, we **strongly encourage** integrators to use
  either `pypi-attestation-models`_ or `sigstore-python`_'s pre-existing APIs
  for attestation manipulation, signing, and verification.

Using the details above, we can provide the steps with slightly more accuracy:

1. Retrieve the distribution (sdist or wheel) being verified and its
   attestation. We'll call these ``sampleproject-4.0.0.tar.gz`` and
   ``sampleproject-4.0.0.tar.gz.publish.attestation``, respectively.

2. Verify that the attestation's ``verification_material.certificate`` is valid
   and chains up to the expected root of trust (i.e., the Sigstore public
   good instance) *and* has the expected subject (i.e., the subject matches
   a valid Trusted Publisher for project ``sampleproject``).

   .. note::

    The "expected subject" is the expected signing identity, which the verifier
    must establish trust in. For example, depending on the security model,
    the verifier could either establish *a priori* that a given CI/CD identity
    is responsible for publishing a given package, or could perform a
    TOFU-style setup where the first identity associated with the package
    is considered the trusted one.

   .. note::

     This step is equivalent to Sigstore "bundle" verification and also requires
     a source of signed time, such as the ``verification_material.transparency_entries``.

3. Verify that the attestation's ``envelope.signature`` is valid for
   ``envelope.statement``, using the `DSSE PAE encoding`_ and the public key of
   ``verification_material.certificate``.

4. Decode the ``envelope.statement``, verify that it's an in-toto Statement
   with the expected ``subject`` (``sampleproject-4.0.0.tar.gz``) and subject digest
   (the SHA-256 of ``sampleproject-4.0.0.tar.gz``'s contents).

5. Confirm that the statement's ``payloadType`` is one of the attestation types
   supported by PyPI, and perform any ``payload``-specific processing.
   For the PyPI Publish attestation, no ``payload`` is present, and therefore
   no additional processing is necessary.

If any of the steps above fail, the attestation should be considered invalid
and any operations on its associated distribution should halt.

.. _`attestation user docs`: https://docs.pypi.org/attestations/

.. _`PyPI Publish attestation`: https://docs.pypi.org/attestations/publish/v1

.. _`SLSA Provenance`: https://slsa.dev/spec/v1.0/provenance

.. _`DSSE PAE encoding`: https://github.com/secure-systems-lab/dsse/blob/v1.0.0/protocol.md

.. _`pypi-attestation-models`: https://github.com/trailofbits/pypi-attestation-models

.. _`sigstore-python`: https://github.com/sigstore/sigstore-python
