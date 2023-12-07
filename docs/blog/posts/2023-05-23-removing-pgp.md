---
title: Removing PGP from PyPI
description: PyPI has removed support for uploading PGP signatures with new releases.
authors:
  - dstufft
date: 2023-05-23
tags:
  - security
---

If you are someone who is currently uploading signatures, your package uploads will
continue to succeed, but any PGP signatures will be silently ignored. If you are
someone who is currently downloading PGP signatures, existing signatures
*SHOULD* continue to be available [^1], but no new signatures will be made available.
The related API fields such as `has_sig` have all been hardcoded to always be
`False`.

<!-- more -->

Historically, PyPI has supported uploading PGP signatures alongside the release
artifacts in an attempt to provide some level of package signing. However, the
approach used had long standing,
[documented issues](https://caremad.io/posts/2013/07/packaging-signing-not-holy-grail/)
which had previously lead us to deemphasize the support
for PGP signatures over time by removing them from the PyPI web user interface.

PyPI has continued to support uploading these signatures in the hope that there
might be some systems out there that found them useful. Recently though,
[an examination of the signatures on PyPI](https://blog.yossarian.net/2023/05/21/PGP-signatures-on-PyPI-worse-than-useless)
has revealed to us that the current support for PGP signatures is not proving useful.

In the last 3 years, about 50k signatures had been uploaded to PyPI by 1069
unique keys. Of those 1069 unique keys, about 30% of them were not discoverable
on major public keyservers, making it difficult or impossible to meaningfully
verify those signatures. Of the remaining 71%, nearly half of them were unable
to be meaningfully verified at the time of the audit (2023-05-19) [^2].

In other words, out of all of the unique keys that had uploaded signatures to
PyPI, only 36% of them were capable of being meaningfully verified [^3] at the
time of audit. Even if *all* of those signatures uploaded in that 3 year period
of time were made by one of those 36% of keys that are able to be meaningfully
verified, that would still represent only 0.3% of all of those files.

Given all of this, the continued support of uploading PGP signatures to PyPI is
no longer defensible. While it doesn't represent a *massive* operational burden
to continue to support it, it does require any new features that touch the
storage of files to be made aware of and capable of handling these PGP
signatures, which is a non zero cost on the maintainers and contributors of
PyPI.

---

_Donald Stufft is a PyPI administrator and maintainer of the Python Package Index since 2013._


[^1]: For now, but they may be removed in the future.
[^2]: These could be because the original signature was made incorrectly and
      never had a binding signature to a associated key identity, or because
      the signature was present but had since expired.
[^3]: We use meaningfully verified to mean that the signature was valid and the
      key that made it was not expired and had binding identify information that
      could tell us if this key was the correct key.
