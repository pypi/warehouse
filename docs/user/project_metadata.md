# Project Metadata

Python packages can include additional metadata to provide more information 
about the project. This document outlines the specific behaviors 
implemented by PyPI to display project metadata and other details. The 
comprehensive list of metadata fields is available in the [Python Packaging 
User Guide].

[Python Packaging User Guide]: https://packaging.python.org/en/latest/specifications/core-metadata/#core-metadata-specifications


## Project URLs

Packages owners can specify various URLs related to their project using 
the [`[project.urls]` table](https://packaging.python.org/en/latest/specifications/pyproject-toml/#urls) in the package's `pyproject.toml`.

PyPI renders these URLs on the project page and splits them into `verified` and 
`unverified` subgroups. They are also available using the 
[JSON API](https://warehouse.pypa.io/api-reference/json.html).

### Verified details

![Verified details](assets/verified_details.png){ loading=lazy }

PyPI currently supports several ways of verifying project URLs. When a URL is verified, PyPI highlights it using a green checkmark (:fontawesome-solid-circle-check:{ .checked }).

!!! warning

    An URL being verified only attests that the URL is under control of the
    PyPI package owner, and does not imply any additional safety about that
    URL or any other relationship to the project in question.

### Self-links

Any URL to the project on PyPI will be considered verified.

### Via Trusted Publishing

[Trusted Publishing](trusted-publishers/index.md) allows PyPI to attest that the 
publishing workflow for a package is coming from a verified source.

PyPI supports the following OIDC Publishers:

- [GitHub Actions][gh-action-tab]
- [Google Cloud][gc-tab]
- [ActiveState][active-tab]
- [GitLab CI/CD][gitlab-tab]

[gh-action-tab]: trusted-publishers/creating-a-project-through-oidc.md#github-actions
[gc-tab]: trusted-publishers/creating-a-project-through-oidc.md#google-cloud
[active-tab]: trusted-publishers/creating-a-project-through-oidc.md#activestate
[gitlab-tab]: trusted-publishers/creating-a-project-through-oidc.md#gitlab-cicd


### Icons

![Unverified details](assets/unverified_details.png){ loading=lazy }

While the labels can be arbitrary, PyPI recognizes the ones from the
lists below and changes the default icon from
:fontawesome-solid-square-up-right: to a customized one.

#### General URL

| Icon                                      | Name          | Description               | Aliases                   |
|:------------------------------------------|:--------------|:--------------------------|:--------------------------|
| :fontawesome-solid-house-chimney:         | Homepage      | For the project homepage  |                           |
| :fontawesome-solid-cloud:                 | Download      | A download link           |                           |
| :fontawesome-solid-scroll:                | Changelog     | Changelog information     |                           |
| :fontawesome-solid-book:                  | Documentation | Project documentation     | Docs                      |
| :fontawesome-solid-bug:                   | Bug           | Bug/Issue report location | Issue, Tracker, Report    |
| :fontawesome-solid-circle-dollar-to-slot: | Funding       | Sponsoring information    | Sponsor, Donation, Donate |


#### Hosting Platforms

| Icon                           | Name      |
|:-------------------------------|:----------|
| :fontawesome-brands-github:    | GitHub    |
| :fontawesome-brands-gitlab:    | GitLab    |
| :fontawesome-brands-bitbucket: | Bitbucket |
| :fontawesome-brands-google:    | Google    |


#### Social Medias Platforms

| Icon                              | Name     |
|:----------------------------------|:---------|
| :fontawesome-brands-gitter:       | Gitter   |
| :fontawesome-brands-discord:      | Discord  |
| :fontawesome-brands-reddit-alien: | Reddit   |
| :fontawesome-brands-slack:        | Slack    |
| :fontawesome-brands-twitter:      | Twitter  |
| :fontawesome-brands-youtube:      | Youtube  |
| :fontawesome-brands-mastodon:     | Mastodon |

#### Continuous Integration Services

| Icon                           | Name      |
|:-------------------------------|:----------|
| :fontawesome-solid-list-check: | AppVeyor  |
| :fontawesome-solid-list-check: | CircleCI  |
| :fontawesome-solid-list-check: | Codecov   |
| :fontawesome-solid-list-check: | Coveralls |
| :fontawesome-solid-list-check: | Travis CI |

#### Python Ecosystem

| Icon                        | Name   | Alias      |
|:----------------------------|:-------|:-----------|
| :fontawesome-solid-cube:    | PyPI   | Cheeseshop |
| :fontawesome-brands-python: | Python |            |

