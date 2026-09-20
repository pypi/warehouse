---
title: Publishing to PyPI
---

# Publishing to PyPI

## Packaging your project

To publish a project to PyPI, you first need to package it correctly. This involves creating a pyproject.toml file that contains metadata about your package.

For instructions on how to package your Python project, please refer to the [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/section-build-and-publish/).

## Publishing your project with Trusted Publishing (recommended)

[Trusted Publishing](../trusted-publishers/index.md) is the recommended method for uploading packages to PyPI. It uses OpenID Connect (OIDC) to establish a secure connection between PyPI and a trusted third-party service, such as a CI/CD provider. This eliminates the need to store and manage API tokens or passwords, significantly reducing the risk of your credentials being compromised.

For an existing project, open ["Your projects"](https://pypi.org/manage/projects/), click "Manage" next to the project, and select "Publishing" in the sidebar. For detailed instructions, please see [adding a trusted publisher](../trusted-publishers/adding-a-publisher.md).

If you're creating a new project, you can configure a "pending" Trusted Publisher from your account settings instead. For detailed instructions, please see [creating a PyPI project with a trusted publisher](../trusted-publishers/creating-a-project-through-oidc.md).

## Using an API token

API tokens are used to authenticate when uploading packages to PyPI. 

!!! warning "Use Trusted Publishing where possible"
    If you are publishing to PyPI from a CI provider that supports [Trusted Publishing](../trusted-publishers/index.md), we strongly recommend using Trusted Publishing instead of managing API tokens.

You can create a token for an entire PyPI account, in which case, the token will work for all projects associated with that account. Alternatively, you can limit a token's scope to a specific project.

When using an API token from a CI provider, we recommend scoping the token down to the minimum necessary projects.

To make an API token:

* [Verify your email address](../your-account/managing-your-account.md#email-address-verification) (check your [account settings](https://pypi.org/manage/account/))
* In your [account settings](https://pypi.org/manage/account/), go to the API tokens section and select "Add API token"

To use an API token:

* Set your username to `__token__`
* Set your password to the token value, including the `pypi-` prefix

Where you edit or add these values will depend on your individual use case. For example, some users may need to edit [their `.pypirc` file](https://packaging.python.org/guides/distributing-packages-using-setuptools/#create-an-account), while others may need to update their CI configuration file (e.g. [`.travis.yml` if you are using Travis](https://docs.travis-ci.com/user/deployment/pypi/)).

[Twine](https://twine.readthedocs.io/) also supports other ways to provide credentials, including keyring integration. See the [Twine authentication documentation](https://twine.readthedocs.io/en/stable/#authentication) for details.

Advanced users may wish to inspect their token by decoding it with base64, and checking the output against the unique identifier displayed on PyPI.

If you run into issues authenticating with an API token, see [Troubleshooting](troubleshooting.md#why-am-i-getting-an-invalid-or-non-existent-authentication-information-error-when-uploading-files).
