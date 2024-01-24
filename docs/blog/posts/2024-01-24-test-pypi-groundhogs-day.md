---
title: Resetting TestPyPI's state
description: The database for test.pypi.org will be reset Friday February 2, 2024.
authors:
  - ewdurbin
date: 2024-01-24
tags:
  - testpypi
  - groundhogs
---

## What is happening?

On February 2, 2024, and each following February 2nd,
the state of [TestPyPI](https://test.pypi.org) will be reset completely.

This includes **all** user accounts, projects, releases, and release files
published to TestPyPI.

In order to use TestPyPI all past and new users will need to
create a new account, enable 2FA, generate new API tokens,
and update any tools to use their new credentials
or configure []().

Associations between usernames and projects will not be retained,
so new projects will need to be created via the standard tooling.

## Why is this happening?

As [Groundhog Day](https://en.wikipedia.org/wiki/Groundhog_Day) approaches,
the PyPI Administrators have taken time to reflect on the intended purpose of
[TestPyPI](https://test.pypi.org) and how the current state has diverged
from that purpose.

<!-- more -->

TestPyPI is _not_ intended to be a reliable long-term place for publishing
and particularly not for installing Python packages. It is intended to be a
sandbox for the community to test their publication tooling and preview the
result.

Additionally TestPyPI itself has grown significantly to the point that it
needlessly consumes substantial resources.

## What will change?

We will introduce a requirement that all project names and usernames
on TestPyPI will all contain a required prefix of `testpypi-YYYY-`.
This is intended to disambiguate between the things hosted on TestPyPI
and "real" PyPI, indicating the temporal nature of the accounts and projects.

For project names this will be transparently applied internal to the codebase
so that publishing tools will "just work"
without having to modify configurations like `pyproject.toml` when testing.

Presentation on the website will automatically redirect to the prefixed
name, but in order to _install_ from test.pypi.org users _must_ use the prefix.

This will hopefully reduce confusion between the two services and mitigate
impersonation and unintended usage of TestPyPI due to misconfiguration.

## Why Grounhog Day?

This is a reference to the 1993 movie "Groundhog Day" which tells the story of
a bitter news anchor that becomes stuck in a time loop, repeating February 2nd
until taking time to be learn, improve, and better himself.
