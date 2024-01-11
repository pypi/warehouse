---
title: Security Model and Considerations
---

# Security model and considerations

## General considerations

While more secure than passwords and long-lived API tokens, OIDC publishing
is not a panacea. In particular:

* Short-lived API tokens are still sensitive material, and should not be
  disclosed (ideally not at all, but certainly not before they expire).

* OIDC tokens themselves are sensitive material, and should not be disclosed.
  OIDC tokens are also short-lived, but an attacker who successfully intercepts
  one can mint API tokens against it for as long as it lives.

* Configuring a trusted publisher means establishing trust in a particular piece
  of external state (such as a GitHub Actions workflow); that state **must not**
  be controllable by untrusted parties.

In summary: treat your trusted publishers *as if* they were API tokens. If you
wouldn't let a user or piece of code access your API token, then they shouldn't
be able to invoke your trusted publisher.

## Provider-specific considerations

Each trusted publishing provider is its own OIDC identity provider, with its
own security model and considerations.

=== "GitHub Actions"

    ### Security model

    GitHub Actions' own security model for OpenID Connect tokens is a little subtle:

    * Any workflow defined in a repository can request an OIDC token,
      *with any audience*, **so long as it has the `id-token: write` permission**.

    * The claims defined in an OIDC token are *bound to the workflow*, meaning
      that a workflow defined at `foo.yml` in `org/repo` **cannot impersonate**
      a workflow defined at `bar.yml` in `org/repo`. However, if `foo.yml` is
      *renamed* to `bar.yml`, then the *new* `bar.yml` will be indistinguishable
      from the old `bar.yml` **except** for claims that reflect the repository's
      state (e.g. `git` ref, branch, etc.).

    * *Generally speaking*, "third party" events **cannot** request an OIDC
      token: even if they can trigger the workflow that requests the token,
      the actual token retrieval step will fail. For example: PRs issued from forks
      of a repository **cannot** access the OIDC tokens in the "upstream"
      repository's workflows.

      * The exception to this is `pull_request_target` events, which are
        **[fundamentally dangerous] by design** and should not be used without
        careful consideration.

    ### Considerations

    * In particular, for trusted publishing with GitHub Actions, you
      **must**:

        * Trust the correct username and repository: if you trust a repository
          other than one you control and trust, that repository can upload to your
          PyPI project.

        * Trust the correct workflow: you shouldn't trust every workflow
          to upload to PyPI; instead, you should isolate responsibility to the
          smallest (and least-privileged) possible separate workflow. We recommend
          naming this workflow `release.yml`.

        * Take care when merging third-party changes to your code: if you trust
          `release.yml`, then you must make sure that third-party changes to that
          workflow (or code that runs within that workflow) are not malicious.

        * Take care when adding repository contributors, members, and administrators:
          by default, anybody who can unconditionally commit to your repository can
          also modify your publishing workflow to make it trigger on events you
          may not intend (e.g., a manual `workflow_dispatch` trigger).

          This particular risk can be mitigated by using a dedicated environment
          with manual approvers, as described below.

    * Trusted publishers are registered to projects, not to users. This means that
      removing a user from a PyPI project does **not** remove any trusted publishers
      that they might have registered, and that you should include a review
      of any/all trusted publishers as part of "offboarding" a project maintainer.

    PyPI has protections in place to make some attacks against OIDC more difficult
    (like [account resurrection attacks]). However, like all forms of authentication,
    the end user is **fundamentally responsible** for applying it correctly.

    In addition to the requirements above, you can do the following to
    "ratchet down" the scope of your trusted publishing workflows:

    * **Use per-job permissions**: The `permissions` key can be defined on the
      workflow level or the job level; the job level is **always more secure**
      because it limits the number of jobs that receive elevated `GITHUB_TOKEN`
      credentials.

    * **[Use a dedicated environment]**: GitHub Actions supports "environments,"
      which can be used to isolate secrets to specific workflows. OIDC publishing
      doesn't use any pre-configured secrets, but a dedicated `publish` or `deploy`
      environment is a general best practice.

        Dedicated environments allow for additional protections like
        [required reviewers], which can be used to require manual approval for a
        workflow using the environment.

        For example, here is how `pypa/pip-audit`'s `release` environment
        restricts reviews to members of the maintenance and admin teams:

        ![](/assets/trusted-publishing/github/required-reviewers.png)

    * **[Use tag protection rules]**: if you use a tag-based publishing workflow
      (e.g. triggering on tags pushed), then you can limit tag creation and
      modification to maintainers and higher (or custom roles) for any tags
      that match your release pattern. For example, `v*` will prevent
      non-maintainers from creating or modifying tags that match version
      strings like `v1.2.3`.

    * **Limit the scope of your publishing job**: your publishing job should
      (ideally) have only two steps:

        1. Retrieve the publishable distribution files from **a separate
          build job**;

        2. Publish the distributions using `pypa/gh-action-pypi-publish@release/v1`.

      By using a separate build job, you keep the number of steps that can
      access the OIDC token to a bare minimum. This prevents both accidental
      and malicious disclosure.

=== "Google Cloud"

    TODO

=== "ActiveState"

    TODO

=== "GitLab CI/CD"

    TODO

[fundamentally dangerous]: https://securitylab.github.com/research/github-actions-preventing-pwn-requests/

[Use a dedicated environment]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment

[Use tag protection rules]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules

[account resurrection attacks]:
../internals/#what-are-account-resurrection-attacks-and-how-does-pypi-protect-against-them

[required reviewers]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#required-reviewers
