---
title: Troubleshooting
---

{{ preview('oidc-publishing') }}

# Troubleshooting

Here's a quick enumeration of errors you might see from the `mint-token`
endpoint:

* `not-enabled`: this indicates that PyPI's backend has
  disabled OIDC entirely. You should not see this message during normal
  operation for the duration of the OIDC beta, **unless** PyPI's admins
  have decided to disable OIDC support.
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
  represented in the actual OIDC token. Check for typos!
