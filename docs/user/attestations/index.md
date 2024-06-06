---
title: Getting Started
---

<!--[[ preview('index-attestations') ]]-->

# Digital Attestations for PyPI

These pages document PyPI's implementation of index attestations ([PEP 740]),
including in-toto attestation predicates specific to PyPI itself.

## Quick background

*Index attestations* enable package maintainers as well as third parties (such
as the index itself, external auditors, etc.) to *cryptographically sign*
for uploaded packages.

These signatures bind each release distribution (such as an individual sdist or
wheel) to a strong cryptographic digest of its contents, allowing both PyPI
and downstream users to verify that a particular package was attested to by
a particular identity (such as a GitHub Actions workflow).

These attestations can take multiple forms, including ["publish" attestations]
for publicly verifiable proof that a package was published via a specific
[Trusted Publisher], or more general [SLSA provenance] attesting to a package's
original source location.

[PEP 740]: https://peps.python.org/pep-0740/

["publish" attestations]: /attestations/publish/v1/

[Trusted Publisher]: /trusted-publishers/

[SLSA provenance]: https://slsa.dev/spec/v1.0/provenance
