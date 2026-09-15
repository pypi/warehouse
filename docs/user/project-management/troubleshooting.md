---
title: Troubleshooting
---

# Troubleshooting

## Why am I getting "the description failed to render" error?
PyPI will reject uploads if the package description fails to render. You may [use twine's check command](https://twine.readthedocs.io/#twine-check) to locally check a description for validity.

## How can I restore a deleted project, release or file?
Deletion of a project, release or file on PyPI is permanent and irreversible, without exception. Deletion of a project makes it uninstallable, and releases the project name for use by any other PyPI user. Deleted files [cannot be re-uploaded](#why-am-i-getting-a-filename-or-contents-already-exists-error). Deleted projects, releases or files cannot be restored by PyPI administrators. 

Instead of deleting projects, we recommend project owners [archive projects instead](archiving-projects.md).

## Why am I getting a "Filename or contents already exists" error?
PyPI returns this error for one of the following reasons:

* The filename has been used before, and the file still exists
* The filename has been used before, but the file no longer exists (for example, it was deleted)
* A file with the exact same content already exists

PyPI does not allow a filename to be reused, even after the original project, release, or file has been deleted and recreated.

## Where does PyPI get its data on project vulnerabilities from, and how can I correct it?
PyPI receives reports on vulnerabilities in the packages hosted on it from the [Open Source Vulnerabilities project](https://osv.dev/), which in turn ingests vulnerabilities from the [Python Packaging Advisory Database](https://github.com/pypa/advisory-database).

If you believe vulnerability data for your project is invalid or incorrect, [file an issue](https://github.com/pypa/advisory-database/issues) with details.

## My project or release says it's in quarantine. What does that mean?
Projects or individual releases may get placed in quarantine for any number of reasons, such as suspicion of malicious activity, spam, or other violations of the [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) or [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/).

While in quarantine, the project or release is not installable by clients, cannot be modified by its maintainers, and is excluded from PyPI's search results and index APIs. When a single release is quarantined, other releases of the same project are unaffected. PyPI Administrators will need to review it before it can be restored.

If you believe your project or release has mistakenly been flagged for quarantine, contact PyPI via [security@pypi.org](mailto:security@pypi.org) with any details.

## Why am I getting a "New uploads are temporarily disabled" or "Read-only mode" error?
During a large-scale spam or malware attack, or other threat to PyPI, administrators can temporarily disable new uploads for all users, independently of any action on your account or project. In the most severe cases, PyPI may enter a full read-only mode, where no uploads are accepted at all.

This is not specific to you or your project — check the PyPI [status page](https://status.python.org/) for updates and the reason for the intervention, and try again once the incident is resolved.

## How can I publish my private packages to PyPI?
PyPI does not support publishing private packages. If you need to publish your private package to a package index, the recommended solution is to run your own deployment of the [devpi project](https://pypi.org/project/devpi/).
