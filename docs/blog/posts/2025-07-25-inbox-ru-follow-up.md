---
title: "inbox.ru Domain Prohibition Follow-up"
description: A follow-up to the inbox.ru email domain prohibition.
authors:
  - miketheman
date: 2025-07-25
tags:
  - security
  - transparency
---

A follow-up to the [previous post](./2025-06-15-prohibiting-inbox-ru-emails.md).

We have since learned that the campaign was orchestrated
by the company that owns the `inbox.ru` email domain,
and not by a malicious third party as we initially suspected.

<!-- more -->

Following the previous post,
a representative of the parent company for `inbox.ru` reached out
to PyPI Admins to discuss the situation.
They expressed their desire to resolve the issue, and reinstate the ability
for their users to register for PyPI accounts with email addresses from the `inbox.ru` domain.

They confirmed that the user account registrations on PyPI originated from an internal security team,
"to prevent possible abuse of external libraries for attacks on our systems".

They also confirmed that they have held staff meetings and have decided to abandon this practice,
and develop alternate methods for detection and prevention of abuse,
and have apologized for the incident.

As such, we have re-enabled the ability for users to register accounts
using the `inbox.ru` email domain,
and to add `inbox.ru` email addresses to existing accounts.

We will continue to monitor the situation,
and if we see any further abuse from this domain or others,
we will take appropriate action to protect PyPI users and resources.
