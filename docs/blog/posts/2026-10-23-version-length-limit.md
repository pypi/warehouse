---
title: PyPI now limits versions to 128 characters
description: >
  New uploads to PyPI must have a version that is 128 characters or less.
  Existing releases are not affected.
authors:
  - jacobcoffee
date: 2026-10-23
tags:
  - user-interface
---

PyPI now rejects new uploads whose version is longer than **128 characters**.

This affects almost no one: across the roughly 9.9 million releases on PyPI,
only 2 have a version that long. Releases that are already on PyPI stay
exactly as they are, and installing them works the same as before.

<!-- more -->

## Why add a limit?

The rules for Python version numbers have never set a maximum length.
Nearly every project uses short, ordinary versions. Half of all releases on
PyPI have a version of 5 characters or fewer, like `1.4.2`, and 99% have 20
characters or fewer. The longest one on PyPI today is 217 characters.

Versions that long don't help anyone install or understand a project.
They make project pages harder to read, they're hard to fit anywhere a
version is shown, and they're especially hard to follow for people who use
screen readers or zoom in to read. Very long versions have come up on PyPI's
issue tracker before ([#12483], [#14965]).

128 characters is well above anything a real project needs, while still
keeping PyPI's pages readable, although version lengths of less than 20 characters
are recommended.

## How is the length counted?

PyPI counts the version in its normalized, standard form, which is the same
form it shows on project pages. Python's packaging tools already
[normalize versions][normalized] this way: `1.00` becomes `1.0`, and `1.0-RC1` becomes
`1.0rc1`. The meaning doesn't change, only how it's written.

## What happens if my upload is rejected?

You'll see an error like this when you upload:

```
HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/
The version must be 128 characters or less after normalization, but is 140 characters.
See https://docs.pypi.org/project_metadata/#version-length-limit for more information.
```

Pick a shorter version and upload again. Details like build dates or commit
IDs are better kept in your changelog or project description than in the
version itself. The [version length limit] documentation has more details.

## Is this a new packaging standard?

No. We [discussed] adding a limit to the shared rules for Python versions,
and the consensus was that each package index can set its own limit.
This is a PyPI policy. Tools like pip and uv don't need to change, and other
package indexes are free to make their own choice.

[#12483]: https://github.com/pypi/warehouse/issues/12483
[#14965]: https://github.com/pypi/warehouse/issues/14965
[normalized]: https://packaging.python.org/en/latest/specifications/version-specifiers/#normalization
[version length limit]: https://docs.pypi.org/project_metadata/#version-length-limit
[discussed]: https://discuss.python.org/t/amend-pep440-to-limit-version-identifiers/109629
