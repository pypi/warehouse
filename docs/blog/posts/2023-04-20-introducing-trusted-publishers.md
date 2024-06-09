---
title: Introducing 'Trusted Publishers'
description: Announcing a new, more secure way to publish to PyPI
authors:
  - di
date: 2023-04-20
tags:
  - publishing
  - security
  - oidc
---

Starting today, PyPI package maintainers can adopt a new, more secure
publishing method that does not require long-lived passwords or API tokens to
be shared with external systems.

<!-- more -->

### About trusted publishing

"Trusted publishing" is our term for using the [OpenID Connect (OIDC)] standard
to exchange short-lived identity tokens between a trusted third-party service
and PyPI. This method can be used in automated environments and eliminates the
need to use username/password combinations or manually generated API tokens to
authenticate with PyPI when publishing.

Instead, PyPI maintainers can configure PyPI to trust an identity provided by a
given OpenID Connect Identity Provider (IdP). This allows allows PyPI to verify
and delegate trust to that identity, which is then authorized to request
short-lived, tightly-scoped API tokens from PyPI. These API tokens never need
to be stored or shared, rotate automatically by expiring quickly, and provide a
verifiable link between a published package and its source.

### Using trusted publishing with GitHub Actions

PyPI currently supports trusted publishing with GitHub Actions, using [their
support for OpenID Connect].

After configuring PyPI to trust a given GitHub repository and workflow, users
of the PyPA's ['pypi-publish' GitHub Action] can adopt trusted publishing by
removing the `username` and `password` fields from their workflow
configuration, and adding permissions to generate an identity token:

```diff
jobs:
   pypi-publish:
     name: upload release to PyPI
     runs-on: ubuntu-latest
+    permissions:
+      # IMPORTANT: this permission is mandatory for trusted publishing
+      id-token: write
     steps:
       # retrieve your distributions here

       - name: Publish package distributions to PyPI
         uses: pypa/gh-action-pypi-publish@release/v1
-        with:
-          username: __token__
-          password: ${{ secrets.PYPI_TOKEN }}
```

Using the PyPA's GitHub action is strongly recommended, but not required. More
details on how to manually exchange tokens are available [in our
documentation].

### Additional security hardening is available

PyPI package maintainers can further increase the security of their release
workflows by configuring trusted publishers to only release from a specific
[GitHub Actions environment].

Configuring an environment is optional, but strongly recommended: with a GitHub
environment, you can apply additional restrictions to your trusted GitHub
Actions workflow, such as requiring manual approval on each run by a trusted
subset of repository maintainers.

### Unblocking future security improvements

In addition to making publishing more secure now, the availability of trusted
publishers unblocks additional future security improvements for PyPI.

Configuring and using a trusted publisher provides a 'strong link' between a
project and its source repository, which can allow PyPI to verify related
metadata, like the URL of a source repository for a project[^1]. Additionally,
publishing with a trusted publisher allows PyPI to correlate more information
about where a given file was published from in a verifiable way.

Finally, although trusted publishers is currently limited to GitHub Actions,
much of the underlying work that went into making this feature possible is
generalizable and not specific to a single publisher. We're interested in
supporting the ability to publish from additional services that provide OpenID
Connect identities.

### Get started today

To get started with using trusted publishers on PyPI, see our documentation
here: <https://docs.pypi.org/trusted-publishers/>.

### Acknowledgements

Funding for this work was provided by the Google Open Source Security Team, and
much of the development work was performed by [Trail of Bits], with special
thanks to contributor [William Woodruff].

Many thanks as well to [Sviatoslav Sydorenko], maintainer of the PyPA's
['pypi-publish' GitHub Action] for his quick and timely work to add support for
trusted publishers in the action.

Finally, we want to thank all our beta testers, including GitHub staff, for
working with us to ensure this feature is intuitive and useful, and for
providing valuable feedback to improve this feature along the way.

---

_Dustin Ingram is a maintainer of the Python Package Index._

[^1]: Currently, information such as this are provided by the uploader and are not verified as accurate by PyPI.
[OpenID Connect (OIDC)]: https://openid.net/connect/
[their support for OpenID Connect]: https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect
['pypi-publish' GitHub Action]: https://github.com/marketplace/actions/pypi-publish
[in our documentation]: https://docs.pypi.org/trusted-publishers/using-a-publisher/#the-manual-way
[GitHub Actions environment]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
[Trail of Bits]: https://www.trailofbits.com/
[William Woodruff]: https://github.com/woodruffw
[Sviatoslav Sydorenko]: https://github.com/webknjaz
