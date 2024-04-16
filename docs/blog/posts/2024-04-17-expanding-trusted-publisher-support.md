---
title: Expanding Trusted Publisher Support
description: Announcing additional Trusted Publishing providers
authors:
  - di
date: 2024-04-17
tags:
  - publishing
  - security
  - oidc
---

Starting today, PyPI package maintainers can publish via Trusted Publishing
from three additional providers:

 * GitLab CI/CD
 * Google Cloud
 * ActiveState

These providers join existing support for publishing from GitHub Actions without
long-lived passwords or API tokens, which [we announced last year], and bring
support for Trusted Publishing to even more hosted providers.

<!-- more -->

### About Trusted Publishing

Trusted Publishing is our term for using the [OpenID Connect (OIDC)] standard
to exchange short-lived identity tokens between a trusted third-party service
and PyPI. This method can be used in automated environments and eliminates the
need to use username/password combinations or long-lived, manually generated
API tokens to authenticate with PyPI when publishing.

Instead, maintainers can configure PyPI to trust an identity provided by a
given OpenID Connect Identity Provider (IdP). This allows allows PyPI to verify
and delegate trust to that identity, which is then authorized to request
short-lived, tightly-scoped API tokens from PyPI. These API tokens never need
to be stored or shared, rotate automatically by expiring quickly, and provide a
verifiable link between a published package and its source.

### Get started today

To get started with using trusted publishers on PyPI, see our documentation
here: <https://docs.pypi.org/trusted-publishers/>.

### Acknowledgements

Funding for work implementing Google Cloud and GitLab support was provided by
the Google Open Source Security Team, and much of the development work was
performed by [Trail of Bits], with special thanks to contributors [William
Woodruff] and [Facundo Tuesca].

ActiveState support was provided by ActiveState, with special thanks to
contributors [Carey Hoffman] and [Pete Garcin].

---

_Dustin Ingram is a maintainer of the Python Package Index._

[we announced last year]: 2023-04-20-introducing-trusted-publishers.md
[William Woodruff]: https://github.com/woodruffw
[Facundo Tuesca]: https://github.com/facutuesca
[Carey Hoffman]: https://github.com/th3coop
[Pete Garcin]: https://github.com/rawktron
[OpenID Connect (OIDC)]: https://openid.net/connect/
[Trail of Bits]: https://www.trailofbits.com/
