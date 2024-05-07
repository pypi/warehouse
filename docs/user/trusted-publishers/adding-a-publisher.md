---
title: Adding a Trusted Publisher to an Existing PyPI Project
---

# Adding a trusted publisher to an existing PyPI project

Adding a trusted publisher to a PyPI project only requires a single setup step.

On the ["Your projects" page](https://pypi.org/manage/projects/), click "Manage" on any project you'd like to
configure:

![Image showing the 'Your Projects' page](/assets/trusted-publishing/manage-link.png)

Then, click on "Publishing" in the project's sidebar:

![Image showing the 'Publishing' link in the project sidebar](/assets/trusted-publishing/project-publishing-link.png)

That link will take you to the publisher configuration page for the project,
which will allow you to configure trusted publishers for the different
platforms supported by PyPI (such as GitHub Actions).

To enable a publisher, you need to tell PyPI how to trust it. Each trusted
publisher has its own configuration requirements; click the tabs below to see
each.

=== "GitHub Actions"

    For GitHub Actions, you **must** provide the repository owner's name, the
    repository's name, and the filename of the GitHub Actions workflow that's
    authorized to upload to PyPI. In addition, you may **optionally**
    provide the name of a [GitHub Actions environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment).

    For example, if you have a project at `https://github.com/octo-org/sampleproject`
    that uses a publishing workflow defined in `.github/workflows/release.yml`
    and a custom environment named `release`, then you'd do the following:

    ![Image showing adding a new GitHub publisher](/assets/trusted-publishing/github/project-publishing-form.png)

    !!! note

        Configuring an environment is optional, but **strongly** recommended:
        with a GitHub environment, you can apply additional restrictions to
        your trusted workflow, such as requiring manual approval on each run
        by a trusted subset of repository maintainers.

    Once you click "Add", your publisher will be registered and will appear
    at the top of the page:

    ![Image showing a newly added GitHub publisher](/assets/trusted-publishing/github/project-publisher-registered.png)

    From this point onwards, the `release.yml` workflow on `octo-org/sampleproject` will
    be able to generate short-lived API tokens from PyPI for the project you've registered
    it against.

=== "Google Cloud"

    For Google Cloud, you **must** provide the email address of the account or
    service account used to publish. [You can learn more about Google Cloud
    service accounts
    here](https://cloud.google.com/iam/docs/service-account-overview).

    For example, if you have created a service account named
    "SERVICE_ACCOUNT_NAME" in the project "PROJECT_NAME" which is in use by
    the environment where you would like to publish to PyPI from, your service
    account email would take the form
    `SERVICE_ACCOUNT_NAME@PROJECT_NAME.iam.gserviceaccount.com`, and you would do
    the following:

    ![Image showing adding a new Google Cloud publisher](/assets/trusted-publishing/google/project-publishing-form.png)

    !!! warning

        Google Cloud also provides [default service
        accounts](https://cloud.google.com/iam/docs/service-account-types#default)
        for various products:

          *  Compute Engine: `PROJECT_ID-compute@developer.gserviceaccount.com`
          *  App Engine: `PROJECT_NAME@appspot.gserviceaccount.com`

        However it is **not** recommended that these be used for publishing, as
        they are provided by default to every service when they are created.

    !!! note

        Configuring the subject is optional. The subject is the numeric ID that
        represents the principal making the request. While not required, providing the
        subject further restricts the identity which is used for publishing, ensuring
        that only a specific instance of a service account can publish, not any service
        account with the configured email. See
        <https://cloud.google.com/docs/authentication/token-types#id-contents>
        for more details

    Once you click "Add", your publisher will be registered and will appear
    at the top of the page:

    ![Image showing a newly added Google Cloud publisher](/assets/trusted-publishing/google/project-publisher-registered.png)

=== "ActiveState"

    For ActiveState, you must provide the name of the ActiveState project,
    the ActiveState organization that project belongs to, and the ActiveState user performing
    the publish action. Learn more about getting set up on the ActiveState Platform [here](https://docs.activestate.com/platform/start/pypi/).
    ![Image showing adding a new ActiveState publisher](/assets/trusted-publishing/activestate/project-publishing-form.png)
    Once you click "Add", your publisher will be registered and will appear at the top of the page:
    ![Image showing a newly added ActiveState publisher](/assets/trusted-publishing/activestate/project-publisher-registered.png)

=== "GitLab CI/CD"

    !!! note

        Currently, only projects hosted on <https://gitlab.com> are supported. Self-managed
        instances are not supported.

    For GitLab CI/CD, you **must** provide the repository's namespace, the
    repository's name, and the filepath of the top-level GitLab CI/CD pipeline
    definition that's authorized to upload to PyPI. In addition, you may
    **optionally** provide the name of a
    [GitLab CI/CD environment](https://docs.gitlab.com/ee/ci/environments/).

    For example, if you have a project at `https://gitlab.com/namespace/sampleproject`
    with a top-level pipeline defined in `.gitlab-ci.yml` and a custom environment
    named `release`, then you'd do the following:

    ![Image showing adding a new GitLab publisher](/assets/trusted-publishing/gitlab/project-publishing-form.png)

    !!! note

        Configuring an environment is optional, but **strongly** recommended:
        with a GitLab environment, you can apply additional restrictions to
        your trusted workflow, such as requiring manual approval on each run
        by a trusted subset of repository maintainers.

    Once you click "Add", your publisher will be registered and will appear
    at the top of the page:

    ![Image showing a newly added GitLab publisher](/assets/trusted-publishing/gitlab/project-publisher-registered.png)

    From this point onwards, the `.gilab-ci.yml` pipeline on `namespace/sampleproject`
    will be able to generate short-lived API tokens from PyPI for the project you've
    registered it against.

A publisher can be registered against multiple PyPI projects (e.g. for a
multi-project repository), and a single PyPI project can have multiple
publishers (e.g. for multiple workflows on different architectures, operating
systems).
