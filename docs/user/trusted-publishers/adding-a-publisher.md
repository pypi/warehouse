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

That link will take you to the publisher configuration page for the project,
which will allow you to configure trusted publishers for the different
platforms supported by PyPI (such as GitHub Actions).

To enable a publisher, you need to tell PyPI how to trust it. Each trusted
publisher has its own configuration requirements; click the tabs below to see
each.

=== "GitHub Actions"

    For GitHub Actions, you **must** provide the repository owner's name, the
    repository's name, and the filename of the GitHub Actions workflow that's
    authorized to upload to PyPI. In addition, you may **optionally**
    provide the name of a [GitHub Actions environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment).

    For example, if you have a project at `https://github.com/octo-org/sampleproject`
    that uses a publishing workflow defined in `.github/workflows/release.yml`
    and a custom environment named `release`, then you'd do the following:

    ![](/assets/project-publishing-form.png)

    !!! note

        Configuring an environment is optional, but **strongly** recommended:
        with a GitHub environment, you can apply additional restrictions to
        your trusted workflow, such as requiring manual approval on each run
        by a trusted subset of repository maintainers.

=== "Google Cloud"

    TODO

=== "ActiveState"

    TODO

=== "GitLab CI/CD"

    TODO

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
