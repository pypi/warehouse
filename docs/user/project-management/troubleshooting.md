---
title: Troubleshooting
---

# Troubleshooting

## How can I restore a deleted project, release or file?
Deletion of a project, release or file on PyPI is permanent and irreversible, without exception. Deletion of a project makes it uninstallable, and releases the project name for use by any other PyPI user. Deleted files [cannot be re-uploaded](../publishing/troubleshooting.md#why-am-i-getting-a-filename-or-contents-already-exists-error). Deleted projects, releases or files cannot be restored by PyPI administrators. 

Instead of deleting projects, we recommend project owners [archive projects instead](archiving-projects.md).

## Where does PyPI get its data on project vulnerabilities from, and how can I correct it?
PyPI receives reports on vulnerabilities in the packages hosted on it from the [Open Source Vulnerabilities project](https://osv.dev/), which in turn ingests vulnerabilities from the [Python Packaging Advisory Database](https://github.com/pypa/advisory-database).

If you believe vulnerability data for your project is invalid or incorrect, [file an issue](https://github.com/pypa/advisory-database/issues) with details.

## My project or release says it's in quarantine. What does that mean?
Projects or individual releases may get placed in quarantine for any number of reasons, such as suspicion of malicious activity, spam, or other violations of the [Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) or [Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/).

While in quarantine, the project or release is not installable by clients, cannot be modified by its maintainers, and is excluded from PyPI's search results and index APIs. When a single release is quarantined, other releases of the same project are unaffected. PyPI Administrators will need to review it before it can be restored.

If you believe your project or release has mistakenly been flagged for quarantine, contact PyPI via [security@pypi.org](mailto:security@pypi.org) with any details.
