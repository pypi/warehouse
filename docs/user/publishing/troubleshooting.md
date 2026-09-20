---
title: Troubleshooting
---

# Troubleshooting

## Why am I getting "the description failed to render" error?
PyPI will reject uploads if the package description fails to render. You may [use twine's check command](https://twine.readthedocs.io/#twine-check) to locally check a description for validity.

## Why am I getting a "Filename or contents already exists" or "Filename has been previously used" error?
PyPI will return these errors for one of these reasons:

* Filename has been used and file exists
* Filename has been used but file no longer exists
* A file with the exact same content exists

PyPI does not allow for a filename to be reused, even once a project has been deleted and recreated.

A distribution filename on PyPI consists of the combination of project name, version number, and distribution type.

This ensures that a given distribution for a given release for a given project will always resolve to the same file, and cannot be surreptitiously changed one day by the projects maintainer or a malicious party (it can only be removed).

To avoid this situation in most cases, you will need to change the version number to one that you haven't previously uploaded to PyPI, rebuild the distribution, and then upload the new distribution.

## Why am I getting a "New uploads are temporarily disabled" or "Read-only mode" error?
During a large-scale spam or malware attack, or other threat to PyPI, administrators can temporarily disable new uploads for all users, independently of any action on your account or project. In the most severe cases, PyPI may enter a full read-only mode, where no uploads are accepted at all.

This is not specific to you or your project — check the PyPI [status page](https://status.python.org/) for updates and the reason for the intervention, and try again once the incident is resolved.

## Why am I getting an "Invalid or non-existent authentication information" error when uploading files?

1. Ensure that your API token is valid and has not been revoked (see below)
2. Ensure that your API token is correctly formatted and does not contain any trailing characters such as newlines.
3. Ensure that the username you are using is `__token__`.

Remember that PyPI and TestPyPI each require you to create an account, so your credentials may be different.

If you're using Windows and trying to paste your token in the Command Prompt or PowerShell, note that `Ctrl-V` and `Shift+Insert` won't work. Instead, you can use `Edit > Paste` from the window menu, or enable `Use Ctrl+Shift+C/V as Copy/Paste` in `Properties`. This is a [known issue](https://bugs.python.org/issue37426) with Python's getpass module.

## What should I do if I receive a compromised API token notification?

If you receive a notification that your API token has been compromised, it means a token associated with your account was found on a public website. For your protection, the exposed token was automatically revoked by PyPI. See [Compromised API tokens](../your-account/security-alerts.md#compromised-api-tokens) for what to do next.

## How can I publish my private packages to PyPI?
PyPI does not support publishing private packages. If you need to publish your private package to a package index, the recommended solution is to run your own deployment of the [devpi project](https://pypi.org/project/devpi/).
