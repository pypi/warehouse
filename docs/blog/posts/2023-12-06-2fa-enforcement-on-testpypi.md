---
title: 2FA Enforcement for TestPyPI
description: PyPI requires 2FA for all management actions on TestPyPI.
authors:
  - miketheman
date: 2023-12-06
tags:
  - 2fa
  - security
---

## What's changing?

Starting today, **all users must enable 2FA**
before they can perform any management actions on [TestPyPI](https://test.pypi.org/).

This change is in preparation for the
[scheduled enforcement of 2FA on PyPI](2023-05-25-securing-pypi-with-2fa.md)
at the end of 2023.

<!-- more -->

Previously the PyPI team has announced
[2FA requirement for uploads](2023-06-01-2fa-enforcement-for-upload.md),
[2FA requirement for new user registrations on PyPI](2023-08-08-2fa-enforcement-for-new-users.md),
and now the requirement extends that **all users** on TestPyPI.

## How does this affect me?

If you only need to browse, download, and install packages from TestPyPI
then a TestPyPI account isn't needed so this change does not affect you.

If you've already enabled 2FA on your TestPyPI account,
this change will not affect you.

If you recently registered a new TestPyPI account,
you are required to enable 2FA before you can perform any management actions.
When attempting to perform a management action,
you may see a red banner flash at the top of the page,
and be redirected to the 2FA setup page for your account.
You will still be able to log in, browse, and download packages without 2FA.
But to perform any management actions, you'll need to enable 2FA.

Visit [the 2FA FAQ](https://pypi.org/help/#twofa) for more details.

_Mike Fiedler is the PyPI Safety & Security Engineer since 2023._
