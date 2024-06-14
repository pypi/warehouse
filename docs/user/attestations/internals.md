---
title: Internals and Technical Details
---

<!--[[ preview('index-attestations') ]]-->

!!! note

    This page is **not useful** to end users!

    It's intended primarily for PyPI developers and developers of other
    package indices looking to support digital attestations.

## Signing identities

A signing identity is a stable, human-readable identifier associated with a
public key. This identifier is used to perform semantic mappings for the
purpose of verification, e.g. to say "Alice signed for `foo`," rather than
"Key `0x1234...` signed for `foo`."

In traditional signing schemes, this is typically a "key identifier,"
such as a truncated hash of the key itself. In X.509-based PKIs it can be
the certificate's subject or other identifying material (such as a domain
name or email address).

As specified in PEP 740, signing identities for index attestations are
*Trusted Publisher* identities. In practice, this means that the identity
expected to sign a distribution's attestation is expected to match the
Trusted Publisher that published the package.

For example, for a GitHub-based Trusted Publisher, the identity might be
`https://github.com/pypa/sampleproject/blob/main/.github/workflows/release.yml`,
i.e. `pypa/sampleproject` on GitHub, publishing from a workflow defined
in `release.yml`.

### Future identities

In the future, PyPI may allow signing identities other than the project's
Trusted Publishers. Some potential future signing identities include:

* E-mail addresses, checked against the project's owners' profiles
  and/or against the uploaded distribution's own metadata.
* Third-party identities (such as GitHub or GitLab usernames), checked against
  the uploaded distribution's own metadata.

## Attestation types

The "scope" of the signing identity varies with the different attestation
types that can be uploaded to PyPI.

### PyPI Publish Attestation

A [PyPI Publish Attestation](/attestations/publish/v1/) is intended to
attest to the Trusted Publisher itself. Therefore, the identity used
is exactly the identity of the Trusted Publisher itself.

For example, using the GitHub-based Trusted Publisher above, the
expected signing identity will be **exactly**
`https://github.com/pypa/sampleproject/blob/main/.github/workflows/release.yml`.

### SLSA Provenance

[SLSA Provenance](https://slsa.dev/spec/v1.0/provenance) is intended to more
generally trace a software artifact back to its source.

Because of this, the identity used to verify a SLSA Provenance attestation
is slightly looser than for a PyPI Publish Attestation: any
identity under `https://github.com/pypa/sampleproject` is accepted, not just
ones corresponding to the `release.yml` workflow.

This is intended to reflect common CI/CD pipeline patterns: `release.yml`
is not itself necessarily responsible for producing the distribution that
gets published, and so SLSA Provenance can't be assumed to be tightly bound to
it.

Consequently, downstream consumers/verifiers of SLSA Provenance attestations
may wish to further evaluate the attestation payload and signing identity
on a local policy basis.

### Future attestations

Per [future identities](#future-identities), PyPI may allow additional
attestation types in the future. These future types may depend on future
identities. Some potential future attestation types:

* Third-party review attestations, e.g. manual review or automatic scanning
  from security tooling.
* "Release" attestations from the index itself, attesting that PyPI has
  actually made a particular distribution available for public download.

## Attestation object internals

This section is intended as a high-level walkthrough of a PEP 740 attestation
object.

First: here is our contrived attestation object:

```json
{
    "version": 1,
    "verification_material": {
        "certificate": "MIIHJzCCBqygAwIBAgIUKFaqF8lQso8y4M2NGFu2V6FmeIMwCgYIKoZIzj0EAwMwNzEVMBMGA1UE\nChMMc2lnc3RvcmUuZGV2MR4wHAYDVQQDExVzaWdzdG9yZS1pbnRlcm1lZGlhdGUwHhcNMjQwNjEw\nMTk0NzI1WhcNMjQwNjEwMTk1NzI1WjAAMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEZWx0M6hz\nAfl6qlrlg+HAXwTEmaENHfrzT3JRts2UGUrFuekphvZJOppO2JPGQuf0eTOyKjL696lbfztAX04P\niqOCBcswggXHMA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAzAdBgNVHQ4EFgQU\nZTZJDtFJMVvzFO5u0Uj6in10OXkwHwYDVR0jBBgwFoAU39Ppz1YkEZb5qNjpKFWixi4YZD8wdQYD\nVR0RAQH/BGswaYZnaHR0cHM6Ly9naXRodWIuY29tL3RyYWlsb2ZiaXRzL3B5cGktYXR0ZXN0YXRp\nb24tbW9kZWxzLy5naXRodWIvd29ya2Zsb3dzL3JlbGVhc2UueW1sQHJlZnMvdGFncy92MC4wLjRh\nMjA5BgorBgEEAYO/MAEBBCtodHRwczovL3Rva2VuLmFjdGlvbnMuZ2l0aHVidXNlcmNvbnRlbnQu\nY29tMBUGCisGAQQBg78wAQIEB3JlbGVhc2UwNgYKKwYBBAGDvzABAwQoMTUzYzlhM2Y1YzE1MmVm\nNTQwNWNiYTIyNzY3NjUzNDY1OGFjZGUyNzAVBgorBgEEAYO/MAEEBAdyZWxlYXNlMDEGCisGAQQB\ng78wAQUEI3RyYWlsb2ZiaXRzL3B5cGktYXR0ZXN0YXRpb24tbW9kZWxzMCAGCisGAQQBg78wAQYE\nEnJlZnMvdGFncy92MC4wLjRhMjA7BgorBgEEAYO/MAEIBC0MK2h0dHBzOi8vdG9rZW4uYWN0aW9u\ncy5naXRodWJ1c2VyY29udGVudC5jb20wdwYKKwYBBAGDvzABCQRpDGdodHRwczovL2dpdGh1Yi5j\nb20vdHJhaWxvZmJpdHMvcHlwaS1hdHRlc3RhdGlvbi1tb2RlbHMvLmdpdGh1Yi93b3JrZmxvd3Mv\ncmVsZWFzZS55bWxAcmVmcy90YWdzL3YwLjAuNGEyMDgGCisGAQQBg78wAQoEKgwoMTUzYzlhM2Y1\nYzE1MmVmNTQwNWNiYTIyNzY3NjUzNDY1OGFjZGUyNzAdBgorBgEEAYO/MAELBA8MDWdpdGh1Yi1o\nb3N0ZWQwRgYKKwYBBAGDvzABDAQ4DDZodHRwczovL2dpdGh1Yi5jb20vdHJhaWxvZmJpdHMvcHlw\naS1hdHRlc3RhdGlvbi1tb2RlbHMwOAYKKwYBBAGDvzABDQQqDCgxNTNjOWEzZjVjMTUyZWY1NDA1\nY2JhMjI3Njc2NTM0NjU4YWNkZTI3MCIGCisGAQQBg78wAQ4EFAwScmVmcy90YWdzL3YwLjAuNGEy\nMBkGCisGAQQBg78wAQ8ECwwJNzcyMjQ3NDIzMC4GCisGAQQBg78wARAEIAweaHR0cHM6Ly9naXRo\ndWIuY29tL3RyYWlsb2ZiaXRzMBcGCisGAQQBg78wAREECQwHMjMxNDQyMzB3BgorBgEEAYO/MAES\nBGkMZ2h0dHBzOi8vZ2l0aHViLmNvbS90cmFpbG9mYml0cy9weXBpLWF0dGVzdGF0aW9uLW1vZGVs\ncy8uZ2l0aHViL3dvcmtmbG93cy9yZWxlYXNlLnltbEByZWZzL3RhZ3MvdjAuMC40YTIwOAYKKwYB\nBAGDvzABEwQqDCgxNTNjOWEzZjVjMTUyZWY1NDA1Y2JhMjI3Njc2NTM0NjU4YWNkZTI3MBcGCisG\nAQQBg78wARQECQwHcmVsZWFzZTBpBgorBgEEAYO/MAEVBFsMWWh0dHBzOi8vZ2l0aHViLmNvbS90\ncmFpbG9mYml0cy9weXBpLWF0dGVzdGF0aW9uLW1vZGVscy9hY3Rpb25zL3J1bnMvOTQ1NDU5MDgw\nMC9hdHRlbXB0cy8xMBYGCisGAQQBg78wARYECAwGcHVibGljMIGKBgorBgEEAdZ5AgQCBHwEegB4\nAHYA3T0wasbHETJjGR4cmWc3AqJKXrjePK3/h4pygC8p7o4AAAGQA7Ds7wAABAMARzBFAiAXAGV7\nDLOusv9KdLUmY6vTp2MMe4St9NUOhEp/eXZIwwIhAKKYj5DfX9lvJUHBsr/AtEIeJYqSeJ6M3CKP\nU18FRxXsMAoGCCqGSM49BAMDA2kAMGYCMQDyN5lhRCzuGlrgEJRpGpg5jdpaTIpiBus0vkAGffzP\nZr9SjKweGoRUtLnfxAJ6Jh4CMQCYEWAcYEVOPEACe+MMH0BPrrlRMnfooun97PmuQ25LwfVi5P48\nFotm8HZ0ViXHUZE=\n",
        "transparency_entries": [
            {
                "logIndex": "101487427",
                "logId": {
                    "keyId": "wNI9atQGlz+VWfO6LRygH4QUfY/8W4RFwiT5i5WRgB0="
                },
                "kindVersion": {
                    "kind": "dsse",
                    "version": "0.0.1"
                },
                "integratedTime": "1718048845",
                "inclusionPromise": {
                    "signedEntryTimestamp": "MEYCIQDMFnTMqL5k9rhgpIE0VG59hChr3vVjUhcpYwlAb9q0zAIhANP7lHSVABph3Rd4HFVv7aMwRF7zSeMfFMd9yxJt3UDA"
                },
                "inclusionProof": {
                    "logIndex": "97323996",
                    "rootHash": "La0A7Z2xT6hGMjh2tOlyI64RHw84pUHU3fVHj7TSVy0=",
                    "treeSize": "97323998",
                    "hashes": [
                        "3Rz+4naQLu4GK37I4HSkU2R3JWPm+oZAhzVapTCVt70=",
                        "PdxfsYo6NM+vpz093wWsIsusyGJ0DlLkUWuxkYhbnmw=",
                        "m+waEsb5wCRc096I+AGAxqWDBZBDJ3duxuWZNbV2ohU=",
                        "b9P3OggQy8jNuVpZLhIY2PXTiTc87/hAmDwP4mf07uI=",
                        "19K0NhNuHUqJP3I26axUgHyh1gqKNIgYCuXCcw+HYKk=",
                        "WhBO//b4F4om9U9MtMQuMJIV8ya5e4lr0UFHcMu/xd0=",
                        "s+idSozXH82LBPVH/Z9uhHJpWlieFgssfKTTlih3tE0=",
                        "Qu6lPX8kEmsqnAi+VrKGmMuZML4NLLrq8niw0Y3xdxE=",
                        "tcJBqniz0pBiR21iqSf205jubz0v9XqBqrVEfocm9NE=",
                        "uToMdLmWkBlY0yVYaf9GS/JBKW8dEZ9thyQyI8gHtQ0=",
                        "RKCkWYqzT6tUZmc3Jvzbxj9MA/gYAWvM/6Ku2bZRDdM=",
                        "rX8ztpnrupitNNHTqrykWKXtm2K1j+1xHpOYrqdXSu0=",
                        "t13rsrmj5sbMlY8QMEBToVdUZGeJf7ABzGqDcy0ktwg=",
                        "cX3Agx+hP66t1ZLbX/yHbfjU46/3m/VAmWyG/fhxAVc=",
                        "sjohk/3DQIfXTgf/5XpwtdF7yNbrf8YykOMHr1CyBYQ=",
                        "98enzMaC+x5oCMvIZQA5z8vu2apDMCFvE/935NfuPw8="
                    ],
                    "checkpoint": {
                        "envelope": "rekor.sigstore.dev - 2605736670972794746\n97323998\nLa0A7Z2xT6hGMjh2tOlyI64RHw84pUHU3fVHj7TSVy0=\n\n— rekor.sigstore.dev wNI9ajBEAiBIowx1POsWydf7F2tZj7huPfFBNngo87WIw2PyWTu5SgIgTxuNk/AFSdY2DjdM+2NodtymfDr0QydRAh8UO9ab8WU=\n"
                    }
                },
                "canonicalizedBody": "eyJhcGlWZXJzaW9uIjoiMC4wLjEiLCJraW5kIjoiZHNzZSIsInNwZWMiOnsiZW52ZWxvcGVIYXNoIjp7ImFsZ29yaXRobSI6InNoYTI1NiIsInZhbHVlIjoiNGE5NTU0MjA2YTk2OTA1ODgyOGU5MTNmOTcwZmE4MGI4NWE4ZDliN2RjZTJiZmI2NGM5Njc1YTY1ZTFjYTVlNyJ9LCJwYXlsb2FkSGFzaCI6eyJhbGdvcml0aG0iOiJzaGEyNTYiLCJ2YWx1ZSI6Ijc2MTgxNmVmNmFjMDNhOWZhN2JmMDQxZmQ4ZjNhZmI1ODRhZTQxYjRlYzNjMmZmYzVmOTkwY2MwMmU3OTcxMGIifSwic2lnbmF0dXJlcyI6W3sic2lnbmF0dXJlIjoiTUVZQ0lRRHFnbnY5MVpUM0J6clQ4UHk4bHpneStZL28xa1ZqNTFkeUIxWXI4Nlc2RFFJaEFOaWNyNm9hUjR4VkhSNWRtYUpLQ3p6NCttcUFwNUcyREpsaTFMTW9BSVpQIiwidmVyaWZpZXIiOiJMUzB0TFMxQ1JVZEpUaUJEUlZKVVNVWkpRMEZVUlMwdExTMHRDazFKU1VoS2VrTkRRbkY1WjBGM1NVSkJaMGxWUzBaaGNVWTRiRkZ6YnpoNU5FMHlUa2RHZFRKV05rWnRaVWxOZDBObldVbExiMXBKZW1vd1JVRjNUWGNLVG5wRlZrMUNUVWRCTVZWRlEyaE5UV015Ykc1ak0xSjJZMjFWZFZwSFZqSk5ValIzU0VGWlJGWlJVVVJGZUZaNllWZGtlbVJIT1hsYVV6RndZbTVTYkFwamJURnNXa2RzYUdSSFZYZElhR05PVFdwUmQwNXFSWGROVkdzd1RucEpNVmRvWTA1TmFsRjNUbXBGZDAxVWF6Rk9la2t4VjJwQlFVMUdhM2RGZDFsSUNrdHZXa2w2YWpCRFFWRlpTVXR2V2tsNmFqQkVRVkZqUkZGblFVVmFWM2d3VFRab2VrRm1iRFp4YkhKc1p5dElRVmgzVkVWdFlVVk9TR1p5ZWxRelNsSUtkSE15VlVkVmNrWjFaV3R3YUhaYVNrOXdjRTh5U2xCSFVYVm1NR1ZVVDNsTGFrdzJPVFpzWW1aNmRFRllNRFJRYVhGUFEwSmpjM2RuWjFoSVRVRTBSd3BCTVZWa1JIZEZRaTkzVVVWQmQwbElaMFJCVkVKblRsWklVMVZGUkVSQlMwSm5aM0pDWjBWR1FsRmpSRUY2UVdSQ1owNVdTRkUwUlVablVWVmFWRnBLQ2tSMFJrcE5Wblo2Ums4MWRUQlZhalpwYmpFd1QxaHJkMGgzV1VSV1VqQnFRa0puZDBadlFWVXpPVkJ3ZWpGWmEwVmFZalZ4VG1wd1MwWlhhWGhwTkZrS1drUTRkMlJSV1VSV1VqQlNRVkZJTDBKSGMzZGhXVnB1WVVoU01HTklUVFpNZVRsdVlWaFNiMlJYU1hWWk1qbDBURE5TZVZsWGJITmlNbHBwWVZoU2VncE1NMEkxWTBkcmRGbFlVakJhV0U0d1dWaFNjR0l5TkhSaVZ6bHJXbGQ0ZWt4NU5XNWhXRkp2WkZkSmRtUXlPWGxoTWxwellqTmtla3d6U214aVIxWm9DbU15VlhWbFZ6RnpVVWhLYkZwdVRYWmtSMFp1WTNrNU1rMUROSGRNYWxKb1RXcEJOVUpuYjNKQ1owVkZRVmxQTDAxQlJVSkNRM1J2WkVoU2QyTjZiM1lLVEROU2RtRXlWblZNYlVacVpFZHNkbUp1VFhWYU1td3dZVWhXYVdSWVRteGpiVTUyWW01U2JHSnVVWFZaTWpsMFRVSlZSME5wYzBkQlVWRkNaemM0ZHdwQlVVbEZRak5LYkdKSFZtaGpNbFYzVG1kWlMwdDNXVUpDUVVkRWRucEJRa0YzVVc5TlZGVjZXWHBzYUUweVdURlpla1V4VFcxV2JVNVVVWGRPVjA1cENsbFVTWGxPZWxrelRtcFZlazVFV1RGUFIwWnFXa2RWZVU1NlFWWkNaMjl5UW1kRlJVRlpUeTlOUVVWRlFrRmtlVnBYZUd4WldFNXNUVVJGUjBOcGMwY0tRVkZSUW1jM09IZEJVVlZGU1ROU2VWbFhiSE5pTWxwcFlWaFNla3d6UWpWalIydDBXVmhTTUZwWVRqQlpXRkp3WWpJMGRHSlhPV3RhVjNoNlRVTkJSd3BEYVhOSFFWRlJRbWMzT0hkQlVWbEZSVzVLYkZwdVRYWmtSMFp1WTNrNU1rMUROSGRNYWxKb1RXcEJOMEpuYjNKQ1owVkZRVmxQTDAxQlJVbENRekJOQ2tzeWFEQmtTRUo2VDJrNGRtUkhPWEphVnpSMVdWZE9NR0ZYT1hWamVUVnVZVmhTYjJSWFNqRmpNbFo1V1RJNWRXUkhWblZrUXpWcVlqSXdkMlIzV1VzS1MzZFpRa0pCUjBSMmVrRkNRMUZTY0VSSFpHOWtTRkozWTNwdmRrd3laSEJrUjJneFdXazFhbUl5TUhaa1NFcG9ZVmQ0ZGxwdFNuQmtTRTEyWTBoc2R3cGhVekZvWkVoU2JHTXpVbWhrUjJ4Mllta3hkR0l5VW14aVNFMTJURzFrY0dSSGFERlphVGt6WWpOS2NscHRlSFprTTAxMlkyMVdjMXBYUm5wYVV6VTFDbUpYZUVGamJWWnRZM2s1TUZsWFpIcE1NMWwzVEdwQmRVNUhSWGxOUkdkSFEybHpSMEZSVVVKbk56aDNRVkZ2UlV0bmQyOU5WRlY2V1hwc2FFMHlXVEVLV1hwRk1VMXRWbTFPVkZGM1RsZE9hVmxVU1hsT2Vsa3pUbXBWZWs1RVdURlBSMFpxV2tkVmVVNTZRV1JDWjI5eVFtZEZSVUZaVHk5TlFVVk1Ra0U0VFFwRVYyUndaRWRvTVZscE1XOWlNMDR3V2xkUmQxSm5XVXRMZDFsQ1FrRkhSSFo2UVVKRVFWRTBSRVJhYjJSSVVuZGplbTkyVERKa2NHUkhhREZaYVRWcUNtSXlNSFprU0Vwb1lWZDRkbHB0U25Ca1NFMTJZMGhzZDJGVE1XaGtTRkpzWXpOU2FHUkhiSFppYVRGMFlqSlNiR0pJVFhkUFFWbExTM2RaUWtKQlIwUUtkbnBCUWtSUlVYRkVRMmQ0VGxST2FrOVhSWHBhYWxacVRWUlZlVnBYV1RGT1JFRXhXVEpLYUUxcVNUTk9hbU15VGxSTk1FNXFWVFJaVjA1cldsUkpNd3BOUTBsSFEybHpSMEZSVVVKbk56aDNRVkUwUlVaQmQxTmpiVlp0WTNrNU1GbFhaSHBNTTFsM1RHcEJkVTVIUlhsTlFtdEhRMmx6UjBGUlVVSm5OemgzQ2tGUk9FVkRkM2RLVG5wamVVMXFVVE5PUkVsNlRVTTBSME5wYzBkQlVWRkNaemM0ZDBGU1FVVkpRWGRsWVVoU01HTklUVFpNZVRsdVlWaFNiMlJYU1hVS1dUSTVkRXd6VW5sWlYyeHpZakphYVdGWVVucE5RbU5IUTJselIwRlJVVUpuTnpoM1FWSkZSVU5SZDBoTmFrMTRUa1JSZVUxNlFqTkNaMjl5UW1kRlJRcEJXVTh2VFVGRlUwSkhhMDFhTW1nd1pFaENlazlwT0haYU1td3dZVWhXYVV4dFRuWmlVemt3WTIxR2NHSkhPVzFaYld3d1kzazVkMlZZUW5CTVYwWXdDbVJIVm5wa1IwWXdZVmM1ZFV4WE1YWmFSMVp6WTNrNGRWb3liREJoU0ZacFRETmtkbU50ZEcxaVJ6a3pZM2s1ZVZwWGVHeFpXRTVzVEc1c2RHSkZRbmtLV2xkYWVrd3pVbWhhTTAxMlpHcEJkVTFETkRCWlZFbDNUMEZaUzB0M1dVSkNRVWRFZG5wQlFrVjNVWEZFUTJkNFRsUk9hazlYUlhwYWFsWnFUVlJWZVFwYVYxa3hUa1JCTVZreVNtaE5ha2t6VG1wak1rNVVUVEJPYWxVMFdWZE9hMXBVU1ROTlFtTkhRMmx6UjBGUlVVSm5OemgzUVZKUlJVTlJkMGhqYlZaekNscFhSbnBhVkVKd1FtZHZja0puUlVWQldVOHZUVUZGVmtKR2MwMVhWMmd3WkVoQ2VrOXBPSFphTW13d1lVaFdhVXh0VG5aaVV6a3dZMjFHY0dKSE9XMEtXVzFzTUdONU9YZGxXRUp3VEZkR01HUkhWbnBrUjBZd1lWYzVkVXhYTVhaYVIxWnpZM2s1YUZrelVuQmlNalY2VEROS01XSnVUWFpQVkZFeFRrUlZOUXBOUkdkM1RVTTVhR1JJVW14aVdFSXdZM2s0ZUUxQ1dVZERhWE5IUVZGUlFtYzNPSGRCVWxsRlEwRjNSMk5JVm1saVIyeHFUVWxIUzBKbmIzSkNaMFZGQ2tGa1dqVkJaMUZEUWtoM1JXVm5RalJCU0ZsQk0xUXdkMkZ6WWtoRlZFcHFSMUkwWTIxWFl6TkJjVXBMV0hKcVpWQkxNeTlvTkhCNVowTTRjRGR2TkVFS1FVRkhVVUUzUkhNM2QwRkJRa0ZOUVZKNlFrWkJhVUZZUVVkV04wUk1UM1Z6ZGpsTFpFeFZiVmsyZGxSd01rMU5aVFJUZERsT1ZVOW9SWEF2WlZoYVNRcDNkMGxvUVV0TFdXbzFSR1pZT1d4MlNsVklRbk55TDBGMFJVbGxTbGx4VTJWS05rMHpRMHRRVlRFNFJsSjRXSE5OUVc5SFEwTnhSMU5OTkRsQ1FVMUVDa0V5YTBGTlIxbERUVkZFZVU0MWJHaFNRM3AxUjJ4eVowVktVbkJIY0djMWFtUndZVlJKY0dsQ2RYTXdkbXRCUjJabWVsQmFjamxUYWt0M1pVZHZVbFVLZEV4dVpuaEJTalpLYURSRFRWRkRXVVZYUVdOWlJWWlBVRVZCUTJVclRVMUlNRUpRY25Kc1VrMXVabTl2ZFc0NU4xQnRkVkV5TlV4M1psWnBOVkEwT0FwR2IzUnRPRWhhTUZacFdFaFZXa1U5Q2kwdExTMHRSVTVFSUVORlVsUkpSa2xEUVZSRkxTMHRMUzBLIn1dfX0="
            }
        ]
    },
    "envelope": {
        "statement": "eyJfdHlwZSI6Imh0dHBzOi8vaW4tdG90by5pby9TdGF0ZW1lbnQvdjEiLCJzdWJqZWN0IjpbeyJu\nYW1lIjoicHlwaV9hdHRlc3RhdGlvbl9tb2RlbHMtMC4wLjRhMi50YXIuZ3oiLCJkaWdlc3QiOnsi\nc2hhMjU2IjoiYzk3MDljZTZmZDViNjdiNTliNGEyODc1OGNmMTRkM2Y0MTE4MDNjNGI4OWI2MDY4\nYjFmMWE4ZTRlZTk0YzhlZiJ9fV0sInByZWRpY2F0ZVR5cGUiOiJodHRwczovL2RvY3MucHlwaS5v\ncmcvYXR0ZXN0YXRpb25zL3B1Ymxpc2gvdjEiLCJwcmVkaWNhdGUiOnt9fQ==\n",
        "signature": "MEYCIQDqgnv91ZT3BzrT8Py8lzgy+Y/o1kVj51dyB1Yr86W6DQIhANicr6oaR4xVHR5dmaJKCzz4\n+mqAp5G2DJli1LMoAIZP\n"
    }
}
```

### Verification material

The `verification_material` conveys the materials used the verify the attestation.

The `certificate` is the most relevant field: it's a base64-encoded DER X.509 certificate,
which we can inspect as follows:

```bash
# put the JSON above in /tmp/attestation.json
jq -r .verification_material.certificate < /tmp/attestation.json \
  | base64 -d \
  | openssl x509 -inform DER -text -noout
```

producing (abbreviated for clarity):

```
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number:
            28:56:aa:17:c9:50:b2:8f:32:e0:cd:8d:18:5b:b6:57:a1:66:78:83
        Signature Algorithm: ecdsa-with-SHA384
        Issuer: O=sigstore.dev, CN=sigstore-intermediate
        Validity
            Not Before: Jun 10 19:47:25 2024 GMT
            Not After : Jun 10 19:57:25 2024 GMT
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
                65:36:49:0E:D1:49:31:5B:F3:14:EE:6E:D1:48:FA:8A:7D:74:39:79
            X509v3 Authority Key Identifier:
                DF:D3:E9:CF:56:24:11:96:F9:A8:D8:E9:28:55:A2:C6:2E:18:64:3F
            X509v3 Subject Alternative Name: critical
                URI:https://github.com/trailofbits/pypi-attestation-models/.github/workflows/release.yml@refs/tags/v0.0.4a2
            1.3.6.1.4.1.57264.1.1:
                https://token.actions.githubusercontent.com
    Signature Algorithm: ecdsa-with-SHA384
    Signature Value:
        30:66:02:31:00:f2:37:99:61:44:2c:ee:1a:5a:e0:10:94:69:
        1a:98:39:8d:da:5a:4c:8a:62:06:eb:34:be:40:06:7d:fc:cf:
        66:bf:52:8c:ac:1e:1a:84:54:b4:b9:df:c4:02:7a:26:1e:02:
        31:00:98:11:60:1c:60:45:4e:3c:40:02:7b:e3:0c:1f:40:4f:
        ae:b9:51:32:77:e8:a2:e9:fd:ec:f9:ae:43:6e:4b:c1:f5:62:
        e4:fe:3c:16:8b:66:f0:76:74:56:25:c7:51:91
```

In this case, we can see that the certificate binds a public key
to an identity (`https://github.com/trailofbits/pypi-attestation-models/.github/workflows/release.yml@refs/tags/v0.0.4a2`),
which can then be matched against the project's registered Trusted Publishers
during the verification process.

### Envelope

The `envelope` key contains two components:

* The `statement`, which contains the core, signed-over in-toto Statement:

  ```bash
  jq -r .envelope.statement < /tmp/attestation.json | base64 -d
  ```

  yielding:

  ```json
  {
    "_type": "https://in-toto.io/Statement/v1",
    "subject": [
      {
        "name": "pypi_attestation_models-0.0.4a2.tar.gz",
        "digest": {
          "sha256": "c9709ce6fd5b67b59b4a28758cf14d3f411803c4b89b6068b1f1a8e4ee94c8ef"
        }
      }
    ],
    "predicateType": "https://docs.pypi.org/attestations/publish/v1",
    "predicate": {}
  }
  ```

* The `signature`, which contains the base64-encoded signature over `statement`.

  `signature` can be verified using the public key bound within
  `verification_material.certificate`, fully linking the attestation back to
  the identity that produced it.

  The signing process itself is not "bare": instead of directly signing over
  `statement`, the payload is computed using the [DSSE PAE encoding]:

  ```
  SIGNATURE = Sign(PAE(UTF8(PAYLOAD_TYPE), SERIALIZED_BODY))
  ```

  where:

  * `PAYLOAD_TYPE` is fixed as `application/vnd.in-toto+json`
  * `SERIALIZED_BODY` is the JSON-encoded `statement`, per above
  * `PAE` is the "pre-authentication encoding", defined as:

    ```
    PAE(type, body) = "DSSEv1" + SP + LEN(type) + SP + type + SP + LEN(body) + SP + body
    +               = concatenation
    SP              = ASCII space [0x20]
    "DSSEv1"        = ASCII [0x44, 0x53, 0x53, 0x45, 0x76, 0x31]
    LEN(s)          = ASCII decimal encoding of the byte length of s, with no leading zeros
    ```

  Thus, the actual signed-over payload roughly resembles:

  ```
  DSSEv1 28 application/vnd.in-toto+json 272 {"_type":"https://in-toto.io/Statement/v1","subject":[{"name":"pypi_attestation_models-0.0.4a2.tar.gz","digest":{"sha256":"c9709ce6fd5b67b59b4a28758cf14d3f411803c4b89b6068b1f1a8e4ee94c8ef"}}],"predicateType":"https://docs.pypi.org/attestations/publish/v1","predicate":{}}
  ```

#### "Why is the `predicate` empty?"

You may have noticed that the in-toto Statement above contains a
predicate of type `https://docs.pypi.org/attestations/publish/v1`, but with an
empty `predicate` body (`{}`).

This is intentional! A publish attestation **does not require** a custom
predicate, since all of the state associated with a Trusted Publisher
is fully encapsulated in the `verification_material.certificate` being
used to verify the `envelope.statement`'s signature.

### Verifying an attestation object

Attestation object verification is described at a high level in [PEP 740].

Using the details above, we can provide the steps with slightly more accuracy:

1. Retrieve the distribution (sdist or wheel) being verified and its attestation.
   We'll call these `foo-1.2.3.tar.gz` and `foo-1.2.3.tar.gz.publish.attestation`,
   respectively.

2. Verify that the attestation's `verification_material.certificate` is valid
   and chains up to the expected root of trust (i.e., the Sigstore public
   good instance) *and* has the expected subject (i.e., the subject matches
   a valid Trusted Publisher for project `foo`).

    This step is equivalent to Sigstore "bundle" verification and also requires
    a source of signed time, such as the `verification_material.transparency_entries`.

3. Verify that the attestation's `envelope.signature` is valid for `envelope.statement`,
   using the [DSSE PAE encoding] and the public key of
   `verification_material.certificate`.

4. Decode the `envelope.statement`, verify that it's an in-toto Statement
   with the expected `subject` (`foo-1.2.3.tar.gz`) and subject digest
   (the SHA-256 of `foo-1.2.3.tar.gz`'s contents).

5. Confirm that the statement's `payloadType` is one of the attestation types
   supported by PyPI, and perform any `payload`-specific processing.
   For the PyPI Publish attestation, no `payload` is present, and therefore
   no additional processing is necessary.

If any of the steps above fail, the attestation should be considered invalid
and any operations on its associated distribution should halt.

Users are **strongly discouraged** from implementing the steps above in an
ad-hoc manner, since they involve error-prone X.509 and transparency log
operations. Instead, we **strongly encourage** integrators to use
either [pypi-attestation-models] or [sigstore-python]'s pre-existing APIs
for attestation manipulation, signing, and verification.

[DSSE PAE encoding]: https://github.com/secure-systems-lab/dsse/blob/v1.0.0/protocol.md

[PEP 740]: https://peps.python.org/pep-0740/

[pypi-attestation-models]: https://github.com/trailofbits/pypi-attestation-models

[sigstore-python]: https://github.com/sigstore/sigstore-python
