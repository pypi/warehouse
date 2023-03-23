---
title: Creating a PyPI project through OIDC
---

{{ preview('oidc-publishing') }}

# Creating a PyPI project through OIDC

OIDC publishing is not just for pre-existing PyPI projects: you can also use
it to *create* a PyPI project!

This again reduces the number of steps needed to set up a fully automated PyPI
publishing workflow: rather than having to manually upload a first release
to "prime" the project on PyPI, you can configure a "pending" OIDC publisher
that will *create* the project when used for the first time. "Pending"
publishers are converted into "normal" publishers on first use, meaning that
no further configuration is required.

The process for configuring a "pending" publisher are similar to those for
a normal publisher, except that the page is under your account sidebar
instead of any project's sidebar (since the project doesn't exist yet):

![](/assets/publishing-link.png)

Clicking on "publishing" will bring you to a familiar looking form:

![](/assets/pending-publisher-form.png)

This form behaves the same as with a "normal" OIDC publisher, except that you
also need to provide the name of the PyPI project that will be created.

For example, if you have a repository at `https://github.com/example/awesome`
with a release workflow at `release.yml` and you'd like to publish it to
PyPI as `pyawesome`, you'd do the following:

![](/assets/pending-publisher-form-filled.png)

Clicking "Add" will register the "pending" publisher, and show it to you:

![](/assets/pending-publisher-registered.png)

From this point on, the "pending" publisher can be used exactly like a
"normal" OIDC publisher. Using it will convert it into a "normal" OIDC
publisher.
