---
title: "Incident Report: User Account Takeover"
description: A PyPI user had their account taken over
authors:
  - miketheman
date: 2023-12-04
tags:
  - 2fa
  - security
  - transparency
---

# Incident Report: User Account Takeover

## What happened?

A PyPI user's account was taken over and used to remove the user's ownership of 4 projects.
This was not a malfunction of PyPI or using any vulnerability,
rather the user's account was not sufficiently protected against account takeover.

The attacker added themselves as a collaborator to these projects,
and removed the original owner. None of the projects had any modifications made to them other than ownership changes.

<!-- more -->

After the attacker completed ownership changes, they deleted the user's account.

PyPI Admins were informed by the user via email,
blocked the attacker's access to the account,
and restored the user's ownership of their projects.

No further compromise was made, and **existing packages were not modified**.

Read on for more details.

## Timeline

_all times are in UTC_

System timings are from project ownership changes and email notifications.
When a user's account is deleted, the account's data is removed immediately,
thus we do not have timing of when the attacker gained access to `meisnate12`'s account.

**Date: 2023-11-22**

- 08:42:33 new user account `dvolk` created

_(this is the first of 4 packages, only describing one here)_

- 08:44:55 `meisnate12` account invites `dvolk` to be a collaborator on `arrapi`
- 08:47:25 `dvolk` accepts the invitation
- 08:47:35 `dvolk` removes `meisnate12` as a collaborator on `arrapi`

_(repeated for `tmdbapis`, `nagerapi`, `pmmutils`)_

- 08:50:27 `meisnate12` account is deleted

No further actions by `dvolk` were observed after this point.

- 14:33, admin@pypi.org receives an email
  from the address associated with `meinstate12`'s account:

    > I was removed as the owner of arrapi, tmdbapis, nagerapi, and pmmutils.
    > Then my account was deleted so I have no way to log in anymore.
    > My username is meisnate12. What are my next steps here.

- 14:46 A PyPI Admin responds with:

    > Thanks for the report. We've frozen the account in question while we look into this.

- 14:44 PyPI Admins discuss options in PyPI Admins Slack channel
  with two other PyPI Admins
- 14:46 A PyPI Admin disables the `dvolk` account

After investigation, PyPI Admins determine that the account was compromised,
but the attacker did not change any of the projects' data.

We decide the correct course of action is to manually restore the deleted user account,
and restore the user's ownership of their projects.

- 15:53 PyPI Admins close the incident

## What can we learn from this incident and improve?

### An ounce of prevention is worth a pound of cure

We integrate with HaveIBeenPwned to [check a user's password](https://github.com/pypi/warehouse/blob/6d4b6a3d35e0ce0d0b6d4e6484808e1a9f6e4852/warehouse/accounts/forms.py#L389-L401)
against their service on every login.
Unfortunately, the password in question had not previously surfaced
in a breach that HaveIBeenPwned knows about, so this didn't prevent the attack.

One of the best tools we have to date to prevent account takeover 
is [Two-Factor Authentication](https://pypi.org/help/#twofa)
(2FA, or MFA - multifactor auth).

If this user account had 2FA enabled,
the attacker would not have been able to take over the account
without access to the user's second factor (TOTP app, WebAuthN device, or passkeys).

We have already taken steps to [ratchet down usage of PyPI without 2FA enabled](https://github.com/pypi/warehouse/issues/14010).

**This encouragement will turn into [enforcement at the end of 2023](https://blog.pypi.org/posts/2023-05-25-securing-pypi-with-2fa/).**

We still have a use case where an infrequent user of PyPI,
with an account created long before 2FA was available,
is still able to log into their account without 2FA, in order to enroll a 2FA device.
[Read more about this issue](https://github.com/pypi/warehouse/issues/11850)
and some ideas for resolution.

### Deleting things can have unintended consequences

When a user account is deleted, all the account's data is removed.
We have a mechanism in place today that prevents a user account from being deleted
if they are the sole owner of any projects, to prevent orphaning projects.

In this case, the attacker was able to remove the user's ownership of their projects,
and then delete the account.

We have previously entertained ideas on how to prevent full deletions
without PyPI Admin intervention, but have yet to settle on a solution.
See [this tracking issue](https://github.com/pypi/warehouse/issues/6091) and for more details.
It's not as simple as it sounds.

Even if we continue to delete resources immediately,
we should entertain what we can do to preserve some of the details we might need
to investigate further.
[This issue](https://github.com/pypi/warehouse/issues/6451) tracks that effort.

### If you see something, say something

When collaborators are added or removed to a project,
or an account is deleted, we email the address on file.

We were informed of the incident by the impacted user,
who still had access to the email account associated with their PyPI username.

Here are a few things you can do to help protect your PyPI account: 

- **[Add 2FA now](https://pypi.org/help/#twofa)**.
- Use a unique and sufficiently complex password for your PyPI account.
- Keep your account [email addresses up to date](https://pypi.org/help/#verified-email),
  and ensure you maintain access.
- If you receive an email from PyPI that you did not expect,
  please contact us via email <mailto:security@pypi.org>

This user's diligence in reporting the incident to us helped prevent further compromise.
