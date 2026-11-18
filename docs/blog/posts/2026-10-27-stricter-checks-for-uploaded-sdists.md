---
title: Stricter checks for uploaded distributions on PyPI
description: >
  PyPI has added and will continue adding more checks against
  uploaded source and built distributions, as part of a larger effort to
  reduce archive differentials in the Python packaging ecosystem
  and conform with Python packaging standards.
authors:
  - woodruffw
date: 2026-11-18
tags:
  - apis
  - security
  - integrations
---

Over the past few months, PyPI has added some additional checks that
can reject uploaded source distributions ("sdists") and built
distributions ("bdists" or "wheels").

These checks are part of a larger initiative to make the Python packaging
ecosystem more resistant to parser differentials, and will be followed
by additional checks that aim to make PyPI's handling of distributions
less permissive and more strictly conformant to their respective specifications.

For downstream users (package consumers), there are **no breaking implications**
to these changes. Package maintainers who see failures should ensure that
they're using non-EOL versions of Python as well as build backends
that produce distributions that properly conform to the packaging
standards.

<!-- more -->

## Background

Python packaging has two primary distribution formats:

- Source distributions, or _sdists_. These are distributed as compressed tar archives ("tarballs") with the suffix `.tar.gz`.
- Built distributions, or _bdists_ (or _wheels_). These are distributed as ZIP archives with the suffix `.whl`.

Neither tar nor ZIP was designed for the role it serves in Python packaging[^packaging]: both represent
metadata that is irrelevant to Python package distribution, and
are surrounded by an ecosystem of parsers that are permissive in their interpretation of inputs.
This laxity is often correct in a local user setting, where users often want to recover important data from
corrupted or otherwise slightly incorrect archives.

However, it's **incorrect** in a networked setting,
particularly a packaging one: even small differences in parsing between [separately permissive implementations]
can result in [parser differentials] that can result in identical inputs extracting
differently on different platforms and with different tools.

[separately permissive implementations]: https://alexgaynor.net/2025/mar/25/postels-law-and-the-three-ring-circus/

[parser differentials]: https://langsec.org/

In principle, an attacker can use differentials to violate many of the properties that Python
packaging (and end users) assume, including:

- That PyPI's own parse of each uploaded distribution (including sensitive metadata like dependencies)
  is consistent with what each installer sees;
- That third-parties (like mirrors and security scanners) "see" the same distribution contents as PyPI
  does;
- That invocations like `pip install ...` and `uv add ...` produce the same installation state.

Violations of these properties can result in users installing distributions that look legitimate
but are actually malicious, even when the distribution's own integrity (e.g. via hashing) is established.

## Changes

Over the last few weeks, PyPI has begun rejecting:

- Source distributions that use "V7"-style tar archives. V7 is a legacy and mostly unspecified
  tar format that comes from UNIX V7 and was never produced by Python's own `tarfile` module.

- Built distributions that include archive-level ZIP comments that could be misinterpreted
  as ZIP control structures.

These changes built on top of [earlier work performed by Seth Larson] last August aimed specifically
at ZIP differential reduction.

[earlier work performed by Seth Larson]: https://blog.pypi.org/posts/2025-08-07-wheel-archive-confusion-attacks/

## What does this mean for me?

If you're a downstream user of Python packaging: **nothing**! These changes **will not directly affect you**,
and any distributions that you already depend on (through `pip install` or `uv add`) will continue to
work.

If you're a package maintainer: **nothing, probably**. The overwhelming majority of source distributions on PyPI
are **not affected** by these changes, because they were already conforming with the pax requirement.

If you're a maintainer and you _do_ encounter an upload rejection for archive format reasons,
please consult PyPI's [archives documentation]. PyPI will endeavour to keep that page up-to-date as we
ratchet down on malformed or non-conforming uploads.

For many maintainers, the fix will be straightforward:

- Make sure that your distributions (both sdists and bdists) are built with a Python build backend,
  and _not_ by manually packing an archive with `tar`, `zip`, or similar. Popular build backends generally
  conform to both the distribution format specifications and to PyPI's additional archive restrictions.

- If you're unable to migrate away from a manual packing step, make sure that you're manually
  conforming to the archive requirements, namely:

    - [Source distributions] **must** be POSIX pax-style tar archives. If you're using GNU `tar`, you'll
      need to pass `--format=pax` to override the default.
        - Moreover, source distributions **must** avoid certain tar features, even if they can be
          framed within a pax-conforming tar. These include "sparse" members and pax vendor extensions.

    - [Built distributions] **must** be valid ZIP archives.

    - Both formats require UTF-8 encoded filenames for their members.

[archives documentation]: https://docs.pypi.org/archives/

[Source distributions]: https://packaging.python.org/en/latest/specifications/source-distribution-format/

[Built distributions]: https://packaging.python.org/en/latest/specifications/binary-distribution-format/

## What's next?

This is an ongoing initiative, one that involves multiple facets of the Python ecosystem.
We aim to align this work with Python itself (by reducing the number of differentials
in Python's own `zipfile` and `tarfile`), as well as Python packaging's standards (by further
constraining and improving the precision of the distribution specifications).

Going forwards, PyPI will continue to identify new restrictions that it can apply to uploaded
distributions. Our goal is to identify **safe** restrictions, i.e. ones that can be made
without breaking (almost) any users. Archive differentials overwhelmingly take advantage of
obscure or unused aspects of archive formats, so this is frequently possible.

In the near term, PyPI will be evaluating the following additional restrictions:

- Rejecting GNU-style tar archives entirely. These are already forbidden by the source
  distribution specification, but are currently allowed because of non-trivial use
  by maintainers. See [#21012] for our initial plans on this.

- Rejecting ZIP comments entirely. PyPI already rejects many forms of these, but allows
  a small subset for compatibility with ZIP encoders that put innocuous messages (like
  their version number) in archive comments. See [#20934] for our initial plans on this.

[#21012]: https://github.com/pypi/warehouse/issues/21012

[#20934]: https://github.com/pypi/warehouse/issues/20934

[^packaging]: Among so many other packaging ecosystems.

