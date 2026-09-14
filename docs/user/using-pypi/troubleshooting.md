---
title: Troubleshooting
---

# Troubleshooting Common Errors

## Why am I getting "the description failed to render" error?

PyPI will reject uploads if the package description fails to render. You may [use twine's check command](https://twine.readthedocs.io/#twine-check) to locally check a description for validity.

## How can I restore a deleted project, release or file?

Deletion of a project, release or file on PyPI is permanent and irreversible, without exception. Deletion of a project makes it uninstallable, and releases the project name for use by any other PyPI user. Deleted files [cannot be re-uploaded](https://pypi.org/help/#file-name-reuse). Deleted projects, releases or files cannot be restored by PyPI administrators. 

Instead of deleting projects, we recommend project owners [archive projects instead](../project-management/archiving-projects.md).

## Where does PyPI get its data on project vulnerabilities from, and how can I correct it?

PyPI receives reports on vulnerabilities in the packages hosted on it from the [Open Source Vulnerabilities project](https://osv.dev/), which in turn ingests vulnerabilities from the [Python Packaging Advisory Database](https://github.com/pypa/advisory-database).

If you believe vulnerability data for your project is invalid or incorrect, [file an issue](https://github.com/pypa/advisory-database/issues) with details.

## My project or release says it's in quarantine. What does that mean?

Projects and releases may get placed in quarantine for any number of reasons, such as suspicion of malicious activity, spam, or other violations of the [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) or [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/).

PyPI can quarantine either an entire project or a single release within it:

* A **quarantined project** is not installable by clients, and cannot be modified by its maintainers.
* A **quarantined release** is excluded from installation and from the index APIs, while the project's other releases are unaffected.

PyPI Administrators will need to review the project or release before it can be restored.

If you believe your project or release has mistakenly been flagged for quarantine, contact PyPI via [security@pypi.org](mailto:security@pypi.org) with any details.

## How can I publish my private packages to PyPI?

PyPI does not support publishing private packages. If you need to publish your private package to a package index, the recommended solution is to run your own deployment of the [devpi project](https://pypi.org/project/devpi/).
