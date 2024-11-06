# Integrity API

<!--[[ preview('user-api-docs') ]]-->

The Integrity API provides access to PyPI's implementation of [PEP 740].

## Concepts

The concepts and objects in the Integrity API closely mirror [PEP 740]:

* **Attestation objects** encapsulate a single "attestation" for a single file,
  such as a [publish attestation] or [SLSA Provenance].

* **Provenance objects** encapsulate *one or more* attestations for a given
  file, bundling them with the *identity* that produced them.

The Integrity API deals in provenance objects; users should extract and verify
individual attestations from a file's provenance, as appropriate.

## Routes

### `GET /integrity/<project>/<version>/<filename>/provenance`

Get the provenance object for the given `<filename>`.

This endpoint is currently only available as JSON.

Example JSON request (default if no `Accept` header is passed):

```http
GET /integrity/sampleproject/1.0.0/sampleproject-1.0.0.tar.gz/provenance HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.integrity.v1+json
```

??? note "Example JSON response"

    This is an example response, demonstrating a provenance object containing
    one attestation and its Trusted Publishing identity.

    ```json
    {
        "version": 1,
        "attestation_bundles": [
            {
                "publisher": {
                    "kind": "GitHub",
                    "claims": null,
                    "repository": "trailofbits/rfc8785.py",
                    "workflow": "release.yml",
                    "environment": null
                },
                "attestations": [
                    {
                        "version": 1,
                        "verification_material": {
                            "certificate": "MIIC0zCCAlmgAwIBAgIUNa1+nVgkOX1xlssDyRyt0DZ6M5UwCgYIKoZIzj0EAwMwNzEVMBMGA1UEChMMc2lnc3RvcmUuZGV2MR4wHAYDVQQDExVzaWdzdG9yZS1pbnRlcm1lZGlhdGUwHhcNMjQwNjA2MTgzOTA1WhcNMjQwNjA2MTg0OTA1WjAAMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEyrm8stLQwPX/MdVS50NZ4gmXEPEh6kYlvhEo079Yk1lMMmMobwFvINC8Lc02kg+03BMscXbM/OKv3Fl1qH9PCKOCAXgwggF0MA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAzAdBgNVHQ4EFgQUn98gJQymjI+dFUDEea6CKbQngj4wHwYDVR0jBBgwFoAUcYYwphR8Ym/599b0BRp/X//rb6wwIwYDVR0RAQH/BBkwF4EVd2lsbGlhbUB5b3NzYXJpYW4ubmV0MCwGCisGAQQBg78wAQEEHmh0dHBzOi8vZ2l0aHViLmNvbS9sb2dpbi9vYXV0aDAuBgorBgEEAYO/MAEIBCAMHmh0dHBzOi8vZ2l0aHViLmNvbS9sb2dpbi9vYXV0aDCBiQYKKwYBBAHWeQIEAgR7BHkAdwB1ACswvNxoiMni4dgmKV50H0g5MZYC8pwzy15DQP6yrIZ6AAABj+7Y7/YAAAQDAEYwRAIgTWyPyS2CKRm5ZUaTwngfBtrOJozwlIfOOfXHyyej0BQCIGCwmYVKhNS7JbUTFeDe90SWNlpwl5YAVDb/2GGFxGNCMAoGCCqGSM49BAMDA2gAMGUCMQCxIekmLNdhAS7HVo6CRgqVRht8RiFO6lbyGK4fDuEQOk/MPaBlRhsaUxwejf7jI2kCMCw5AOijMvqsXHjZYk7TfRH/079Zy0qEWjD9lurfPiTX9qSQKSiXORvxpk/DQsfTsg==",
                            "transparency_entries": [
                                {
                                    "logIndex": "28175749",
                                    "logId": {
                                        "keyId": "0y8wo8MtY5wrdiIFohx7sHeI5oKDpK5vQhGHI6G+pJY="
                                    },
                                    "kindVersion": {
                                        "kind": "dsse",
                                        "version": "0.0.1"
                                    },
                                    "integratedTime": "1717699145",
                                    "inclusionPromise": {
                                        "signedEntryTimestamp": "MEYCIQDx9J86FXVVe/PIoY5jHvlQJ85A6oZ2BiZ6/3ZYe3EeAQIhALl97dZebI/Smm0qQMdVVkbVznthHZCaSClN4djajx3G"
                                    },
                                    "inclusionProof": {
                                        "logIndex": "28160930",
                                        "rootHash": "zWVcqCxxaF+b1WWfb+xZZlQYK4MdEr81Dd0KzOFu0Ko=",
                                        "treeSize": "28160931",
                                        "hashes": [
                                            "qDMDpEGtUE3c8CnnlguBb24eYIGo+nv0wGjN2Wdq1V8=",
                                            "r3g45oVhy3zCnIK7lkTsH8Sg1Qdy0kH/CqfaBUE0yok=",
                                            "XAv5fJtrNK1YPZwvB0JIVOOwWiLHk/oWoqzN1xzF9t4=",
                                            "14fYRBMB/6rTWV5Qpei46FU+7rHmaqqLFV/K22kI6sg=",
                                            "KhgfVnUZkrYVk1Je+xSJ3iT5wZMgut38srFhH/iVsWQ=",
                                            "C9LjSdxA96yalX4DOGX/fV0kuhx9LLU1BERodtxE+No=",
                                            "NwfjLTWUBnDymaU+Ca/ykaXOiGNRvIt5/5ZZDzEyTyA=",
                                            "jKHh3ZbaWLoBLn5qZTUpiw9oPlStl/ZSfPmdsHte+AQ=",
                                            "ekhZZrQ/riDDmsvqy3I4gAcbUBcoyoNMChiDAXsTu3Y=",
                                            "oMHAlypWw/lk5Q9JHd9O5UJZ7bdcH6Gzs+zCES7YUKo=",
                                            "Kn3gkyUwY86Ut3fWtexgSLtxteycn2p6k7Kj7qJFEDw=",
                                            "IfPx7HUTjLRrRAy6mhkYP/7aq48i6G+Mk/NQidZPJk8=",
                                            "Edul4W41O3EfxKEEMlX2nW0+GTgCv00nGmcpwhALgVA=",
                                            "rBWB37+HwkTZgDv0rMtGBUoDI0UZqcgDZp48M6CaUlA="
                                        ],
                                        "checkpoint": {
                                            "envelope": "rekor.sigstage.dev - 8050909264565447525\\n28160931\\nzWVcqCxxaF+b1WWfb+xZZlQYK4MdEr81Dd0KzOFu0Ko=\\n\\n— rekor.sigstage.dev 0y8wozBFAiBOHi+eUTSSX6mrNLjQwoKJLum7cpnVpvAb8QwK+DnLngIhAO2170Q0xfbOMwrbF2sM80z1wkYhnlVRidI+/j4/k4JJ\\n"
                                        }
                                    },
                                    "canonicalizedBody": "eyJhcGlWZXJzaW9uIjoiMC4wLjEiLCJraW5kIjoiZHNzZSIsInNwZWMiOnsiZW52ZWxvcGVIYXNoIjp7ImFsZ29yaXRobSI6InNoYTI1NiIsInZhbHVlIjoiZGY1MDk2Njg2NzNkMmY4MjAxOTQ2ZTBmNTliNmFiNzhiZWY0NmYyMTc5NTc5N2EzYjJkMTUyZjc3NmFmYzEyZSJ9LCJwYXlsb2FkSGFzaCI6eyJhbGdvcml0aG0iOiJzaGEyNTYiLCJ2YWx1ZSI6IjcyOTM0Yjc1YzgxODk3ZWE4Yjg4NTk0N2ExOWRjODE4ZWUzNjIwYzUwMzJhZmIzYjc4ODc3ZmJjYmI3MjMwYzEifSwic2lnbmF0dXJlcyI6W3sic2lnbmF0dXJlIjoiTUVVQ0lBdmtSSEZ1K24yenMvNGorVjNjTTIyRFZaSTF6cUs0TmpmbHphdEVRTWZnQWlFQW82VjNaN3RpaE9Ha1lpeXNGMTh4dFpWcWVPdDNyZHdWVmI3Nm1XcDhETWM9IiwidmVyaWZpZXIiOiJMUzB0TFMxQ1JVZEpUaUJEUlZKVVNVWkpRMEZVUlMwdExTMHRDazFKU1VNd2VrTkRRV3h0WjBGM1NVSkJaMGxWVG1FeEsyNVdaMnRQV0RGNGJITnpSSGxTZVhRd1JGbzJUVFZWZDBObldVbExiMXBKZW1vd1JVRjNUWGNLVG5wRlZrMUNUVWRCTVZWRlEyaE5UV015Ykc1ak0xSjJZMjFWZFZwSFZqSk5ValIzU0VGWlJGWlJVVVJGZUZaNllWZGtlbVJIT1hsYVV6RndZbTVTYkFwamJURnNXa2RzYUdSSFZYZElhR05PVFdwUmQwNXFRVEpOVkdkNlQxUkJNVmRvWTA1TmFsRjNUbXBCTWsxVVp6QlBWRUV4VjJwQlFVMUdhM2RGZDFsSUNrdHZXa2w2YWpCRFFWRlpTVXR2V2tsNmFqQkVRVkZqUkZGblFVVjVjbTA0YzNSTVVYZFFXQzlOWkZaVE5UQk9XalJuYlZoRlVFVm9ObXRaYkhab1JXOEtNRGM1V1dzeGJFMU5iVTF2WW5kR2RrbE9RemhNWXpBeWEyY3JNRE5DVFhOaldHSk5MMDlMZGpOR2JERnhTRGxRUTB0UFEwRllaM2RuWjBZd1RVRTBSd3BCTVZWa1JIZEZRaTkzVVVWQmQwbElaMFJCVkVKblRsWklVMVZGUkVSQlMwSm5aM0pDWjBWR1FsRmpSRUY2UVdSQ1owNVdTRkUwUlVablVWVnVPVGhuQ2twUmVXMXFTU3RrUmxWRVJXVmhOa05MWWxGdVoybzBkMGgzV1VSV1VqQnFRa0puZDBadlFWVmpXVmwzY0doU09GbHRMelU1T1dJd1FsSndMMWd2TDNJS1lqWjNkMGwzV1VSV1VqQlNRVkZJTDBKQ2EzZEdORVZXWkRKc2MySkhiR2hpVlVJMVlqTk9lbGxZU25CWlZ6UjFZbTFXTUUxRGQwZERhWE5IUVZGUlFncG5OemgzUVZGRlJVaHRhREJrU0VKNlQyazRkbG95YkRCaFNGWnBURzFPZG1KVE9YTmlNbVJ3WW1rNWRsbFlWakJoUkVGMVFtZHZja0puUlVWQldVOHZDazFCUlVsQ1EwRk5TRzFvTUdSSVFucFBhVGgyV2pKc01HRklWbWxNYlU1MllsTTVjMkl5WkhCaWFUbDJXVmhXTUdGRVEwSnBVVmxMUzNkWlFrSkJTRmNLWlZGSlJVRm5VamRDU0d0QlpIZENNVUZEYzNkMlRuaHZhVTF1YVRSa1oyMUxWalV3U0RCbk5VMWFXVU00Y0hkNmVURTFSRkZRTm5seVNWbzJRVUZCUWdwcUt6ZFpOeTlaUVVGQlVVUkJSVmwzVWtGSloxUlhlVkI1VXpKRFMxSnROVnBWWVZSM2JtZG1RblJ5VDBwdmVuZHNTV1pQVDJaWVNIbDVaV293UWxGRENrbEhRM2R0V1ZaTGFFNVROMHBpVlZSR1pVUmxPVEJUVjA1c2NIZHNOVmxCVmtSaUx6SkhSMFo0UjA1RFRVRnZSME5EY1VkVFRUUTVRa0ZOUkVFeVowRUtUVWRWUTAxUlEzaEpaV3R0VEU1a2FFRlROMGhXYnpaRFVtZHhWbEpvZERoU2FVWlBObXhpZVVkTE5HWkVkVVZSVDJzdlRWQmhRbXhTYUhOaFZYaDNaUXBxWmpkcVNUSnJRMDFEZHpWQlQybHFUWFp4YzFoSWFscFphemRVWmxKSUx6QTNPVnA1TUhGRlYycEVPV3gxY21aUWFWUllPWEZUVVV0VGFWaFBVblo0Q25CckwwUlJjMlpVYzJjOVBRb3RMUzB0TFVWT1JDQkRSVkpVU1VaSlEwRlVSUzB0TFMwdENnPT0ifV19fQ=="
                                }
                            ]
                        },
                        "envelope": {
                            "statement": "eyJfdHlwZSI6Imh0dHBzOi8vaW4tdG90by5pby9TdGF0ZW1lbnQvdjEiLCJzdWJqZWN0IjpbeyJuYW1lIjoicmZjODc4NS0wLjEuMi1weTMtbm9uZS1hbnkud2hsIiwiZGlnZXN0Ijp7InNoYTI1NiI6ImM0ZTkyZTllY2M4MjhiZWYyYWE3ZGJhMWRlOGFjOTgzNTExZjc1MzJhMGRmMTFjNzcwZDM5MDk5YTI1Y2YyMDEifX1dLCJwcmVkaWNhdGVUeXBlIjoiaHR0cHM6Ly9kb2NzLnB5cGkub3JnL2F0dGVzdGF0aW9ucy9wdWJsaXNoL3YxIiwicHJlZGljYXRlIjpudWxsfQ==",
                            "signature": "MEUCIAvkRHFu+n2zs/4j+V3cM22DVZI1zqK4NjflzatEQMfgAiEAo6V3Z7tihOGkYiysF18xtZVqeOt3rdwVVb76mWp8DMc="
                        }
                    }
                ]
            }
        ]
    }
    ```

#### Status codes

* `200 OK` - no error, provenance is available
* `403 Forbidden` - access is temporarily disabled by the PyPI administrators
* `404 Not Found` - file has no provenance
* `406 Not Acceptable` - `Accept:` header not recognized

[PEP 740]: https://peps.python.org/pep-0740/

[publish attestation]: /attestations/publish/v1

[SLSA Provenance]: https://slsa.dev/spec/v1.0/provenance
