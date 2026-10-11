---
title: Troubleshooting
---

# Troubleshooting

## Reusable workflows on GitHub

[Reusable workflows] cannot currently be used as the workflow in a Trusted
Publisher. This is a practical limitation, and is being tracked in
[warehouse#11096].

## Ratelimiting

PyPI currently imposes rate limits on Trusted Publisher registration: no more
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

* `invalid-payload` with `unknown trusted publishing issuer` error: the OIDC
  provider that generated the token is not supported. This can happen when using
  a self-managed GitLab instance, since currently only projects hosted on
  <https://gitlab.com> are supported.
* `invalid-token`: the OIDC token itself is either formatted incorrectly,
  has an invalid signature, is expired, etc. This encompasses pretty much
  any failure mode that can occur with an OIDC token (which is just a JWT)
  *before* it's actually matched against a publisher.
* `invalid-pending-publisher` and `invalid-publisher`: the OIDC token itself
  is well-formed (and has a valid signature), but doesn't match any known
  (pending) OIDC publisher. This likely indicates a mismatch between the
  OIDC publisher specified in the user/project settings and the claims
  represented in the actual OIDC token. Check for typos! If you're using
  GitHub Actions, check if the workflow is using the same environment
  as configured when the publisher was configured on PyPI.
* `invalid-publisher` for a previously-working project: this usually indicates
  a typo or that something has changed on either side. One example we've seen
  is when a source repository is renamed, and the configuration on PyPI
  continues to use the old repository name. For GitHub, check that the
  `repository_owner`, `repository` and workflow filename values are the same on
  both sides.

## Upload errors

When using a pending publisher to create a new project, you may run into
an error like this:

```
Non-user identities cannot create new projects. This was probably caused by
successfully using a pending publisher but specifying the project name
incorrectly (either in the publisher or in your project's metadata).
Please ensure that both match.
```

This means that the pending publisher created the project successfully, but
the project name supplied in the upload's metadata does not match it. This
can happen if either the pending publisher's project name or the metadata's
was mistyped or otherwise mistakenly entered.

For example, a project that specifies a `python-example` in its metadata but
is registered as `example` in the pending publisher will cause this error.

To fix this, you must determine which of the two names is the correct one:

* If the name used in the pending publisher is the correct one, then you must
  update your project metadata to reflect that name. Subsequent uploads with the
  Trusted Publisher will work automatically, and no further action is required.

* If the name used in the project metadata is the correct one, then you must:

  1. Go to [your projects] and delete the incorrectly created project.
     This will also have the effect of deleting the incorrectly registered
     Trusted Publisher.

  2. Create a new pending publisher with the corrected project name.

  The next upload will create the project with the expected name, and subsequent
  uploads will also work as expected.

[reusable workflows]: https://docs.github.com/en/actions/using-workflows/reusing-workflows

[warehouse#11096]: https://github.com/pypi/warehouse/issues/11096

[your projects]: https://pypi.org/manage/projects/
