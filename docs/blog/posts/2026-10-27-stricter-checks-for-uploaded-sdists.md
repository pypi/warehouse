---
title: Stricter checks for uploaded source distributions on PyPI
description: >
  PyPI has added and will continue adding more checks against
  uploaded source distributions, as part of a larger effort to
  reduce archive differentials in the Python packaging ecosystem
  and conform with Python packaging standards.
authors:
  - woodruffw
date: 2026-10-27
tags:
  - apis
  - security
  - integrations
---

Over the past few months, PyPI has added some additional checks that
can reject uploaded source distributions ("sdists").

These checks are part of a larger initiative to make the Python packaging
ecosystem more resistant to parser differentials, and will be followed
by additional checks that aim to make PyPI's handling of distributions
(both sdists _and_ wheels) less permissive and more strictly conformant
to their respective specifications.

For downstream users (index consumers), there are **no breaking implications**
to these changes. Package maintainers who see failures should ensure that
they're using non-EOL versions of Python as well as build backends
that produce distributions that properly conform to the packaging
standards. Some examples of that conformance are provided below.

<!-- more -->

## Background
