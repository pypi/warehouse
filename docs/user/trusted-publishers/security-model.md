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

    <h3>Security model</h3>

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

    <h3>Considerations</h3>

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

        ![Screenshot of an example configuring an environment on GitHub](/assets/trusted-publishing/github/required-reviewers.png)

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

    <h3>Security Model</h3>

    If a trusted publisher is configured for a given PyPI project, any service
    that uses the configured service account can request an OpenID Connect token
    from Google's identity provider on behalf of that identity. That token can be
    exchanged for a PyPI API token with the ability to publish to the PyPI project.
    The identity used for publishing can be optionally constrained further by
    specifying the subject, an ID that represents the principal making the request.

    <h3>Considerations</h3>

    When using trusted publishing with Google Cloud, you must trust the service account
    and _any service which uses it as the default ephemeral identity_.

    Specifically, it is not recommened to configure the [default service
    accounts](https://cloud.google.com/iam/docs/service-account-types#default), as
    they are provided by default to every service when they are created.

=== "ActiveState"

    <h3>Security Model</h3>

    Trusted Publishing occurs from within an isolated build container in the ActiveState
    Platform build infrastructure.  When a build is triggered by a user that will publish
    to PyPI, an OIDC token is generated and passed into the necessary build container as
    an environment variable along with your release artifact that will be uploaded. The
    OIDC token is used by the build container to request a PyPI API token which it then
    uses to upload your release.

    <h3>Considerations</h3>

    * The user configured in the Trusted Publisher must be the user that triggers the
      build in the ActiveState Platform.  This user will need editing privileges in the
      ActiveState organization associated with the project.
    * The ActiveState Platform project must be private.

    For more information about Trusted Publishing using the ActiveState Platform please
    see the [PyPI configuration documentation](https://docs.activestate.com/platform/start/pypi/) and the [ActiveState Platform documentation](https://docs.activestate.com/platform).

=== "GitLab CI/CD"

    <h3>Security model</h3>

    * OIDC tokens are requested by workflows that specify the
      [`id_tokens`](https://docs.gitlab.com/ee/ci/yaml/index.html#id_tokens) keyword,
      along with the desired audience. The tokens are made available through
      environment variables when the job runs.
    * The claims defined in an OIDC token are *bound to the group and project*, meaning that a
      repository located at orgA/repo cannot impersonate a repository located at orgB/repo.
    * The claims defined in an OIDC token are *bound to the top-level pipeline*, meaning
      that any pipeline included by the top-level pipeline (usually `.gitlab-ci.yml`)
      will be able to upload using a trusted publisher that trusts the `.gitlab-ci.yml`
      pipeline.
    * An OIDC token for a specific repository and pipeline can be generated by anyone
      who has permissions to run that pipeline in the repository's CI/CD.

    <h3>Considerations</h3>

    * In particular, for trusted publishing with GitLab CI/CD, you
      **must**:

        * Trust the correct namespace and repository: if you trust a repository
          other than one you control and trust, that repository can upload to your
          PyPI project.

        * Take care of account resurrection attacks: PyPI checks the namespace
          claim (username or group) included in the OIDC token. However, if that
          username or group is deleted and a new one with the same name is created,
          PyPI will still recognise OIDC tokens generated by the new one as valid.

        * Take care when merging third-party changes to your code: if you trust
          the top-level pipeline `.gitlab-ci.yml`, then you must make sure that
          third-party changes to that file are not malicious. This is particularly
          important since GitLab does not provide granular information about which
          job requested the token: only the top-level pipeline is included in the
          claims, which means that any job run by the top-level pipeline can request
          a valid OIDC token.

        * Take care when adding repository contributors, members, and administrators:
          by default, anybody who can unconditionally commit to your repository can
          also modify your publishing workflow to make it trigger on events you
          may not intend (e.g., a manual `when: manual` rule).

            This particular risk can be mitigated by using a dedicated environment
            with manual approvers, as described below.

    * Trusted publishers are registered to projects, not to users. This means that
      removing a user from a PyPI project does **not** remove any trusted publishers
      that they might have registered, and that you should include a review
      of any/all trusted publishers as part of "offboarding" a project maintainer.

    In addition to the requirements above, you can do the following to
    "ratchet down" the scope of your trusted publishing workflows:

    * **[Use a dedicated environment](https://docs.gitlab.com/ee/ci/environments/)**:
      GitLab CI/CD supports "environments", which can be used to isolate secrets to
      specific workflows. OIDC publishing doesn't use any pre-configured secrets, but a
      dedicated `publish` or `deploy` environment is a general best practice.

        Dedicated environments allow for additional protections like
        [protected environments], which can be used to require manual approval for a
        workflow using the environment.


    * **[Use protected tags]**: if you use a tag-based publishing workflow
      (e.g. triggering on tags pushed), then you can limit tag creation and
      modification to maintainers and higher (or custom roles) for any tags
      that match your release pattern. For example, `v*` will prevent
      non-maintainers from creating or modifying tags that match version
      strings like `v1.2.3`.

    * **Limit the scope of your publishing job**: your publishing job should
      (ideally) have only three steps:

        1. Retrieve the publishable distribution files from **a separate
          build job**;

        2. Exchange the OIDC token for a PyPI API token;

        3. Publish the distributions using `twine` with the API token.

      By using a separate build job, you keep the number of steps that can
      access the OIDC token to a bare minimum. This prevents both accidental
      and malicious disclosure.

[fundamentally dangerous]: https://securitylab.github.com/research/github-actions-preventing-pwn-requests/

[Use a dedicated environment]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment

[Use tag protection rules]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules

[account resurrection attacks]:
../internals/#what-are-account-resurrection-attacks-and-how-does-pypi-protect-against-them

[required reviewers]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#required-reviewers

[protected environments]: https://docs.gitlab.com/ee/ci/environments/protected_environments.html

[Use protected tags]: https://docs.gitlab.com/ee/user/project/protected_tags.html#configuring-protected-tags
