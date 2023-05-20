---
title: Adding a Trusted Publisher to an Existing PyPI Project
---

# Adding a trusted publisher to an existing PyPI project

Adding a trusted publisher to a PyPI project only requires a single setup step.

On the ["Your projects" page](https://pypi.org/manage/projects/), click "Manage" on any project you'd like to
configure:

![](/assets/manage-link.png)

Then, click on "Publishing" in the project's sidebar:

![](/assets/project-publishing-link.png)

That link will take you to the publisher configuration page for the project:

![](/assets/project-publishing.png)

To enable a publisher, you need to tell PyPI how to trust it. For
GitHub Actions (the only currently supported publisher), you do this by
providing the repository owner's name, the repository's name, and the
filename of the GitHub Actions workflow that's authorized to upload to
PyPI.

For example, if you have a project at `https://github.com/octo-org/sampleproject`
that uses a publishing workflow defined in `.github/workflows/release.yml`
and a custom environment named `release`, then you'd do the following:

![](/assets/project-publishing-form.png)

!!! note

    Configuring an environment is optional, but **strongly** recommended:
    with a GitHub environment, you can apply additional restrictions to
    your trusted workflow, such as requiring manual approval on each run
    by a trusted subset of repository maintainers.

Once you click "Add", your publisher will be registered and will appear
at the top of the page:

![](/assets/project-publisher-registered.png)

From this point onwards, the `release.yml` workflow on `octo-org/sampleproject` will
be able to generate short-lived API tokens from PyPI for the project you've registered
it against.

A publisher can be registered against multiple PyPI projects (e.g. for a
multi-project repository), and a single PyPI project can have multiple
publishers (e.g. for multiple workflows on different architectures, operating
systems).
