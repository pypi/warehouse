---
title: 2FA Enforcement for New User Registrations
description: PyPI requires new users to enable 2FA before performing management actions.
authors:
  - miketheman
date: 2023-08-08
tags:
  - 2fa
  - security
---

## What's changing?

Starting today, **newly registered users must enable 2FA
before they can perform any management actions on PyPI**.
This change comes after we've also added a rule for accounts to have
a verified, _primary_ email address for the same set of management actions.

As a reminder, PyPI has supported adding 2FA since 2019.

<!-- more -->

This change is continuing along the path of enforcing 2FA for all users.
In May of this year we [announced](./2023-05-25-securing-pypi-with-2fa.md)
that by the end of 2023 PyPI will require all users to enable Two-Factor Authentication (2FA).
That post has a wealth of information on what enforcement means,
and how folks can prepare for the change before end of year.

## What are management actions?

Management actions may include any of the following:

- Creating/managing Projects
- Adding/removing API Tokens
- Uploading/removing Releases
- Adding/removing Collaborators
- Requesting/managing [Organizations](./2023-04-23-introducing-pypi-organizations.md)
- Adding/managing [Trusted Publishers](./2023-04-20-introducing-trusted-publishers.md)

This is not an exhaustive list,
but should provide a good idea of the actions we're talking about.

## How does this affect me?

If you only need to browse, download, and install packages from PyPI
then a PyPI account isn't needed so this change doesn't affect you.

If you've already enabled 2FA on your PyPI account,
this change will not affect you.
Thanks for doing your part to keep the Python ecosystem safe!

If you recently registered a new PyPI account,
you are required to enable 2FA before you can perform any management actions.
When attempting to perform a management action,
you may see a red banner flash at the top of the page,
and be redirected to the 2FA setup page for your account.

You will still be able to log in, browse, and download packages without 2FA.
But to perform any management actions, you'll need to enable 2FA.

## Is this the end?

As a reminder, we will enforce the 2FA requirement for all PyPI users
at the end of 2023.

These changes intend to mitigate scenarios like account takeovers,
where an attacker may be able to gain access to a user's account
using only an email and password (either via phishing or credential stuffing).
If a user's email account access is compromised,
and the attacker is able to successfully request a password reset,
the attacker would still need to bypass the 2FA requirement.

The more users using a Two Factor Authentication methods available,
the safer we all are.
Today PyPI offers both [Time-based One-Time Passwords (TOTP)](https://en.wikipedia.org/wiki/Time-based_one-time_password)
and [WebAuthn](https://en.wikipedia.org/wiki/WebAuthn).

Security is a spectrum.
As long as we continue to make incremental progress,
we'll improve the overall posture for **all users** of PyPI.

---

_Mike Fiedler is the PyPI Safety & Security Engineer since 2023._
