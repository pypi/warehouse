---
title: Service Availability
---

# Service Availability

PyPI is heavily cached and distributed via CDN thanks to our sponsor [Fastly](https://www.fastly.com/) and thus is generally available globally. However, as the site is mostly maintained by volunteers, we do not provide any specific Service Level Agreement, and as could be expected for a giant distributed system, things can and sometimes do, go wrong. 

See [our status page](https://status.python.org/) for current and past outages and incidents. 

## Private indices and mirrors

If you have high availability requirements for your package index, consider running either a [private index](../publishing/troubleshooting.md#how-can-i-publish-my-private-packages-to-pypi) or a mirror. 

For mirroring, the [bandersnatch project](https://pypi.org/project/bandersnatch/) is recommended. Note that the storage requirements for a full mirror would exceed 1 terabyte — and growing!
