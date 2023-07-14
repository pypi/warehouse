---
title: Internals and Technical Details
---

# Internals and Technical Details

!!! note

    This page is **not useful** to *users* of trusted publishers!

    It's intended primarily for PyPI developers and developers of other
    package indices looking to support similar authentication models.

## How trusted publishing works

PyPI's trusted publishing functionality is built on top of
[OpenID Connect], or "OIDC" for short.

OIDC gives *services* (like GitHub Actions) a way to *provably identify*
themselves: an authorized entity (such as a GitHub user, or an automated
workflow) can present an *OIDC token* to a third-party service. That
party service can then verify the token and determine whether it's
authorized to perform some other action.

In the context of trusted publishing, the machinery is as follows:

* *OIDC identity providers* like GitHub ("providers" for short) generate OIDC
  tokens that contain scoped *claims*, which convey appropriate authorization
  scopes.

    * For example, the `repo` claim might be bound to the value
      `octo-org/example`, indicating that the token should be authorized
      to access resources for which `octo-org/example` is a valid repository.

* *Trusted publishers* are pieces of configuration on PyPI that tell PyPI
  *which* OIDC providers to trust, and *when* (i.e., which specific set
  of claims to consider valid).

    * For example, a trusted publisher configuration for GitHub Actions might
      specify `repo: octo-org/example` with `workflow: release.yml` and
      `environment: release`, indicating that a presented OIDC token **must**
      contain exactly those claims to be considered valid.

    * When applicable, PyPI also checks claims that prevent
      [account resurrection attacks]. For example, with GitHub as the OIDC IdP,
      PyPI checks the `repository_owner_id` claim.

* *Token exchange* is how PyPI converts OIDC tokens into credentials
  (PyPI API tokens) that can be used to authenticate against the package upload
  endpoint.

    * Token exchange boils down to a matching process between a presented
      OIDC token and every trusted publisher currently configured on PyPI:
      the token's signature is first verified (to ensure that it's actually
      coming from the expected provider), and then its claims are matched
      against zero or more projects with registered trusted publishers.

      If the OIDC token corresponds to one or more trusted publishers, then
      a short-lived (15 minute) PyPI API token is issued. This API token
      is scoped to every project with a matching trusted publisher, meaning
      that it can be used to upload to multiple projects (if so configured).

If everything goes correctly, a successful trusted publishing flow results in
a short-lived PyPI API token *without any user interaction*, which in turn
offers security and ergonomic benefits to PyPI packagers: users no longer
have to worry about token provisioning or revocation.

## Q&A

### Why does trusted publishing use a "two-phase" token exchange?

As noted above, trusted publishing uses a "token exchange" mechanism, which
happens in two phases:

1. The uploading client presents an OIDC token, which PyPI verifies.
   If valid, PyPI responds with a valid and appropriately scoped PyPI API token.

1. The uploading client takes the valid PyPI API token that it was given
   and uses it as normal.

In principle, this is more complicated than necessary: PyPI could
instead take the OIDC token *directly* and treat it as a special case during
API token handling, skipping a network round-trip between the uploading
client and the package index.

While conceptually simpler, a "one-phase" token exchange presents problems
of its own:

1. *Isolation of concerns*: conceptually, an OIDC token is an *externally
    issued* token, with external concerns: it has failure modes that aren't
    internal to PyPI itself (e.g. a failure of the issuing identity provider
    to sign correctly).

    Keeping these concerns isolated from PyPI's actual business logic
    ensures that they remain encapsulated and do not impose design
    or security constraints on PyPI itself (e.g., mandating that
    PyPI use OIDC tokens in places where they are a poor fit).

1. *Complications to existing authentication and authorization logic*:
    PyPI has a large pre-existing body of AuthN and AuthZ code. Most of the
    existing code for API tokens is directly adapted to the PyPI API token
    format, which is based on
    [Macaroons].

    Handling OIDC tokens (which are [JSON Web Tokens] under the hood) would have
    required significant duplication of existing codepaths, which in turn
    means an increased testing (and vulnerability) surface. By exchanging
    OIDC tokens for API tokens in PyPI's existing format, our implementation
    could reuse our existing (and well-tested) codepaths without any significant
    changes.

1. *Automatic secret scanning and revocation challenges*: PyPI is a partner
   in [GitHub's secret scanning system], which allows PyPI to automatically
   revoke PyPI API tokens that are accidentally leaked in public repositories.

   This system relies on PyPI tokens having a unique prefix: they all begin
   with `pypi-`. Without that prefix, GitHub would be unable to efficiently
   scan public repositories for tokens.

   OIDC tokens are issued by independent providers, meaning that PyPI has
   no ability to impose a `pypi-` prefix on them. Moreover, OIDC tokens
   are strictly defined as [JSON Web Tokens], meaning that they appear
   as mostly unstructured random characters. This makes them difficult to scan
   for. Finally, even an effective scanner for JWTs would need to report
   every compromised JWT to both its issuer (e.g., GitHub itself) *and* its
   consumer (e.g., PyPI), introducing complexity and additional
   failure modes during revocation.

   Exchanging OIDC tokens for PyPI API tokens completely sidesteps all of these
   problems.

While these reasons are documented for PyPI, they are likely some of the
same reasons why other "federated" consumers of OIDC (like cloud providers)
do similar "two-phase" exchange mechanisms.

### Why is the PyPI project to publisher relationship "many-many"?

If you play around with trusted publishers on PyPI, you'll notice that
PyPI projects can have multiple publishers, and individual publishers
can be registered to multiple projects.

This is a "many-many" relationship between PyPI projects and their trusted
publishers which, like "two-phase" exchange, seems more complicated in
principle than necessary.

In practice, this many-many relationship addresses publishing patterns commonly
used by the Python packaging community:

1. *One publisher, many projects*: it's not uncommon for several related
   PyPI projects to share a single source repository. Moreover, it's not
   uncommon for several related PyPI projects to share the same release
   workflow, due to tandem releases (e.g., a simultaneous release
   of a library package and its corresponding CLI tool).

   Trusted publishing's design accommodates this use case: maintainers
   can use the same `release.yml` workflow for all of their packages,
   rather than having to split it up by packages.

1. *One project, many publishers*: PyPI contains a large number of built
   distributions ("wheels"), some of which are "binary wheels" that contain
   processor, operating system, or platform-specific binaries.

   Because these binaries are specific to individual platforms, they frequently
   must be built on separate platforms, often on dedicated builder
   configurations for each platform.

   From there, it is common to have each individual platform builder also
   perform releases for that platform: Linux-specific wheels are uploaded
   by the Linux builder, etc.

   This is arguably **not best practice**, in terms of reliability and isolation
   of concerns: the best practice would be to *collect* all platform-specific
   builds in a final platform-agnostic publishing step, which could then
   be a single publisher.

   However, in the interest of getting trusted publishers into users' hands
   without requiring them to make significant unrelated changes to the builds,
   the trusted publishing feature allows users to register multiple
   publishers against a single project. Consequently, `sampleproject`
   can be published from both `release-linux.yml` and `release-macos.yml`
   without needing to be refactored into a single `release.yml`.

### What are account resurrection attacks, and how does PyPI protect against them?

Some OIDC providers support username changes, so a claim of
`repository_owner: octo-org` might not necessarily refer to the same `octo-org`
that a user initially authorized in a trusted publisher configuration.

If a repository owner changes their username or deletes their account, a
malicious actor may be able to take the freed username and create their
own repositories under the original trusted name. This is known as an *account
resurrection attack*.

To solve this issue for GitHub-based publishers, PyPI always checks the
`repository_owner_id` claim. This claim attests to the ID of the repository
owner, which is stable and permanent unlike usernames. When a trusted publisher
is configured, PyPI looks up the configured username's ID and stores it. During
API token minting, PyPI checks the `repository_owner_id` claim against the
stored ID and fails if they don't match. Through this process, only the original
GitHub user remains authorized to publish to their PyPI projects, even if they
change their username or delete their account.

[OpenID Connect]: https://openid.net/connect/

[account resurrection attacks]:
./#what-are-account-resurrection-attacks-and-how-does-pypi-protect-against-them

[Macaroons]: https://en.wikipedia.org/wiki/Macaroons_(computer_science)

[JSON Web Tokens]: https://en.wikipedia.org/wiki/JSON_Web_Token

[GitHub's secret scanning system]: https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning
