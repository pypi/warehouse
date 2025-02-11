---
title: Security Model and Considerations
---

# Security model and considerations

Trusted Publishing is primarily designed to be a more secure alternative to
the long-lived API tokens that have traditionally been used for publishing to
PyPI.

In recent years, theft of credentials such as API tokens has [played a major
role in cyber attacks]. The reason for this is the unfortunate reality that
managing credentials can be complicated and risky. Trusted Publishing reduces
this risk by using short-lived tokens instead of long-lived tokens. Short-lived
tokens are less likely to be misplaced, leaked in logs, or stolen by malware
since they don't have to be stored. Additionally, if short-lived tokens are
leaked, they only give attackers a narrow time window to exploit the leaked
token, which minimizes the potential damage.

However, it is important to still be aware of the kinds of risks that
Trusted Publishing does not cover. You should think of Trusted Publishing as one
tool in the toolbelt for securing packages.

## General considerations

* Trusted Publishing uses short-lived API tokens that expire 
  no more than 15 minutes after the OIDC flow that authorizes them.
  Just like normal API authentication, Trusted Publishing
  does not assert the safety of the code or the trustworthiness
  of its authors.
 
* Trusted Publishing does not address whether the package has been modified
  before or after it was built. [Attestations] can address those risks.

* Short-lived API tokens are sensitive material that must be protected from
  getting stolen or leaked.

* OIDC tokens themselves are also sensitive material that must be protected
  from getting stolen or leaked. OIDC tokens expire quickly, but an attacker who
  successfully intercepts one can use it to generate API tokens until it
  expires.

* Configuring a Trusted Publisher means trusting an identity provider (IdP),
  such as GitHub Actions. Trusted Publishing relies on the integrity of that
  IdP and the actors that are authorized to use it. In practice, this means
  that users of Trusted Publishing must protect and secure the CI/CD workflows
  that they register as Trusted Publishers, as weaknesses in those workflows
  can be equivalent to credential compromise.

In summary: treat your Trusted Publishers *as if* they are API tokens. If you
wouldn't let a user or piece of code access your API token, then they shouldn't
be able to invoke your Trusted Publisher.

## Provider-specific considerations

Each Trusted Publishing provider is its own OIDC identity provider, with its
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

    * In particular, for Trusted Publishing with GitHub Actions, you
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

    * Trusted Publishers are registered to projects, not to users. This means that
      removing a user from a PyPI project does **not** remove any Trusted Publishers
      that they might have registered, and that you should include a review
      of any/all Trusted Publishers as part of "offboarding" a project maintainer.

    PyPI has protections in place to make some attacks against OIDC more difficult
    (like [account resurrection attacks]). However, like all forms of authentication,
    the end user is **fundamentally responsible** for applying it correctly.

    In addition to the requirements above, you can do the following to
    "ratchet down" the scope of your Trusted Publishing workflows:

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

    If a Trusted Publisher is configured for a given PyPI project, any service
    that uses the configured service account can request an OpenID Connect token
    from Google's identity provider on behalf of that identity. That token can be
    exchanged for a PyPI API token with the ability to publish to the PyPI project.
    The identity used for publishing can be optionally constrained further by
    specifying the subject, an ID that represents the principal making the request.

    <h3>Considerations</h3>

    When using Trusted Publishing with Google Cloud, you must trust the service account
    and _any service which uses it as the default ephemeral identity_.

    Specifically, it is not recommended to configure the [default service
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
      will be able to upload using a Trusted Publisher that trusts the `.gitlab-ci.yml`
      pipeline.
    * An OIDC token for a specific repository and pipeline can be generated by anyone
      who has permissions to run that pipeline in the repository's CI/CD.

    <h3>Considerations</h3>

    * In particular, for Trusted Publishing with GitLab CI/CD, you
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

    * Trusted Publishers are registered to projects, not to users. This means that
      removing a user from a PyPI project does **not** remove any Trusted Publishers
      that they might have registered, and that you should include a review
      of any/all Trusted Publishers as part of "offboarding" a project maintainer.

    In addition to the requirements above, you can do the following to
    "ratchet down" the scope of your Trusted Publishing workflows:

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

[played a major role in cyber attacks]: https://therecord.media/cisa-cyberattacks-using-valid-credentials

[Attestations]: /attestations/

[fundamentally dangerous]: https://securitylab.github.com/research/github-actions-preventing-pwn-requests/

[Use a dedicated environment]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment

[Use tag protection rules]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules

[account resurrection attacks]:
../internals/#what-are-account-resurrection-attacks-and-how-does-pypi-protect-against-them

[required reviewers]: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#required-reviewers

[protected environments]: https://docs.gitlab.com/ee/ci/environments/protected_environments.html

[Use protected tags]: https://docs.gitlab.com/ee/user/project/protected_tags.html#configuring-protected-tags
