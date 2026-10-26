---
title: Higher limits for organization projects
description: >
  Projects owned by a PyPI organization can now upload larger files
  and use more storage by default.
authors:
  - jacobcoffee
  - Thespi-Brain
date: 2026-10-26
tags:
  - organizations
---

Projects owned by a [PyPI organization] now get higher limits by default:

|                             | Personal projects | Organization projects |
|-----------------------------|-------------------|-----------------------|
| Largest file you can upload | 100 MiB           | **200 MiB**           |
| Total size of a project     | 10 GiB            | **20 GiB**            |

<!-- more -->

There's nothing to turn on.
Every project owned by either a company or community organization gets the new limits automatically,
including projects you move into an organization later.
A project that leaves an organization goes back to the personal limits.

## Creating new projects

Organizations can also create up to **10 new projects per day**,
more than a personal account can.
This isn't new, but we want to make sure organizations know about it.

## Need more?

Personal and organization projects can both still [request an increase]
through the regular support channels.
Any increase you already have stays in place:
your project always gets whichever limit is higher.

[PyPI organization]: https://docs.pypi.org/organization-accounts/
[request an increase]: https://docs.pypi.org/project-management/storage-limits/
