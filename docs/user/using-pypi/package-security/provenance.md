---
title: Checking Provenance (package origin)
---

# Checking Provenance - where a package came from

## What is Provenance?

**Provenance** describes where a release file came from. On PyPI, provenance is shared via **attestations**, which provide a verifiable record of the build or publishing details.

## What is an attestation?

An attestation describes how, when, and where a package was built or published.

The presence of an attestation, and the information within it, can help protect you from [account takeover attacks](common-attacks.md#account-takeover-ato) and [supply chain attacks](common-attacks.md#supply-chain-attacks).

Attestations can be verified, helping you decide whether a package is safe to use.

## Attestations on PyPI

If a file on PyPI has an attestation, it is displayed:
1. On the "security" tab
2. On the file detail page

Attestations contain key details about the origin of the file, which may include:

- What source repository and source commit was used to build or publish the package
- What platform (e.g. GitHub Actions) built or published the package
- What workflow built or published the package

<!-- add image -->
Figure: a screenshot of a build provenance attestation on PyPI

Each attestation is recorded in a public ledger as [transparency log entry](https://docs.sigstore.dev/logging/overview/) ([example](https://search.sigstore.dev/?logIndex=227282797)), which is a permanent, auditable record that cannot be changed.

<!-- add image -->
Figure: a screenshot of a sigstore transparency log entry on the [Sigstore Rekor public ledger](https://docs.sigstore.dev/logging/overview/)

## Attestation types

PyPI currently supports two types of attestations:

1. **[PyPI publish attestations](../../attestations/publish/v1/)**: An attestation, created and signed by the uploading workflow, confirming that a file was uploaded via a PyPI [Trusted Publishing](../../publishing/trusted-publishers/), and that a specific Trusted Publisher identity was used to publish the file, such as a particular GitHub Actions workflow.

   PyPI verifies this attestation at upload time, confirming that the identity matches what the package maintainer previously configured for Trusted Publishing.

   Currently, the vast majority of attestations on PyPI are PyPI publish attestations. This is because producing these attestations happens by default in [the canonical workflow used by many package maintainers to publish packages.](https://github.com/marketplace/actions/pypi-publish)

2. **[SLSA attestation](https://slsa.dev/provenance/v1)**: An attestation and associated transparency log, signed by the build platform (e.g., GitHub, Google Cloud), that details exactly how the file was produced, cryptographically linking the final artifact back to its original source code (if available), build instructions or build log.

## Verifying attestations

Tools like pip and uv are currently working on functionality to automatically verify attestations when you install a package. This upcoming feature will be an integral part of the installation process, meaning you won't need to take any extra steps to check attestations.

Instead, when you install a package, the tools will automatically flag a potential security risk if there's a discrepancy between the provided attestation and what you intended to install.

In the meantime, users can manually consume and verify attestations for a project by retrieving them from PyPI's [Integrity API](../../api/integrity.md). See our [documentation on consuming attestations](../../attestations/consuming-attestations.md) for additional information.

## Provenance/attestation warnings

TODO: add content here about provenance warning states.

## Attestation limitations

Attestations are a big step forward for securing the Python packaging ecosystem, but they do have limitations:

- **Code Safety**: An attestation only tells you where a file came from. It does not mean the original code or the build environment is safe or trustworthy.

- **Implicit Trust**: When you trust an attestation, you are implicitly trusting the processes and authority of the organization that issued it.

For detailed information about attestations, including how to produce and consume them, see the [attestations documentation](../../../attestations/).
