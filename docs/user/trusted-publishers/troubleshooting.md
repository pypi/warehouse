---
title: Troubleshooting
---

# Troubleshooting

## Reusable workflows on GitHub

[Reusable workflows] cannot currently be used as the workflow in a trusted
publisher. This is a practical limitation, and is being tracked in
[warehouse#11096].

## Ratelimiting

PyPI currently imposes ratelimits on trusted publisher registration: no more
than 100 publishers can be registered by a single user or IP address within a 24
hour window.

This should be more than sufficient for most users (since publisher
registration should happen rarely relative to publisher use), but maintainers
with large numbers of projects or who access PyPI via a shared IP address
may run into ratelimiting errors. If this happens to you, please wait 24 hours,
try again, and then [contact PyPI's admins](mailto:admin@pypi.org)
if the problem persists.

## Token minting

Here's a quick enumeration of errors you might see from the `mint-token`
endpoint:

* `not-enabled`: this indicates that PyPI's backend has
  disabled OIDC entirely. You should not see this message during normal
  operation, **unless** PyPI's admins have decided to disable OIDC support.
* `invalid-payload`: the OIDC token payload submitted to the `mint-token`
  endpoint is not formatted correctly. The payload **must** be a JSON serialized
  object, with the following layout:

  ```json
  {
    "token": "oidc-token-here"
  }
  ```

  No other layouts are supported.

* `invalid-token`: the OIDC token itself is either formatted incorrectly,
  has an invalid signature, is expired, etc. This encompasses pretty much
  any failure mode that can occur with an OIDC token (which is just a JWT)
  *before* it's actually matched against a publisher.
* `invalid-pending-publisher` and `invalid-publisher`: the OIDC token itself
  is well-formed (and has a valid signature), but doesn't match any known
  (pending) OIDC publisher. This likely indicates a mismatch between the
  OIDC publisher specified in the user/project settings and the claims
  represented in the actual OIDC token. Check for typos and GitHub environment
  configurations!

[reusable workflows]: https://docs.github.com/en/actions/using-workflows/reusing-workflows

[warehouse#11096]: https://github.com/pypi/warehouse/issues/11096
