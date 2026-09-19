---
title: Troubleshooting
---

# Troubleshooting

## Why am I getting "the description failed to render" error?
PyPI will reject uploads if the package description fails to render. You may [use twine's check command](https://twine.readthedocs.io/#twine-check) to locally check a description for validity.

## Why am I getting a "Filename or contents already exists" error?
PyPI returns this error for one of the following reasons:

* The filename has been used before, and the file still exists
* The filename has been used before, but the file no longer exists (for example, it was deleted)
* A file with the exact same content already exists

PyPI does not allow a filename to be reused, even after the original project, release, or file has been deleted and recreated.

## Why am I getting a "New uploads are temporarily disabled" or "Read-only mode" error?
During a large-scale spam or malware attack, or other threat to PyPI, administrators can temporarily disable new uploads for all users, independently of any action on your account or project. In the most severe cases, PyPI may enter a full read-only mode, where no uploads are accepted at all.

This is not specific to you or your project — check the PyPI [status page](https://status.python.org/) for updates and the reason for the intervention, and try again once the incident is resolved.

## How can I publish my private packages to PyPI?
PyPI does not support publishing private packages. If you need to publish your private package to a package index, the recommended solution is to run your own deployment of the [devpi project](https://pypi.org/project/devpi/).
