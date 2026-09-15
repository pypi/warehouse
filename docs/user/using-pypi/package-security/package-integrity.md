---
title: Verifying Package Integrity
---

# Verifying Package Integrity

Integrity checks confirm that the file you downloaded is **bit-for-bit identical to the one the author uploaded to PyPI**. This process helps protect you from [man-in-the-middle attacks](common-attacks.md#3-man-in-the-middle-mitm-attacks).

## File hashes (checksums)

A file hash, or checksum, is a unique digital fingerprint of a file. If a file is modified, its hash changes completely.

For every package file hosted on PyPI, there are corresponding hashes. You can use these to verify that the file you downloaded matches the one uploaded by the project maintainer—a practice that is especially useful when downloading packages from a mirror.

### How to obtain and verify hashes

You can obtain these hashes from the project page under the "Release Files" tab, or via the [JSON API](../../api/json.md).

![checksums](assets/checksum.png){ loading=lazy }

#### Automated verification
When installing packages with `pip`, you can use [hash checking mode](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode). In this mode, `pip` automatically verifies that the hash of the downloaded file matches the hash specified in your requirements file.

#### Manual verification
If you need to generate a hash manually to compare against the PyPI record, you can use Python’s `hashlib` library:

```python
import hashlib

# Replace with the path to your downloaded file
file_path = "file-path-to-verify"

with open(file_path, "rb") as f:
    file_contents = f.read()

blake2b_hash = hashlib.blake2b(file_contents, digest_size=32).hexdigest()
sha256_hash = hashlib.sha256(file_contents).hexdigest()

print(f"BLAKE2b-256: {blake2b_hash}\nSHA256: {sha256_hash}")
```

!!! info
    In practice, you only need to verify one of these hashes.

## Limitations

A hash only verifies that the file you have downloaded is the same as the one on PyPI's servers. It does not verify that the original code is safe or trustworthy. It also requires you to trust the source of the checksum you are using for verification, and that it was not tampered with or modified before you verified it.
