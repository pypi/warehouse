---
title: How AWS Powers PyPI and the PSF
description: A look at how AWS's Open Source Credits Program and Security Sponsorship keep PyPI's infrastructure bill near zero, what changed in 2026, and how the community can help.
authors:
  - jacobcoffee
date: 2026-08-14
tags:
  - infrastructure
  - sustainability
---

Working on infrastructure at the Python Software Foundation (PSF) as the Director of Engineering is a broad job with many hats. Python turns up everywhere. It's in healthcare systems and government agencies, in research labs and classrooms, in one-person side projects and in infrastructure at companies with six-figure headcounts. Somebody is using it to analyze a genome right now and somebody else is using it to automate a spreadsheet they hate arranging by hand. That range has always been the interesting part of the PSF's work, and it's only broadened in the last couple of years as AI continues to pull people from many disciplines into writing Python.

<!-- more -->

At the PSF we support and maintain the infrastructure behind PyPI, Python.org, PyCon US, CPython, and a growing number of community services. The majority of the PSF's infrastructure runs on [AWS](https://aws.amazon.com/opensource/), and nearly all of that bill is covered by credits from the [AWS Open Source Credits Program](https://aws.amazon.com/blogs/opensource/aws-cloud-credits-for-open-source-projects-affirming-our-commitment/).

## The shape of it

PyPI takes over three billion requests a day and about six billion counting file downloads. Package egress runs around 10 petabytes a day.

Almost none of that reaches AWS. Fastly serves it at the edge through their Fast Forward program at a hit ratio just under 99%, so only about one request in seventy makes it to origin. That caching is the core reason our AWS bill is not measured in the millions of dollars a year.

What does reach us is the part that is not cached, including things like user uploads, logins, and account management. That work runs on:

- **Amazon EC2** for the application fleet, almost entirely Graviton at this point. We're [huge fans of Arm-based hardware](https://newsroom.arm.com/blog/how-the-python-software-foundation-future-proofed-its-infrastructure-with-arm) at the PSF!
- **Amazon RDS** for the Postgres database behind Warehouse, which is the application you're looking at when you're on pypi.org.
- **Amazon OpenSearch Service** for project search.
- **Amazon S3** holds ~304 TB of package archives, plus the release history (that nobody ever wants to need).
- **Amazon EKS**, newly stood up, as the target for migrating the whole fleet.

## What changed this year

Our AWS spend is up about 69% comparing July 2026 to July 2025, and 40% across the trailing twelve months. That's new.

For context on how new: last October, Ee Durbin, our former Director of Infrastructure, noted that [PSF's AWS credit usage had grown 25% over eight years](https://pyfound.blogspot.com/2025/10/open-infrastructure-is-not-free-pypi.html) while daily requests went from millions to billions. Eight years of holding that line. 2026 is the first year it broke.

Some of it is simply more of everything. Compute, search, and load balancing all climbed from 30% to 80%, which is the profile of more people and machines using the service. There are certainly more of both. A lot more Python being written, a lot more agents installing packages on someone's behalf, and a lot more CI runs from all the projects those people and agents are creating. Package repositories were designed around the assumption that a human decides to run pip install some number of times a day. That assumption is well past its expiration.

## What we do about it

At the PSF, we take the credits seriously, which means spending real engineering time on utilizing what we have in an optimal way so our usage doesn't increase. Being frugal with the credits entrusted to us is vital.

When a widely used GitHub Action makes requests it doesn't need to make, fixing the Action beats anything we can do on our side. As an example, [the PSF pushed for exactly that in astral-sh/setup-uv](https://github.com/astral-sh/setup-uv/issues/745#issuecomment-3867334064), which is [now live](https://github.com/astral-sh/setup-uv/pull/967) and will shave off usage as people upgrade.

On the PSF side, the EKS migration is the big one. Once we're there, autoscaling lets capacity track demand instead of sitting provisioned for peak at 3 AM (San Francisco time) on a Sunday.

There's just one little (read: major) constraint: Ee left the PSF earlier this year, and I'm currently the only person here working full time on infrastructure. Every item on that list is real and every one is slower than it should be. [The PSF is hiring](https://jobs.pyfound.org/), and that hiring is possible in part because we aren't spending the same money on servers.

That said, hiring has a ceiling set by funding, and PyPI should be considered a supply chain risk until the PSF is able to hire more engineering staff. There is a very large amount of the software industry that sits on top of our services. Feature development, a rising volume of security reports, and day to day maintenance are currently being carried by one and a half full-time employees and one full-time employee on PyPI support requests. If your company installs from PyPI, ask internally about what your organization would be willing to fund. That question can be worth much more coming from inside a company than from the PSF. If you are interested in securing a service agreement with PyPI, please [fill out our survey](https://www.surveymonkey.com/r/H53HHSS).

## What the funding actually bought

AWS has backed PyPI two different ways, and both are worth outlining.

A very exciting investment was made in 2023, when AWS became [PyPI's inaugural Security Sponsor](https://blog.pypi.org/posts/2023-05-09-announcing-pypi-safety-and-security-engr-role/), putting $144,000 into creating the PyPI Safety & Security Engineer role. That role is now funded by [Alpha-Omega](http://alpha-omega.dev/), and it's the reason malware comes down off PyPI in hours instead of whenever a volunteer has a spare moment. This investment also followed a pattern AWS had already established, having helped fund the rewrite, internationalization, and 2FA support for PyPI.

The credits do something quieter. They hold the infrastructure bill near zero, which means the PSF's general fund goes to employees, PyCon US, and other operational costs instead of servers. That's what pays for support staff handling the account recovery and project ownership requests that arrive every single day, and what makes it possible to ship things like Trusted Publishing, digital attestations, and organization accounts--instead of just keeping the lights on.

PyPI is free to use and will stay free to use at reasonable levels. Core publishing and installing stay free, permanently. What we are doing is building out real benefits for Organization accounts, and looking at sensible rate limits for the heaviest consumers at the top of the curve.

Which is exactly why in-kind support isn't just a line item to us. A sponsor choosing not to renew would mean an emergency migration or tens of thousands of dollars a month, either of which comes straight out of the work above. AWS has renewed every year since 2018, and the predictability of that is worth as much as the amount. The same goes for Fastly, Google Cloud, Datadog, Sentry, Depot, and PagerDuty, who carry other parts of this mountain of infrastructure.

## How you can help

Four things, in order of how much they matter:

**Cache your installs.** If your CI pulls from PyPI on every run with a cold cache, you're a meaningful part of the graph. The PSF uses Docker cache mounts and pip's cache on our own builds, and npm and apt caching too, because it's faster for us and cheaper for everyone. [Free package repositories aren't a limitless resource](https://pyfound.blogspot.com/2025/10/open-infrastructure-is-not-free-pypi.html), and the fix is usually about six lines of config.

[**Sign up for a PyPI Organization**](https://pypi.org/manage/organizations/) if your company publishes to PyPI. Recurring revenue from Organizations is the most sustainable funding base we have, and Community organizations remain free. Look forward to announcements about future features for PyPI organization accounts soon.

**Interested in a PyPI service agreement?** Enhanced options like annual bulk seat purchases, higher project size limits, and prioritized support are available. The revenue helps fund the broader PyPI ecosystem while giving your organization benefits at scale. Fill out [our service agreement interest survey](https://www.surveymonkey.com/r/H53HHSS) and we'll follow up.

**Ask your infrastructure vendors for multi-year commitments with open source foundations.** Annual renewal cycles carry real risk for projects like ours. The five-year agreement the PSF signed with Fastly in 2024 is a sustainable model, and we'd like more of them.

The [open letter the PSF co-signed last year](https://openssf.org/blog/2025/09/23/open-infrastructure-is-not-free-a-joint-statement-on-sustainable-stewardship/) called this a critical inflection point rather than a crisis. A year on, with our first real break in eight years of flat infrastructure costs, that still reads about right.

A big thanks to Mila Zhou and the AWS Open Source team, who have made the credits process about as painless as an annual funding renewal can be, and to everyone at AWS who's kept this program going for so long. PyPI would look very different without it.
