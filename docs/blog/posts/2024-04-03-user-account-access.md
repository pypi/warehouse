---
title: "Incident Report: Unauthorized User Accounts Access"
description: An attack on PyPI user accounts starting on March 31st, 2024.
authors:
  - miketheman
date: 2024-04-03
tags:
  - 2fa
  - security
  - transparency
---

On Sunday, March 31st, 2024, PyPI Admins received emails
about unexpected account activity from PyPI users.
Users received notifications from PyPI that they had
enrolled in two-factor authentication (2FA).
These users claimed that they had not done so themselves.

PyPI Admins have **not found any evidence** of existing package tampering,
or any other malicious activity beyond unauthorized account access and modification.

The main actions post-investigation taken were:

* affected accounts were frozen for further investigation
* email re-verification was required for all accounts not yet enabled in 2FA

Read on for a summary of what happened, how we responded, and what's next.

<!-- more -->

_All times are in Eastern Time (UTC-4), and some are approximated for clarity._

## What Happened

### Sunday, March 31st, 2024

It was a weekend morning.

* 06:20: PyPI Admins receive an influx of emails from users.

These users were responding to an automated notification from PyPI
that they had enrolled in two-factor authentication (2FA).

**As a reminder, [PyPI requires all users](./2024-01-01-2fa-enforced.md) to enable 2FA.**

Users stated they had not enrolled in 2FA themselves.
The accounts in question had not previously enrolled in any form of 2FA,
and the users were surprised by these notifications.

Emails of this nature trickled in over the course of the day,
as users read their email and notice the activity.

* 08:00:  A volunteer PyPI Admin saw these notifications and began to investigate.

They found some traffic patterns used for the attack.
The admin then reached out to the rest of the team to discuss their findings,
and to take action on the accounts that were affected.

The main action taken was to immediately freeze any suspicious accounts,
as this is completely reversible and would prevent any further damage
to the known compromised accounts or projects they have access to.

~120 user accounts were frozen due to the analysis of the situation,
based on their characteristics and the traffic patterns observed.
_(A precise count was not recorded as actions were taken in real-time.)_

PyPI Admins began work on a feature which would require re-verification
of email addresses for all accounts not yet enabled in 2FA,
before any other account action can be taken (including enabling 2FA).

* 11:00: the volunteer admin had to step away from the computer for the remainder of the day.

Investigation continues on Monday.

### Monday, April 1st, 2024

Monday morning, investigations continue.

* 08:00: an additional ~54 accounts were frozen based on similar criteria, with better filters

Another investigation to determine if any packages had been tampered with began.
**No evidence of package tampering was found** associated with any of these accounts.

PyPI Admins completed the new feature to now require email address
re-verification for any account that has not yet enabled 2FA.

* 12:20: Account re-verification change went live.

Once the change was in place, PyPI Admins took another action -
invalidated any existing email verifications for accounts **without 2FA enabled**.
This was done to prevent any unauthorized access to accounts that may have been compromised.
Now, if a user who has not enrolled in 2FA logs in,
they will be required to re-verify their email address,
prior to enrollment in 2FA.
This process ensures that someone logging into a pre-existing account
without 2FA controls the password _and_ email address associated with the account.

* 12:30: Email invalidation applied to 370k (56%) email addresses.

The rationale was that these accounts were at risk of unauthorized access,
and this was a proactive measure to prevent further damage.

## Summary

This event has similar characteristics to a
[credential stuffing](https://attack.mitre.org/techniques/T1110/004/) attack,
where attackers use credentials found via other service's leaks or incidents
to attempt to log in to accounts on PyPI.

For the time frame in question we did not observe a higher-than-normal
rate of requests to the PyPI login endpoint.
Authentication rate limits did not show any out-of-the-ordinary activity.

This an attack that 2FA is designed to protect against,
as even if the attackers have the correct username and password,
they would still need to provide a second factor to gain access to the account.

PyPI disallows the use of compromised passwords,
commonly used in credential stuffing attacks,
by [integrating](https://github.com/pypi/warehouse/blob/d16fc21b0d5a57409740f5ebd780ea446df6d95c/warehouse/accounts/services.py#L769-L825)
with the [Have I Been Pwned](https://haveibeenpwned.com/) [API](https://haveibeenpwned.com/API/v3)
to check for compromised passwords on login, but there was no evidence
that these passwords were compromised in known data leaks on that platform
at the time of login.

All PyPI users should take precautions to secure their PyPI account
and associated projects, including, but not only:

* Use a unique password on PyPI
* Verify your email address, add a secondary email address (optional)
* Enable 2FA on your account. **Save your recovery codes somewhere safe!**
* Review your packages for any unauthorized changes
* Review collaborators on your projects

For any users who have been affected by this incident,
and cannot obtain access to their accounts with email re-verification,
Please read the [FAQ on account recovery](https://pypi.org/help/#account-recovery).

We will continue to monitor the situation and take further action as needed.

---

_This analysis, and my role, is made possible with the support from
[Amazon Web Services Open Source](https://aws.amazon.com/opensource/),
[Georgetown CSET](https://cset.georgetown.edu/),
the [PSF](https://www.python.org/psf/) and their sponsors._
