---
title: Publishing to PyPI
---

# Publishing to PyPI

## Packaging your project

To publish a project to PyPI, you first need to package it correctly. This involves creating a pyproject.toml file that contains metadata about your package.

For instructions on how to package your Python project, please refer to the [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/section-build-and-publish/).

## Publishing your project with Trusted Publishing (recommended)

[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) is the recommended method for uploading packages to PyPI. It uses OpenID Connect (OIDC) to establish a secure connection between PyPI and a trusted third-party service, such as a CI/CD provider. This eliminates the need to store and manage API tokens or passwords, significantly reducing the risk of your credentials being compromised.

You can configure Trusted Publishing for your project in your PyPI account settings. For detailed instructions, please see [adding a trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).

## Using an API token

API tokens are used to authenticate when uploading packages to PyPI. 

!!! warning "Use Trusted Publishing where possible"
    If you are publishing to PyPI from a CI provider that supports [Trusted Publishing](https://pypi.org/help/#trusted-publishers), we strongly recommend using Trusted Publishing instead of managing API tokens.

You can create a token for an entire PyPI account, in which case, the token will work for all projects associated with that account. Alternatively, you can limit a token's scope to a specific project.

When using an API token from a CI provider, we recommend scoping the token down to the minimum necessary projects.

To make an API token:

-   [Verify your email address](https://pypi.org/help/#verified-email) (check your [account settings](https://pypi.org/manage/account/))
    
-   In your [account settings](https://pypi.org/manage/account/), go to the API tokens section and select "Add API token"
    
To use an API token:

-   Set your username to `__token__`
    
-   Set your password to the token value, including the `pypi-` prefix

Where you edit or add these values will depend on your individual use case. For example, some users may need to edit [their .pypirc file](https://packaging.python.org/guides/distributing-packages-using-setuptools/#create-an-account), while others may need to update their CI configuration file (e.g. [.travis.yml if you are using Travis](https://docs.travis-ci.com/user/deployment/pypi/)).

[Twine](https://twine.readthedocs.io/) also supports other ways to provide credentials, including keyring integration. See the [Twine authentication documentation](https://twine.readthedocs.io/en/stable/#authentication) for details.

Advanced users may wish to inspect their token by decoding it with base64, and checking the output against the unique identifier displayed on PyPI.

### Troubleshooting API token issues

"Invalid or non-existent authentication information." error when uploading files

1.  Ensure that your API token is valid and has not been revoked (see below)
    
2.  Ensure that your API token is [properly formatted](https://pypi.org/help/#apitoken) and does not contain any trailing characters such as newlines.
    
3.  Ensure that the username you are using is `__token__`.
    

Remember that PyPI and TestPyPI each require you to create an account, so your credentials may be different.

If you're using Windows and trying to paste your token in the Command Prompt or PowerShell, note that Ctrl-V and Shift+Insert won't work. Instead, you can use "Edit > Paste" from the window menu, or enable "Use Ctrl+Shift+C/V as Copy/Paste" in "Properties". This is a [known issue](https://bugs.python.org/issue37426) with Python's getpass module.

#### Compromised API token

If you receive a notification that your API token has been compromised, it means a token associated with your account was found on a public website. For your protection, the exposed token was automatically revoked by PyPI.

Before generating a new token, you should:

-   Review the notification email and investigate how the token may have been exposed
    
-   Review your account's security history for any unauthorized actions 
    
-   Contact the PyPI admins at [admin@pypi.org](mailto:admin@pypi.org) if any unauthorized actions have occurred
    
-   Reset your password
