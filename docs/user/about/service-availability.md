---
title: Service Availability
---

# Service Availability

PyPI is heavily cached and distributed via CDN thanks to our sponsor [Fastly](https://www.fastly.com/) and thus is generally available globally. However, as the site is mostly maintained by volunteers, we do not provide any specific Service Level Agreement, and as could be expected for a giant distributed system, things can and sometimes do, go wrong. 

See [our status page](https://status.python.org/) for current and past outages and incidents. 

If you have high availability requirements for your package index, consider either a [private index](https://pypi.org/help/#private-indices) or a [mirror](https://pypi.org/help/#mirroring). The [bandersnatch project](https://pypi.org/project/bandersnatch/) is the recommended solution for mirroring. Note that the storage requirements for a PyPI mirror would exceed 1 terabyte — and growing!

