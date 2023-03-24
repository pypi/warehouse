---
title: Getting started
---

{{ preview('oidc-publishing') }}

# Publishing to PyPI with a Trusted Publisher

## Confirming that you're in the beta

Before we do anything else: let's confirm that you're actually in the
beta! You can do this by [logging into PyPI](https://pypi.org/account/login/)
and clicking on "Account settings" in the dropdown under your profile:

![](/assets/dropdown.png)

On the "Account settings" page, you should see a right-side menu that
contains a "Publishing" link:

![](/assets/publishing-link.png)

If you see that link and can click on it, then you're in the beta group!

## Quick background: Publishing with OpenID Connect

OpenID Connect (OIDC) publishing is a mechanism for uploading packages to PyPI, *complementing*
existing methods (username/password combinations, API tokens).

You don't need to understand OIDC to use OIDC publishing with PyPI, but here's
the TL;DR:

1. Certain CI services (like GitHub Actions) are OIDC *identity providers*, meaning that
   they can issue short-lived credentials ("OIDC tokens") that a third party
   can **strongly** verify came from the CI service (as well as which user,
   repository, etc. actually executed);
1. Projects on PyPI can be configured to trust a particular configuration on
   a particular CI service, making that configuration an OIDC publisher
   for that project;
1. Release automation (like GitHub Actions) can submit an OIDC token
   to PyPI. The token will be matched against configurations trusted by
   different projects; if any projects trust the token's configuration,
   then PyPI will mint a *short-lived API token* for those projects and
   return it;
1. The short-lived API token behaves exactly like a normal project-scoped API
   token, except that it's only valid for 15 minutes from time of creation
   (enough time for the CI to use it to upload packages).

This confers significant usability and security advantages when compared
to PyPI's traditional authentication methods:

* Usability: with trusted publishing, users no longer need to manually create
  API tokens on PyPI and copy-paste them into their CI provider. The only
  manual step is configuring the publisher on PyPI.
* Security: PyPI's normal API tokens are long-lived, meaning that an attacker
  who compromises a package's release can use it until its legitimate user
  notices and manually revokes it. Similarly, uploading with a password means
  that an attacker can upload to *any* project associated with the account.
  Trusted publishing avoids both of these problems: the tokens minted expire
  automatically, and are scoped down to only the packages that they're
  authorized to upload to.
