---
title: "Prohibiting inbox.ru email domain registrations"
description: We have prohibited new registrations of accounts using inbox.ru email domains.
authors:
  - miketheman
date: 2025-07-15
tags:
  - security
  - transparency
---

A recent spam campaign against PyPI has prompted an administrative action,
preventing using the `inbox.ru` email domain.
This includes new registrations as well as adding as additional addresses.

The campaign created over 250 new user accounts,
publishing over 1,500 new projects on PyPI,
leading to end-user confusion, abuse of resources, and potential security issues.

All relevant projects have been removed from PyPI, and accounts have been disabled.

<!-- more -->

## Background

Users are welcome to use any valid email address to register a new account,
however this delegates some of the responsibility of account security
to the email provider.

PyPI uses the [`disposable-email-domains`](https://github.com/disposable-email-domains/disposable-email-domains)
list to prevent new registrations using disposable email addresses,
and PyPI maintains its own internal block list,
updated by PyPI Admins in response to discovering abuse.

See a [previous post](./2024-06-16-prohibiting-msn-emails.md)
for a previous case of prohibiting a popular email domain provider.

## Timeline

Here's a timeline of the events I was able to put together

- 2025-06-09 first user account created, verified, 2FA set up, API Token provisioned
- 2025-06-11 46 more user accounts created over the course of 3 hours
- 2025-06-24 207 more user accounts created over the course of 4 hours
- 2025-06-29 New projects are created a file uploads start

Here's a table showing how many projects were published on each date:

| Date       | Number of Projects |
|------------|--------------------|
| 2025-06-26 | 9                  |
| 2025-06-27 | 295                |
| 2025-06-28 | 39                 |
| 2025-06-29 | 119                |
| 2025-06-30 | 740                |
| 2025-07-01 | 249                |
| 2025-07-02 | 46                 |
| 2025-07-10 | 16                 |
| 2025-07-11 | 12                 |

Total: 1,525

## Details

The projects were created with a variety of names with no code inside,
so this wasn't a case of malware, but possibly using popular projects' entrypoints
(often a command line execution interface),
as those are not required to be the same as the **project name** on PyPI.

This pattern seems to be consistent with setting up a large number of accounts,
confirming access, and then executing a large-scale "attack".
This may have proven to be a "dry run" for a future attack,
depending on the success of this campaign.

PyPI Admins were alerted to this condition initially on 2025-07-08
from a user telling us that they were working with a Large Language Model (Sonnet 4)
recommending installing a project that did not exist - aka ["slopsquatting"](https://en.wikipedia.org/wiki/Slopsquatting).
This is a good reminder that users should always verify the project names they are installing,
and not copy & paste the name of a project suggested by a third party,
such as an AI model or random person on the internet.

Thanks again to users who are vigilant and report issues to us!

Hopefully we can reverse this decision at some point in the future when
we have more confidence in this email provider's ability to prevent abuse.
If you work at this provider, please email us at [security@pypi.org](mailto:security@pypi.org)
to discuss this decision.
