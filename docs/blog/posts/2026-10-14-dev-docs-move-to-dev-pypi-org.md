---
title: PyPI's developer documentation has moved to dev.pypi.org
description: >
  The Warehouse developer documentation now lives at dev.pypi.org.
  Links to warehouse.pypa.io will keep working and redirect to the new address.
authors:
  - jacobcoffee
date: 2026-10-14
tags:
  - infrastructure
  - meta
---

The developer documentation for [Warehouse], the codebase that powers PyPI,
has moved from `warehouse.pypa.io` to **[dev.pypi.org]**.

Existing links to `warehouse.pypa.io` will keep working:
every page now redirects to the same page on `dev.pypi.org`.

<!-- more -->

## Why the move?

PyPI's other sites already live under `pypi.org`:
user documentation at [docs.pypi.org], and this blog at [blog.pypi.org].
The developer documentation was the odd one out.
Moving it to `dev.pypi.org` puts all of PyPI's sites under one domain.

## What's on dev.pypi.org?

The same content that was on `warehouse.pypa.io`, aimed at people working
on warehouse, the codebase behind PyPI itself:

- The [getting started guide] for setting up a local development environment
- An [architectural overview] of how Warehouse fits together
- Reference material, such as the [XML-RPC API]

If you're looking for help _using_ PyPI, such as publishing packages,
Trusted Publishing, or the JSON API, that's still at [docs.pypi.org].

## Do I need to do anything?

**No.** Old links redirect automatically.

If you have bookmarks, or link to the developer documentation from your
own project, we'd appreciate it if you updated them to `dev.pypi.org`,
but existing links will still work and just redirect!

[Warehouse]: https://github.com/pypi/warehouse
[dev.pypi.org]: https://dev.pypi.org/
[docs.pypi.org]: https://docs.pypi.org/
[blog.pypi.org]: https://blog.pypi.org/
[getting started guide]: https://dev.pypi.org/development/getting-started/
[architectural overview]: https://dev.pypi.org/application/
[XML-RPC API]: https://dev.pypi.org/api-reference/xml-rpc/
