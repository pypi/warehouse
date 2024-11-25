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

### Get provenance for file

Route: `GET /integrity/<project>/<version>/<filename>/provenance`

Get the provenance object for the given `<filename>`.

This endpoint is currently only available as JSON.

Example JSON request (default if no `Accept` header is passed):

```http
GET /integrity/sampleproject/4.0.0/sampleproject-4.0.0.tar.gz/provenance HTTP/1.1
Host: pypi.org
Accept: application/vnd.pypi.integrity.v1+json
```

??? note "Example JSON response"

    This is an example response, demonstrating a provenance object containing
    one attestation and its Trusted Publishing identity.

    ```json
    {
      "attestation_bundles": [
        {
          "attestations": [
            {
              "envelope": {
                "signature": "MEUCIQD1JCA8lWR9na44+zY2tr13sEuMCIu+FLS6eDkwESP5KgIgQDNG+eA5PiLSvVd+0AJn3Nk1V3CpRjRoz59L/MMTxyM=",
                "statement": "eyJfdHlwZSI6Imh0dHBzOi8vaW4tdG90by5pby9TdGF0ZW1lbnQvdjEiLCJzdWJqZWN0IjpbeyJuYW1lIjoic2FtcGxlcHJvamVjdC00LjAuMC50YXIuZ3oiLCJkaWdlc3QiOnsic2hhMjU2IjoiMGFjZTc5ODBmODJjNTgxNWVkZTRjZDdiZjlmNjY5MzY4NGNlYzJhZTQ3YjliN2FkZTlhZGQ1MzNiODYyN2M2YiJ9fV0sInByZWRpY2F0ZVR5cGUiOiJodHRwczovL2RvY3MucHlwaS5vcmcvYXR0ZXN0YXRpb25zL3B1Ymxpc2gvdjEiLCJwcmVkaWNhdGUiOm51bGx9"
              },
              "verification_material": {
                "certificate": "MIIGoTCCBiigAwIBAgITFai+PDKak1xA1HLq0mskqhDV5zAKBggqhkjOPQQDAzA3MRUwEwYDVQQKEwxzaWdzdG9yZS5kZXYxHjAcBgNVBAMTFXNpZ3N0b3JlLWludGVybWVkaWF0ZTAeFw0yNDExMDYyMjM3MDdaFw0yNDExMDYyMjQ3MDdaMAAwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAARbx1Fse2Ln00On5aFaL+lHNGFYLaqeKDduplZDPJS+w2PjYfNPL0g/n4sDWEQFZfyIExEWKulZ2GKNzAc0+SmUo4IFSDCCBUQwDgYDVR0PAQH/BAQDAgeAMBMGA1UdJQQMMAoGCCsGAQUFBwMDMB0GA1UdDgQWBBT/uSEIXmQzuRkppWXrTKVkfZFJbzAfBgNVHSMEGDAWgBTf0+nPViQRlvmo2OkoVaLGLhhkPzBhBgNVHREBAf8EVzBVhlNodHRwczovL2dpdGh1Yi5jb20vcHlwYS9zYW1wbGVwcm9qZWN0Ly5naXRodWIvd29ya2Zsb3dzL3JlbGVhc2UueW1sQHJlZnMvaGVhZHMvbWFpbjA5BgorBgEEAYO/MAEBBCtodHRwczovL3Rva2VuLmFjdGlvbnMuZ2l0aHVidXNlcmNvbnRlbnQuY29tMBIGCisGAQQBg78wAQIEBHB1c2gwNgYKKwYBBAGDvzABAwQoNjIxZTQ5NzRjYTI1Y2U1MzE3NzNkZWY1ODZiYTNlZDhlNzM2YjNmYzAVBgorBgEEAYO/MAEEBAdSZWxlYXNlMCAGCisGAQQBg78wAQUEEnB5cGEvc2FtcGxlcHJvamVjdDAdBgorBgEEAYO/MAEGBA9yZWZzL2hlYWRzL21haW4wOwYKKwYBBAGDvzABCAQtDCtodHRwczovL3Rva2VuLmFjdGlvbnMuZ2l0aHVidXNlcmNvbnRlbnQuY29tMGMGCisGAQQBg78wAQkEVQxTaHR0cHM6Ly9naXRodWIuY29tL3B5cGEvc2FtcGxlcHJvamVjdC8uZ2l0aHViL3dvcmtmbG93cy9yZWxlYXNlLnltbEByZWZzL2hlYWRzL21haW4wOAYKKwYBBAGDvzABCgQqDCg2MjFlNDk3NGNhMjVjZTUzMTc3M2RlZjU4NmJhM2VkOGU3MzZiM2ZjMB0GCisGAQQBg78wAQsEDwwNZ2l0aHViLWhvc3RlZDA1BgorBgEEAYO/MAEMBCcMJWh0dHBzOi8vZ2l0aHViLmNvbS9weXBhL3NhbXBsZXByb2plY3QwOAYKKwYBBAGDvzABDQQqDCg2MjFlNDk3NGNhMjVjZTUzMTc3M2RlZjU4NmJhM2VkOGU3MzZiM2ZjMB8GCisGAQQBg78wAQ4EEQwPcmVmcy9oZWFkcy9tYWluMBgGCisGAQQBg78wAQ8ECgwIMTQ4OTk1OTYwJwYKKwYBBAGDvzABEAQZDBdodHRwczovL2dpdGh1Yi5jb20vcHlwYTAWBgorBgEEAYO/MAERBAgMBjY0NzAyNTBjBgorBgEEAYO/MAESBFUMU2h0dHBzOi8vZ2l0aHViLmNvbS9weXBhL3NhbXBsZXByb2plY3QvLmdpdGh1Yi93b3JrZmxvd3MvcmVsZWFzZS55bWxAcmVmcy9oZWFkcy9tYWluMDgGCisGAQQBg78wARMEKgwoNjIxZTQ5NzRjYTI1Y2U1MzE3NzNkZWY1ODZiYTNlZDhlNzM2YjNmYzAUBgorBgEEAYO/MAEUBAYMBHB1c2gwWQYKKwYBBAGDvzABFQRLDElodHRwczovL2dpdGh1Yi5jb20vcHlwYS9zYW1wbGVwcm9qZWN0L2FjdGlvbnMvcnVucy8xMTcxMzAzODk4MS9hdHRlbXB0cy8xMBYGCisGAQQBg78wARYECAwGcHVibGljMIGKBgorBgEEAdZ5AgQCBHwEegB4AHYA3T0wasbHETJjGR4cmWc3AqJKXrjePK3/h4pygC8p7o4AAAGTA5/X5AAABAMARzBFAiA6nYK0GxqVzJutrjrYA1bAIKHUjGrsHMLrOJTTEUiERAIhAJZotATnSwlKt7C3Zwhx3fcSrhGfOakTlM2w+8qmltcjMAoGCCqGSM49BAMDA2cAMGQCMB+ilsPgy4ynUG9GtqDEBqW8+ZqjX6LpuxQqjCr7s4ytyt2ppFdgjrGrG1DY4nSZtQIwblrgq9t9izAMTkJeqhQBs2OUiyIJZipceD5vAAE/Nfgd/9uK0MZAHFsLgalqOBl8",
                "transparency_entries": [
                  {
                    "canonicalizedBody": "eyJhcGlWZXJzaW9uIjoiMC4wLjEiLCJraW5kIjoiZHNzZSIsInNwZWMiOnsiZW52ZWxvcGVIYXNoIjp7ImFsZ29yaXRobSI6InNoYTI1NiIsInZhbHVlIjoiOTNlMWYzNjRjODYwZWQ3MzI1MWYzYjI2YTU0YTM5NzFiZmZmZWYwNGU5MGNhNDgyNGU2YjhlMDJhMWIxMTVjMiJ9LCJwYXlsb2FkSGFzaCI6eyJhbGdvcml0aG0iOiJzaGEyNTYiLCJ2YWx1ZSI6Ijk1YTdkMGM3ZmVhZWQ1NDA5NDJlZGZlNzBhZjlkM2JiNjNiNjNlODgwZDJkN2ExYzYzZmQ4NDI0YTU2YjQ1YmMifSwic2lnbmF0dXJlcyI6W3sic2lnbmF0dXJlIjoiTUVVQ0lRRDFKQ0E4bFdSOW5hNDQrelkydHIxM3NFdU1DSXUrRkxTNmVEa3dFU1A1S2dJZ1FETkcrZUE1UGlMU3ZWZCswQUpuM05rMVYzQ3BSalJvejU5TC9NTVR4eU09IiwidmVyaWZpZXIiOiJMUzB0TFMxQ1JVZEpUaUJEUlZKVVNVWkpRMEZVUlMwdExTMHRDazFKU1VkdlZFTkRRbWxwWjBGM1NVSkJaMGxVUm1GcEsxQkVTMkZyTVhoQk1VaE1jVEJ0YzJ0eGFFUldOWHBCUzBKblozRm9hMnBQVUZGUlJFRjZRVE1LVFZKVmQwVjNXVVJXVVZGTFJYZDRlbUZYWkhwa1J6bDVXbE0xYTFwWVdYaElha0ZqUW1kT1ZrSkJUVlJHV0U1d1dqTk9NR0l6U214TVYyeDFaRWRXZVFwaVYxWnJZVmRHTUZwVVFXVkdkekI1VGtSRmVFMUVXWGxOYWswelRVUmtZVVozTUhsT1JFVjRUVVJaZVUxcVVUTk5SR1JoVFVGQmQxZFVRVlJDWjJOeENtaHJhazlRVVVsQ1FtZG5jV2hyYWs5UVVVMUNRbmRPUTBGQlVtSjRNVVp6WlRKTWJqQXdUMjQxWVVaaFRDdHNTRTVIUmxsTVlYRmxTMFJrZFhCc1drUUtVRXBUSzNjeVVHcFpaazVRVERCbkwyNDBjMFJYUlZGR1dtWjVTVVY0UlZkTGRXeGFNa2RMVG5wQll6QXJVMjFWYnpSSlJsTkVRME5DVlZGM1JHZFpSQXBXVWpCUVFWRklMMEpCVVVSQloyVkJUVUpOUjBFeFZXUktVVkZOVFVGdlIwTkRjMGRCVVZWR1FuZE5SRTFDTUVkQk1WVmtSR2RSVjBKQ1ZDOTFVMFZKQ2xodFVYcDFVbXR3Y0ZkWWNsUkxWbXRtV2taS1lucEJaa0puVGxaSVUwMUZSMFJCVjJkQ1ZHWXdLMjVRVm1sUlVteDJiVzh5VDJ0dlZtRk1SMHhvYUdzS1VIcENhRUpuVGxaSVVrVkNRV1k0UlZaNlFsWm9iRTV2WkVoU2QyTjZiM1pNTW1Sd1pFZG9NVmxwTldwaU1qQjJZMGhzZDFsVE9YcFpWekYzWWtkV2R3cGpiVGx4V2xkT01FeDVOVzVoV0ZKdlpGZEpkbVF5T1hsaE1scHpZak5rZWt3elNteGlSMVpvWXpKVmRXVlhNWE5SU0Vwc1dtNU5kbUZIVm1oYVNFMTJDbUpYUm5CaWFrRTFRbWR2Y2tKblJVVkJXVTh2VFVGRlFrSkRkRzlrU0ZKM1kzcHZka3d6VW5aaE1sWjFURzFHYW1SSGJIWmliazExV2pKc01HRklWbWtLWkZoT2JHTnRUblppYmxKc1ltNVJkVmt5T1hSTlFrbEhRMmx6UjBGUlVVSm5OemgzUVZGSlJVSklRakZqTW1kM1RtZFpTMHQzV1VKQ1FVZEVkbnBCUWdwQmQxRnZUbXBKZUZwVVVUVk9lbEpxV1ZSSk1Wa3lWVEZOZWtVelRucE9hMXBYV1RGUFJGcHBXVlJPYkZwRWFHeE9lazB5V1dwT2JWbDZRVlpDWjI5eUNrSm5SVVZCV1U4dlRVRkZSVUpCWkZOYVYzaHNXVmhPYkUxRFFVZERhWE5IUVZGUlFtYzNPSGRCVVZWRlJXNUNOV05IUlhaak1rWjBZMGQ0YkdOSVNuWUtZVzFXYW1SRVFXUkNaMjl5UW1kRlJVRlpUeTlOUVVWSFFrRTVlVnBYV25wTU1taHNXVmRTZWt3eU1XaGhWelIzVDNkWlMwdDNXVUpDUVVkRWRucEJRZ3BEUVZGMFJFTjBiMlJJVW5kamVtOTJURE5TZG1FeVZuVk1iVVpxWkVkc2RtSnVUWFZhTW13d1lVaFdhV1JZVG14amJVNTJZbTVTYkdKdVVYVlpNamwwQ2sxSFRVZERhWE5IUVZGUlFtYzNPSGRCVVd0RlZsRjRWR0ZJVWpCalNFMDJUSGs1Ym1GWVVtOWtWMGwxV1RJNWRFd3pRalZqUjBWMll6SkdkR05IZUd3S1kwaEtkbUZ0Vm1wa1F6aDFXakpzTUdGSVZtbE1NMlIyWTIxMGJXSkhPVE5qZVRsNVdsZDRiRmxZVG14TWJteDBZa1ZDZVZwWFducE1NbWhzV1ZkU2VncE1NakZvWVZjMGQwOUJXVXRMZDFsQ1FrRkhSSFo2UVVKRFoxRnhSRU5uTWsxcVJteE9SR3N6VGtkT2FFMXFWbXBhVkZWNlRWUmpNMDB5VW14YWFsVTBDazV0U21oTk1sWnJUMGRWTTAxNldtbE5NbHBxVFVJd1IwTnBjMGRCVVZGQ1p6YzRkMEZSYzBWRWQzZE9XakpzTUdGSVZtbE1WMmgyWXpOU2JGcEVRVEVLUW1kdmNrSm5SVVZCV1U4dlRVRkZUVUpEWTAxS1YyZ3daRWhDZWs5cE9IWmFNbXd3WVVoV2FVeHRUblppVXpsM1pWaENhRXd6VG1oaVdFSnpXbGhDZVFwaU1uQnNXVE5SZDA5QldVdExkMWxDUWtGSFJIWjZRVUpFVVZGeFJFTm5NazFxUm14T1JHc3pUa2RPYUUxcVZtcGFWRlY2VFZSak0wMHlVbXhhYWxVMENrNXRTbWhOTWxaclQwZFZNMDE2V21sTk1scHFUVUk0UjBOcGMwZEJVVkZDWnpjNGQwRlJORVZGVVhkUVkyMVdiV041T1c5YVYwWnJZM2s1ZEZsWGJIVUtUVUpuUjBOcGMwZEJVVkZDWnpjNGQwRlJPRVZEWjNkSlRWUlJORTlVYXpGUFZGbDNTbmRaUzB0M1dVSkNRVWRFZG5wQlFrVkJVVnBFUW1SdlpFaFNkd3BqZW05MlRESmtjR1JIYURGWmFUVnFZakl3ZG1OSWJIZFpWRUZYUW1kdmNrSm5SVVZCV1U4dlRVRkZVa0pCWjAxQ2Fsa3dUbnBCZVU1VVFtcENaMjl5Q2tKblJVVkJXVTh2VFVGRlUwSkdWVTFWTW1nd1pFaENlazlwT0haYU1td3dZVWhXYVV4dFRuWmlVemwzWlZoQ2FFd3pUbWhpV0VKeldsaENlV0l5Y0d3S1dUTlJka3h0WkhCa1IyZ3hXV2s1TTJJelNuSmFiWGgyWkROTmRtTnRWbk5hVjBaNldsTTFOV0pYZUVGamJWWnRZM2s1YjFwWFJtdGplVGwwV1Zkc2RRcE5SR2RIUTJselIwRlJVVUpuTnpoM1FWSk5SVXRuZDI5T2FrbDRXbFJSTlU1NlVtcFpWRWt4V1RKVk1VMTZSVE5PZWs1cldsZFpNVTlFV21sWlZFNXNDbHBFYUd4T2VrMHlXV3BPYlZsNlFWVkNaMjl5UW1kRlJVRlpUeTlOUVVWVlFrRlpUVUpJUWpGak1tZDNWMUZaUzB0M1dVSkNRVWRFZG5wQlFrWlJVa3dLUkVWc2IyUklVbmRqZW05MlRESmtjR1JIYURGWmFUVnFZakl3ZG1OSWJIZFpVemw2V1ZjeGQySkhWbmRqYlRseFdsZE9NRXd5Um1wa1IyeDJZbTVOZGdwamJsWjFZM2s0ZUUxVVkzaE5la0Y2VDBSck5FMVRPV2hrU0ZKc1lsaENNR041T0hoTlFsbEhRMmx6UjBGUlVVSm5OemgzUVZKWlJVTkJkMGRqU0ZacENtSkhiR3BOU1VkTFFtZHZja0puUlVWQlpGbzFRV2RSUTBKSWQwVmxaMEkwUVVoWlFUTlVNSGRoYzJKSVJWUktha2RTTkdOdFYyTXpRWEZLUzFoeWFtVUtVRXN6TDJnMGNIbG5Remh3TjI4MFFVRkJSMVJCTlM5WU5VRkJRVUpCVFVGU2VrSkdRV2xCTm01WlN6QkhlSEZXZWtwMWRISnFjbGxCTVdKQlNVdElWUXBxUjNKelNFMU1jazlLVkZSRlZXbEZVa0ZKYUVGS1dtOTBRVlJ1VTNkc1MzUTNRek5hZDJoNE0yWmpVM0pvUjJaUFlXdFViRTB5ZHlzNGNXMXNkR05xQ2sxQmIwZERRM0ZIVTAwME9VSkJUVVJCTW1OQlRVZFJRMDFDSzJsc2MxQm5lVFI1YmxWSE9VZDBjVVJGUW5GWE9DdGFjV3BZTmt4d2RYaFJjV3BEY2pjS2N6UjVkSGwwTW5Cd1JtUm5hbkpIY2tjeFJGazBibE5hZEZGSmQySnNjbWR4T1hRNWFYcEJUVlJyU21WeGFGRkNjekpQVldsNVNVcGFhWEJqWlVRMWRncEJRVVV2VG1ablpDODVkVXN3VFZwQlNFWnpUR2RoYkhGUFFtdzRDaTB0TFMwdFJVNUVJRU5GVWxSSlJrbERRVlJGTFMwdExTMEsifV19fQ==",
                    "inclusionPromise": {
                      "signedEntryTimestamp": "MEQCIGzFZon9/joNsiQOL1uoIP/gtz7/A6eAB+50oX3M0CBaAiAZmLVxcgknlWls6R1FswJWCHY0vkwQ/jE5dSkcY43jWA=="
                    },
                    "inclusionProof": {
                      "checkpoint": {
                        "envelope": "rekor.sigstore.dev - 1193050959916656506\n25232879\nQrnMowJnGj9hZkL1UOvkg7w+KuG27PEDcsdaEqCtoDM=\n\n— rekor.sigstore.dev wNI9ajBFAiEAshgj30XTIU+L6UyYL0yzLXJbLFmxPEc8ZRmS1R3N1sQCIFCjFEqe9J+Et9sWzJp6SE3p7Eh/+97zON7mwX6unCem\n"
                      },
                      "hashes": [
                        "Bc4heeKQhKCr6/ZtuEHmAyp8AzvP4N1ROusEacAmfFQ=",
                        "ZTeyp2wk6H1Bgz3SZOqQWoQvCmkiltfFstDiy1WaR9Y=",
                        "vnHPC5XIhbYQib86Hi6M4OaEOFGFMlOip8+5mxZd8cs=",
                        "BEONTVFois+c47/YA7vzwZG7fbNLBkVLz1hUM/WMb1k=",
                        "PWqRmPYAwa1fq6R1qSrYlOxCtiKnFZq9hnNt7XwCIA8=",
                        "KHxYP0XNSf1yKjp+xY/5Kkckw0Yweyjx9Z6qn2+pnZM=",
                        "8/b9kmTAbALhl4EaKIH4uMXhES9ILB0XQkuH44FltJY=",
                        "mXfX9NDkaWje6HpniWis2CBELUGjv8LiW2jeMOclCs0=",
                        "jRPOva2IEma7ZE7mPN3xHtEnXtMF/HNvrmbC5TKTy14=",
                        "s8vUdxeRlxXWTCMdSLhiSzRiYM3eGsVvrm+5HWkTNBc=",
                        "4lUF0YOu9XkIDXKXA0wMSzd6VeDY3TZAgmoOeWmS2+Y=",
                        "gf+9m552B3PnkWnO0o4KdVvjcT3WVHLrCbf1DoVYKFw="
                      ],
                      "logIndex": "25232877",
                      "rootHash": "QrnMowJnGj9hZkL1UOvkg7w+KuG27PEDcsdaEqCtoDM=",
                      "treeSize": "25232879"
                    },
                    "integratedTime": "1730932627",
                    "kindVersion": {
                      "kind": "dsse",
                      "version": "0.0.1"
                    },
                    "logId": {
                      "keyId": "wNI9atQGlz+VWfO6LRygH4QUfY/8W4RFwiT5i5WRgB0="
                    },
                    "logIndex": "147137139"
                  }
                ]
              },
              "version": 1
            }
          ],
          "publisher": {
            "claims": null,
            "environment": "",
            "kind": "GitHub",
            "repository": "pypa/sampleproject",
            "workflow": "release.yml"
          }
        }
      ],
      "version": 1
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
