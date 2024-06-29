---
title: "Prohibiting Outlook email domains"
description: We have prohibited new registrations of accounts using Outlook email domains.
authors:
  - ewdurbin
date: 2024-06-16T00:00:00
tags:
  - security
  - transparency
---

In response to ongoing mass bot account registrations, Outlook domains
`outlook.com` and `hotmail.com` have been prohibited from
new associations with PyPI accounts.
This includes new registrations as well as adding as additional addresses.

<!-- more -->

If you have been following PyPI here on our blog, or in the news,
it should come as no surprise that malware and abuse has been part of our
day-to-day concerns for many years.

In response we have added more and more layers of protection to our systems
which dissuade abuse. These escalations have included
improved bot deterrence via captcha,
requiring verified email addresses to perform actions with new accounts,
changes to our 2FA on-boarding process,
as well as ratelimits and other "basic" methods.

One of the most impactful mechanisms we currently have is prohibiting
known "throw-away" email domains from creating accounts on the index.
We currently use the [disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) 
list as well as our own internal list to block registration with
－or association of －
such domains for PyPI accounts.

In the last year as malware campaigns have become more and more sophisticated
and coordinated, these prohibitions have proven very impactful with one major
exception.

In a campaign today which included over 160 projects *and* associated new user
registrations, the accounts were registered using
`outlook.com` and `hotmail.com`
email addresses.
Past campaigns of similar scale have had similar characteristics.

This indicates to us that the Outlook email services are falling short of other
major email providers in prevention of automated, bot, and bulk signups for new
accounts.

Past campaigns have shown similar characteristics, those who hope to circumvent
our protections tend to use or pay for bot farms which are able to bypass
automation detection of Outlook email accounts in order to establish accounts
on PyPI with ostensibly trustworthy email addresses.

We hope that this change does not need to be permanent,
given our current capacity for response and tooling it is the next step that we
currently have.
