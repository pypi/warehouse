---
title: Verifying Package Integrity
---

# Verifying Package Integrity

Integrity checks confirm that the file you downloaded is **bit-for-bit identical to the one the author uploaded to PyPI**. This helps protect you from [man-in-the-middle attacks](common-attacks.md#man-in-the-middle-mitm-attacks).

## File hashes

A file hash is a unique digital fingerprint of a file. If the file is modified, its hash changes completely.

For each package file hosted on PyPI, there are corresponding hashes. These hashes can be used to verify that the file you are downloading is the same one that the project maintainer uploaded. This is especially useful if downloading packages from a mirror. The hashes can be obtained from the project page in the "Release Files" section or from the [JSON API](../../api/json.md).

<!-- TODO: add image -->
Figure: a screenshot of file hashes on PyPI. These can be used to verify that the file you have downloaded is the same as the file hosted on PyPI's servers

When you install packages using pip using [hash checking mode](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode), pip will automatically verify that the hash of the downloaded file matches the hash from your requirements file.

## Limitations

A hash only verifies that the file you have downloaded is the same as the one on PyPI's servers. It does not verify that the original code is safe or trustworthy. It also requires you to trust the source of the checksum you are using for verification, and that it was not tampered with or modified before you verified it.
