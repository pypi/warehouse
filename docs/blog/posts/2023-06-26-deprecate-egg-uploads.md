---
title: Deprecation of bdist_egg uploads to PyPI
description: PyPI will stop accepting .egg uploads August 1, 2023.
authors:
  - ewdurbin
date: 2023-06-26
tags:
  - deprecation
---

[PEP 715](https://peps.python.org/pep-0715/), deprecating `bdist_egg`/`.egg`
uploads to PyPI has been
[accepted](https://discuss.python.org/t/pep-715-disabling-bdist-egg-distribution-uploads-on-pypi/27610/13).
We'll begin the process of implementing this today.

Please note that this does **NOT** remove any existing uploaded eggs from PyPI.

<!-- more -->

The deprecation timeline is as follows:

- Today, June 26, 2023: All maintainers of projects which have uploaded one or
  more eggs since January 1, 2023 will receive a one-time email informing them
  of this change.
- Today, June 26, 2023: Each upload of an egg to PyPI will result in a notice
  being sent to all Owners and Maintainers for the project.
- August 1, 2023: Uploads of eggs will be [**rejected**](https://i.kym-cdn.com/photos/images/original/001/402/192/398.jpg) by PyPI.

You can read more detailed rationale in [PEP 715](https://peps.python.org/pep-0715/#rationale).
Thanks to contributor [William Woodruff](https://blog.yossarian.net) for his
work to author and propose PEP 715, as well as support the rollout of the
implementation.

---

_Ee Durbin is the Director of Infrastructure at
the Python Software Foundation.
They have been contributing to keeping PyPI online, available, and
secure since 2013._
