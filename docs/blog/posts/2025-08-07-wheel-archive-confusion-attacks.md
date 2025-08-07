---
title: Preventing ZIP parser confusion attacks on Python package installers
description: PyPI will begin warning and will later reject wheels that contain differentiable ZIP features or incorrect RECORD files.
authors:
  - sethmlarson
date: 2025-08-07
tags:
  - security
  - publishing
  - deprecation
---

The Python Package Index is introducing new restrictions to protect
Python package installers and inspectors from confusion attacks arising
from ZIP parser implementations. This has been done in response to
the discovery that the popular installer uv has a different extraction behavior
to many Python-based installers that use the ZIP parser implementation
provided by the `zipfile` standard library module.

## Summary

* ZIP archives constructed to exploit ZIP confusion attacks are now rejected by PyPI.
* There is no evidence that this vulnerability has been exploited using PyPI.
* PyPI is deprecating wheel distributions with incorrect `RECORD` files.

Please see [this blog post](https://astral.sh/blog/uv-security-advisory-cve-2025-54368) and [CVE-2025-54368](https://www.cve.org/CVERecord?id=CVE-2025-54368)
for more information on uv's patch.

<!-- more -->

## Wheels are ZIPs, and ZIPs are complicated

Python package "wheels" (or "binary distributions"), like many other file formats,
actually a ZIP in disguise. The [ZIP archive standard](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT) was created in 1989, where large archives
might need to be stored across multiple distinct storage units due to size constraints. This requirement influenced
the design of the ZIP archive standard, such as being able to update or delete already-archived
files by appending new records to the end of a ZIP instead of having to rewrite the entire ZIP
from scratch which might potentially be on another disk.

These design considerations meant that the ZIP standard is complicated to implement, and
in many ways is ambiguous in what the "result" of extracting a valid ZIP file should be.

The ["Binary Distribution Format" specification](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#binary-distribution-format)
defines how a wheel is [meant to be installed](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#installing-a-wheel-distribution-1-0-py32-none-any-whl).
However, the specification leaves many of the details on how exactly to extract the archive
and handle ZIP-specific features to implementations. The most detail provided is:

> Although a specialized installer is recommended, a wheel file may be installed by simply unpacking into site-packages with the standard ‘unzip’ tool while preserving enough information to spread its contents out onto their final paths at any later time.

This means that ZIP ambiguities are unlikely to be caught by installers, as there are no
restrictions for which ZIP features are allowed in a valid wheel archive.

There's also a Python packaging specific mechanism for which files are meant to be included
in a wheel. The `RECORD` file included inside wheel `.dist-info` directories
lists files by name and optionally a checksum (like SHA256).
The [specification for the `.dist-info` directory](https://packaging.python.org/en/latest/specifications/binary-distribution-format/#the-dist-info-directory)
details how installers are supposed to check the contents of the ZIP archive against `RECORD`:

> Apart from `RECORD` and its signatures, installation will fail if any file in the archive is not both mentioned and correctly hashed in `RECORD`.

However, most Python installers today do not do this check and extract the contents
of the ZIP archive similar to `unzip` and then amend the installed `RECORD` within the
virtual environment so that uninstalling the package works as expected.

This means that there is no forcing function on Python projects and
packaging tools to follow packaging standards or normalize their use of ZIP archive features.
This leads to the ambiguous situation today where no one installer can start
enforcing standards without accidentally "breaking" projects and archives
that already exist on PyPI.

PyPI is adopting a few measures to prevent attackers from abusing the complexities
of ZIP archives and installers not checking `RECORD` files to smuggle files past
manual review processes and automated detection tools.

## What is PyPI doing to prevent ZIP confusion attacks?

The correct method to unpack a ZIP is to first check the Central Directory
of files before extracting entries. See this [blog post](https://www.crowdstrike.com/en-us/blog/how-to-prevent-zip-file-exploitation/)
for a more detailed explanation of ZIP confusion attacks.

PyPI is implementing the following logic to prevent ZIP confusion attacks on
the upload of wheels and ZIPs:

* Rejecting ZIP archives with invalid record and framing information.
* Rejecting ZIP archives with duplicate filenames in Local File and Central Directory headers.
* Rejecting ZIP archives where files included in Local File and Central Directory headers don't match.
* Rejecting ZIP archives with trailing data or multiple End of Central Directory headers.
* Rejecting ZIP archives with incorrect End of Central Directory Locator values.

PyPI already implements ZIP and tarball compression-bomb detection
as a part of upload processing.

PyPI will also begin sending emails to **warn users when wheels are published
whose ZIP contents don't match the included `RECORD` metadata file**. After 6 months of warnings,
on February 1st, 2026, PyPI will begin **rejecting** newly uploaded wheels whose ZIP contents
don't match the included `RECORD` metadata file.

We encourage all Python installers to use this opportunity to
implement cross-checking of extracted wheel contents with the `RECORD` metadata file.

## `RECORD` and ZIP issues in top Python packages

Almost all the top 15,000 Python packages by downloads (of which 13,468 publish wheels)
have no issues with the ZIP format or the `RECORD` metadata file.
This makes us confident that we can deploy
these changes without major disruption of existing Python project
development.

| Status                              | Number of Projects |
|-------------------------------------|--------------------|
| No `RECORD` or ZIP issues           | 13,460             |
| Missing file from `RECORD`          | 4                  |
| Mismatched `RECORD` and ZIP headers | 2                  |
| Duplicate files in ZIP headers      | 2                  |
| Other ZIP format issues             | 0                  |

Note that there are more occurrences of ZIP and `RECORD` issues
that have been reported for other projects on PyPI, but those projects
are not in the top 15,000 by downloads.

## What actions should I take?

The mitigations above mean that
users of PyPI, regardless of their installer, don't need to take immediate action
to be safe. We recommend the following actions to users of PyPI to ensure
compliance with Python package and ZIP standards:

* **For users installing PyPI projects**: Make sure your installer tools are up-to-date.
* **For maintainers of PyPI projects**: If you encounter an error during upload,
  read the error message and update your own build process or report the issue
  to your build tool, if applicable.
* **For maintainers of installer projects**: Ensure that your ZIP implementation follows the ZIP standard
  and checks the Central Directory before proceeding with decompression.
  See the CPython `zipfile` module for a ZIP implementation that implements this
  logic. Begin checking the `RECORD` file against ZIP contents and erroring
  or warning the user that the wheel is incorrectly formatted.
  
## Acknowledgements

Thanks to Caleb Brown (Google Open Source Security Team) and Tim Hatch (Netflix) for reporting this issue.

This level of coordination across Python ecosystem projects requires significant
engineering time investment. Thanks to [Alpha-Omega](https://alpha-omega.dev) who sponsors the security-focused
[Developer-in-Residence](https://www.python.org/psf/developersinresidence/) positions at the Python Software Foundation.
