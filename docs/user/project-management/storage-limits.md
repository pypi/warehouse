---
title: Storage Limits
---

PyPI imposes storage limits on the size of individually uploaded files,
as well as the total size of all files in a project.

The current default limits are **100.0 MB** for individual files and **10.0 GB**
for the entire project.

You can see your project's current size and storage limits on
the project settings page (`https://pypi.org/manage/project/YOUR-PROJECT/settings/`):

![](/assets/project-size-and-limits.png)

## File size limits

By default, PyPI limits the size of individual files to **100.0 MB**.
If you attempt to upload a file that exceeds this limit, you'll receive
an error like the following:

```console
Uploading sampleproject-1.2.3.tar.gz
HTTPError: 400 Client Error: File too large. Limit for project 'sampleproject' is 100 MB.
```

### Requesting a file size limit increase

!!! note

    Note: All users submitting feedback, reporting issues or contributing to
    PyPI are expected to follow the
    [PSF Code of Conduct](https://github.com/pypa/.github/blob/main/CODE_OF_CONDUCT.md).

If you can't upload your project's release to PyPI because you're hitting the
upload file size limit, we can sometimes increase your limit. Make sure you've
uploaded at least one release for the project that's under the limit
(a [developmental release version number](https://packaging.python.org/en/latest/specifications/version-specifiers/#developmental-releases) is fine). Then,
[file an issue](https://github.com/pypi/support/issues/new?assignees=&labels=limit+request&template=limit-request-file.yml&title=File+Limit+Request%3A+PROJECT_NAME+-+000+MB) and tell
us:

- A link to your project on PyPI (or TestPyPI)
- The size of your release, in megabytes
- Which index/indexes you need the increase for (PyPI, TestPyPI, or both)
- A brief description of your project, including the reason for the additional size.

## Project size limits

By default, PyPI limits the total size of all files in a project to **10.0 GB**.
If you attempt to upload a file that would exceed this limit, you'll receive
an error like the following:

```console
Uploading sampleproject-1.2.3.tar.gz
HTTPError: 400 Client Error: Project size too large. Limit for project 'sampleproject' total size is 10 GB.
```

### Freeing up storage on an existing project

!!! important

    Deleting and [yanking](./yanking.md) are two different actions. Yanking a release or file
    does **not** free up storage space.

!!! warning

    Deleting releases and files from your project is permanent and cannot be undone
    without administrative intervention.

!!! warning

    Deletion can be very disruptive for downstream dependencies of your project,
    since it breaks installation for
    [pinned versions](https://pip.pypa.io/en/stable/topics/repeatable-installs/).

    Before performing a deletion, we **strongly** recommend that you
    consider the potential impact on your downstreams.

If you're hitting the project size limit, you can free up storage by removing
old releases or individual files from your project. To do this:

1. Navigate to the release management for your project: `https://pypi.org/manage/project/YOUR-PROJECT/releases/`;
2. Click on `Options` next to the release you wish to delete from;
    - If you wish to delete the entire release, click `Delete`;
    - If you wish to delete individual files from the release, click `Manage`,
      then use each file's `Options` menu to delete it.

### Requesting a project size limit increase

!!! note

    Note: All users submitting feedback, reporting issues or contributing to
    PyPI are expected to follow the
    [PSF Code of Conduct](https://github.com/pypa/.github/blob/main/CODE_OF_CONDUCT.md).

If you can't upload your project's release to PyPI because you're hitting the project size limit,
first [remove any unnecessary releases or individual files](#freeing-up-storage-on-an-existing-project)
to lower your overall project size.

If that is not possible, we can sometimes increase your limit. [File an issue](https://github.com/pypi/support/issues/new?assignees=&labels=limit+request&template=limit-request-project.yml&title=Project+Limit+Request%3A+PROJECT_NAME+-+00+GB) and tell us:

- A link to your project on PyPI (or TestPyPI)
- The total size of your project, in gigabytes
- A brief description of your project, including the reason for the additional size.
