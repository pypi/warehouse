---
title: Managing Your Account
---

# Managing Your Account

!!! warning "Received a security notification or noticed something suspicious?"
    See [handling security alerts and suspicious account activity](security-alerts.md) for guidance on how to secure your account.

## Account creation and acceptable use

By creating a PyPI account, you agree to the [PyPI Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/). All users are expected to adhere to the following principles:

* **Do not use PyPI for any illegal or harmful activities.** This includes hosting packages that violate laws or promote harmful behavior.  
* **Do not impersonate others.** Do not register accounts in the name of other individuals or organizations or post their private information without explicit consent.  
* **Be respectful.** Abusive, discriminatory, or harassing language and behavior are not welcome on PyPI.  
* **Do not post spam or distribute malware.** PyPI is for distributing Python packages, not for unsolicited advertising or malicious software.  
* **Do not use PyPI to conduct security research.**

For a complete set of guidelines, please read the full [Acceptable Use Policy](https://pypi.org/policy/acceptable-use-policy/).

## Account registration limits

To reduce spam and automated abuse, PyPI applies some limits when creating a new account:

* **Disposable email addresses are rejected.** PyPI checks the reputation of the email domain used during registration, and will reject signups that use a known disposable or temporary email provider. Use a persistent email address you control to register.
* **Registration attempts are rate limited by network.** If too many accounts are registered from the same network (IP address) in a short period, further registration attempts from that network will be temporarily blocked. If you see a "Too many registration attempts" error, wait and try again later.
* **New registrations may be disabled entirely during an attack.** If PyPI administrators are dealing with a large-scale spam or malware campaign, they can temporarily disable new user or new project registration site-wide to contain the threat, independently of the per-account limits above. See [Security and Internals](../about/security-and-internals.md#pypi-security-features) for more information, and the [status page](https://status.python.org/) for updates during such an event.

## Email address verification

Currently, PyPI requires a verified email address to perform the following operations:

* Register a new project  
* Upload a new version or file

The list of activities that require a verified email address is likely to grow over time.

This policy will allow us to enforce a key policy of [PEP 541](https://www.python.org/dev/peps/pep-0541/) regarding maintainer reachability. It also reduces the viability of spam attacks to create many accounts in an automated fashion.

You can manage your account's email addresses in your [account settings](https://pypi.org/manage/account/). This also allows for sending a new confirmation email for users who signed up in the past, before we began enforcing this policy.

## Password confirmation for sensitive actions

PyPI asks you to confirm your password before performing a *sensitive action*. Sensitive actions include:

* Adding or removing project maintainers  
* Deleting distributions  
* Generating API tokens  
* Setting up two-factor authentication

You'll only have to re-confirm your password if it's been more than an hour since you last confirmed it.

**We strongly recommend you only perform such actions on your personal, password-protected computer.**

## API tokens for authentication

API tokens are used to authenticate when **uploading packages** to PyPI.

You can create a token for an entire PyPI account, in which case, the token will work for all projects associated with that account. Alternatively, you can limit a token's scope to a specific project.

When using an API token from a CI provider, we recommend scoping the token down to the minimum necessary projects.

**If you are publishing to PyPI from a CI provider that supports [Trusted Publishing](../trusted-publishers/index.md), we strongly recommend using Trusted Publishing instead.**

To make an API token:

* [Verify your email address](https://pypi.org/help/#verified-email) (check your [account settings](https://pypi.org/manage/account/))  
* In your [account settings](https://pypi.org/manage/account/), go to the API tokens section and select "Add API token"

To use an API token:

* Set your username to `__token__`  
* Set your password to the token value, including the `pypi-` prefix

Where you edit or add these values will depend on your individual use case. For example, some users may need to edit [their `.pypirc` file](https://packaging.python.org/guides/distributing-packages-using-setuptools/#create-an-account), while others may need to update their CI configuration file (e.g. [`.travis.yml` if you are using Travis](https://docs.travis-ci.com/user/deployment/pypi/)).

Advanced users may wish to inspect their token by decoding it with base64, and checking the output against the unique identifier displayed on PyPI.

## Two-factor authentication (2FA)

As of early 2024, 2FA is mandatory for all accounts that maintain any project or organization on PyPI. See [Two-factor authentication](two-factor-authentication.md) for more information.

## Changing your PyPI username

PyPI does not currently support changing your username directly.

However, you can achieve the same result by following these steps:

1. Create a new PyPI account with your desired username  
2. Add the new account as a maintainer to all the projects owned by your old account  
3. Once you have confirmed the new account has the correct permissions, you can delete the old account

For more information see [Managing project owners](../project-management/managing-owners.md).

## Account recovery

See [Account recovery](account-recovery.md) for information on how to recover your account.
