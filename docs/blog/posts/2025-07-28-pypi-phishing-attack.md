---
title: PyPI Users Email Phishing Attack
description: PyPI Users are receiving emails detailing them to log in to a fake PyPI site.
authors:
  - miketheman
date: 2025-07-28
tags:
  - security
  - transparency
---
(Ongoing, preliminary report)

PyPI has not been hacked, but users are being targeted by a phishing attack
that attempts to trick them into logging in to a fake PyPI site.

Over the past few days, users who have published projects on PyPI
with their email in package metadata may have received an email titled:

> [PyPI] Email verification

from the email address `noreply@pypj.org`.

Note the lowercase `j` in the domain name,
which is not the official PyPI domain, `pypi.org`.

This is not a security breach of PyPI itself,
but rather a phishing attempt that exploits the trust users have in PyPI.

<!-- more -->

The email instructs users to follow a link to verify their email address,
which leads to a phishing site that looks like PyPI but is not the official site.

The user is prompted to log in, and the requests are passed back to PyPI, which may lead to the user
believing they have logged in to PyPI, but in reality, they have provided their credentials
to the phishing site.

PyPI Admins are looking into a few methods of handling this attack,
and want to make sure users are aware of the phishing attempt
while we investigate different options.

There is currently a banner on the PyPI homepage
to warn users about this phishing attempt.

Always inspect the URL in the browser before logging in.

We are also waiting for CDN providers and name registrars
to respond to the trademark and abuse notifications
we have sent them regarding the phishing site.

If you have received this email, do not click on any links or provide any information.
Instead, delete the email immediately.

If you have already clicked on the link and provided your credentials,
we recommend changing your password on PyPI immediately.
Inspect your account's Security History for anything unexpected.
