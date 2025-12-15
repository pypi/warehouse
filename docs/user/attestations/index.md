---
title: Introduction
---

These pages document PyPI's implementation of digital attestations ([PEP 740]),
including in-toto attestation predicates specific to PyPI itself.

## Quick background

*Digital attestations* enable package maintainers as well as third parties (such
as the index itself, external auditors, etc.) to *cryptographically sign*
for uploaded packages.

These signatures bind each release distribution (such as an individual sdist or
wheel) to a strong cryptographic digest of its contents, allowing both PyPI
and downstream users to verify that a particular package was attested to by
a particular identity (such as a GitHub Actions workflow).

These attestations can take multiple forms, including [publish attestations]
for publicly verifiable proof that a package was published via a specific
[Trusted Publisher], or more general [SLSA Provenance] attesting to a package's
original source location.

## Supported attestations

PyPI uses the [in-toto Attestation Framework] for the attestations it accepts.

Currently, PyPI allows the following attestation predicates:

* [SLSA Provenance]
* [PyPI Publish]

Each file can be uploaded along its attestations. Currently PyPI supports two
attestations per file: one for each of the allowed predicates. Uploads with more
than two attestations per file, or with attestations with repeated predicates will
be rejected.

Currently, PyPI allows for attestations to be signed by the following Trusted
Publisher identities:

* [GitHub Actions]
* [GitLab CI/CD]
* [Google Cloud]

[in-toto Attestation Framework]: https://github.com/in-toto/attestation/blob/main/spec/README.md

[PEP 740]: https://peps.python.org/pep-0740/

[PyPI Publish]: /attestations/publish/v1/

[publish attestations]: /attestations/publish/v1/

[Trusted Publisher]: /trusted-publishers/

[SLSA Provenance]: https://slsa.dev/spec/v1.0/provenance

[GitHub Actions]: /trusted-publishers/using-a-publisher/#github-actions

[GitLab CI/CD]: /trusted-publishers/using-a-publisher/#gitlab-cicd

[Google Cloud]: /trusted-publishers/using-a-publisher/#google-cloud

