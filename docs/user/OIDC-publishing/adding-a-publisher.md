---
title: Adding an OIDC publisher to a PyPI project
---

{{ preview('oidc-publishing') }}

# Adding an OIDC publisher to a PyPI project

Adding an OIDC publisher to a PyPI project only requires a single setup step.

On the "Your projects" page, click "Manage" on any project you'd like to
configure:

![](/assets/manage-link.png)

Then, click on "Publishing" in the project's sidebar:

![](/assets/project-publishing-link.png)

That link will take you to the OIDC publisher configuration page for the project:

![](/assets/project-publishing.png)

To enable an OIDC publisher, you need to tell PyPI how to trust it. For
GitHub Actions (the only currently supported provider), you do this by
providing the repository owner's name, the repository's name, and the
filename of the GitHub Actions workflow that's authorized to upload to
PyPI.

For example, if you have a project at `https://github.com/pypa/pip-audit`
that uses a publishing workflow defined in `.github/workflows/release.yml`,
then you'd do the following:

![](/assets/project-publishing-form.png)

Once you click "Add", your OIDC publisher will be registered and will appear
at the top of the page:

![](/assets/project-publisher-registered.png)

From this point onwards, the `release.yml` workflow on `pypa/pip-audit` will
be able to mint short-lived API tokens for the PyPI project you've registered
it against.

An OIDC publisher can be registered against multiple PyPI projects (e.g. for a
multi-project repository), and a single PyPI project can have multiple OIDC
publishers (e.g. for multiple workflows on different architectures, OSes).
