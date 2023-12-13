---
title: 2FA Requirement for PyPI begins 2024-01-01
description: PyPI will require 2FA for all users on Jan 1, 2024.
authors:
  - miketheman
date: 2023-12-13
tags:
  - 2fa
  - security
---

## What's changing?

Starting January 1, 2024, **all users must [enable 2FA](https://pypi.org/help/#twofa)**
for their PyPI accounts.

PyPI has been on the path of being a fully Two-factor Authenticated service a reality,
which [began in 2019](https://pyfound.blogspot.com/2019/03/commencing-security-accessibility-and.html).
Read more about some of the steps taken in recent months:

<!-- more -->

- [Securing PyPI accounts via Two-Factor Authentication](2023-05-25-securing-pypi-with-2fa.md)
- [2FA Enforcement for New User Registrations](2023-08-08-2fa-enforcement-for-new-users.md)
- [2FA Enforcement for upload.pypi.org](2023-06-01-2fa-enforcement-for-upload.md)
- [2FA Enforcement for TestPyPI](2023-12-06-2fa-enforcement-on-testpypi.md)

PyPI Admins will activate the requirement for PyPI.org on Jan 1, 2024[^1]
for all users, all projects.
Read more in [the 2FA FAQ](https://pypi.org/help/#twofa).

## How does this affect me?

- If you only need to browse, download, and install packages from PyPI
then a PyPI account isn't needed so this change does not affect you.
- If you've already enabled 2FA on your PyPI account,
this change will not affect you.
- If you do not have a form of 2FA enabled on your PyPI account,
you will be required to enable 2FA before you can perform any management actions,
- or upload files to PyPI.

When attempting to perform a management action,
you may see a red banner flash at the top of the page,
and be redirected to the 2FA setup page for your account.
You will still be able to log in, browse, and download packages without 2FA.
But to perform any management actions, you'll need to enable 2FA.

When uploading a file, you may receive an error message that contains a message
that contains: `an API Token or Trusted Publisher must be used to upload`.
You may also receive an email notice with a similar message,
which will include a link to [API Tokens help](https://pypi.org/help/#apitoken).

If you are no longer responsible for a PyPI account that publishes packages,
please **forward these details** along to someone who does,
so they are not caught unaware.

Thank you for helping to keep the Python packaging ecosystem secure!

[^1]: Exact timing is not specified, switch will happen during US Eastern daytime.
