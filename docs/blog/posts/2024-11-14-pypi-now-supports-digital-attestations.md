---
title: PyPI now supports digital attestations
description: Announcing support for PEP 740 on the Python Package Index
authors:
  - di
date: 2024-11-14
tags:
  - publishing
  - security
  - oidc
---

PyPI package maintainers can now publish signed digital attestations when
publishing, in order to further increase trust in the supply-chain security of
their projects. Additionally, a new API is available for consumers and
installers to verify published attestations.

Many projects have already begun publishing attestations, with more than 20,000
attestations already published.

This finalizes PyPI's support for [PEP 740], and follows directly from previous
work to add support for [Trusted Publishing], as well as the [deprecation and
removal of PGP signatures].

<!-- more -->

### Why not plain signatures?

PyPI's support for digital attestations has three key advantages over regular
cryptographic signatures, such as those provided by PGP:

* **Attestations are signed by an identity, not a key pair:**
  Similar to our recent support for Trusted Publishing, PyPI's support for
  digital attestations relies upon Open ID Connect (OIDC) identities. By signing
  attestations with identities, and not a public/private key pair, we mitigate the
  potential for an individual's key loss or compromise, one of the most common failure cases for
  PGP signing.
* **Attestations provide a verifiable link to an upstream source repository:**
  By signing with the identity of the upstream source repository, such as in the
  case of an upload of a project built with GitHub Actions, PyPI's support for
  digital attestations defines a strong and verifiable association between a file
  on PyPI and the source repository, workflow, and even the commit hash that
  produced and uploaded the file. Additionally, publishing attestations to a
  transparency log helps mitigate against both compromise of PyPI and compromise
  of the projects themselves.
* **Attestations are verified when uploaded, and must be verifiable to be uploaded:**
  Upon review of the state of historical PGP signatures published to PyPI, [we
  found that many signatures were not verifiable], either by PyPI or by end
  users. With support for PEP 740, PyPI only permits attestations with a
  verifiable signature to be uploaded and redistributed by the index. This
  ensures that all attestations are verifiable and useful for all PyPI users.

Much more detail is provided in a corresponding blog post by Trail of Bits:
[Attestations: a new generation of signatures on PyPI].

### How to view a file's attestations
For consumers and package installers wanting to perform verification, PyPI
currently provides two ways to access digital attestations associated with a
given file on PyPI:

* **A new Integrity API for PyPI**
  The [Integrity API](https://docs.pypi.org/api/integrity/) provides programmatic
  access to PyPI's implementation of PEP 740. Operating on individual files, it
  collects all published attestations for a given file and returns them as a
  single response.

* **A new web UI for viewing per-file attributes**
  Similarly, we have introduced a new page on PyPI's web UI, displaying details
  for individual files, including the presence of any attestations about the
  file. You can see an example here:
  <https://pypi.org/project/sampleproject/#sampleproject-4.0.0.tar.gz>

### Get started today

The generation and publication of attestations happens by default, and no
changes are necessary for projects that meet all of these conditions:

1. publish from GitHub Actions;
2. via [Trusted Publishing]; and
3. use the [pypa/gh-action-pypi-publish] action to publish.

Support for automatic attestation generation and publication from other Trusted
Publisher environments [is planned]. While not recommended, maintainers can also
[manually generate and publish attestations].

### Acknowledgements

Support for work on PEP 740's authoring and design was provided by the
[Sovereign Tech Agency] and the Google Open Source Security Team.

Funding for the implementation of PEP 740 was provided by the Google Open
Source Security Team, and much of the development work on PyPI and related
tools was performed by [Trail of Bits], with special thanks to contributors
[William Woodruff], [Facundo Tuesca], and [Alexis Challande].

Thanks to the the [Sigstore project] for their work popularizing identity-based signing, hosting a public-good transparency log, and continued support of the [Python client for Sigstore].

Many thanks to [Sviatoslav Sydorenko] as well for his support and ongoing
maintenance of the [pypa/gh-action-pypi-publish] action, as well his support
for implementing PEP 740 in the action.

---

_Dustin Ingram is a maintainer of the Python Package Index._

[PEP 740]: https://peps.python.org/pep-0740/
[Trusted Publishing]: https://docs.pypi.org/trusted-publishers/
[deprecation and removal of PGP signatures]: https://blog.pypi.org/posts/2023-05-23-removing-pgp/
[pypa/gh-action-pypi-publish]: https://github.com/pypa/gh-action-pypi-publish
[Attestations: a new generation of signatures on PyPI]: https://blog.trailofbits.com/2024/11/14/attestations-a-new-generation-of-signatures-on-pypi/
[Integrity API]: https://docs.pypi.org/api/integrity/
[we announced last year]: 2023-04-20-introducing-trusted-publishers.md
[we found that many signatures were not verifiable]: https://blog.yossarian.net/2023/05/21/PGP-signatures-on-PyPI-worse-than-useless
[manually generate and publish attestations]: https://docs.pypi.org/attestations/producing-attestations/#the-manual-way
[Sovereign Tech Agency]: https://www.sovereign.tech/tech/python-package-index
[is planned]: https://github.com/pypi/warehouse/issues/17001
[Trail of Bits]: https://www.trailofbits.com/
[William Woodruff]: https://github.com/woodruffw
[Facundo Tuesca]: https://github.com/facutuesca
[Alexis Challande]: https://github.com/DarkaMaul
[Sigstore project]: https://www.sigstore.dev/
[Python client for Sigstore]: https://pypi.org/project/sigstore/
[Sviatoslav Sydorenko]: https://github.com/webknjaz
