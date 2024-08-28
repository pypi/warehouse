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
    PyPI package owner at the time of verification, and does not imply any
    additional safety about that URL or any other relationship to the project
    in question.

    URL verification occurs when release files are uploaded and is not repeated
    afterwards. This means the websites that verified URLs point to can change,
    and the URL will still show up as verified. The verified status only reflects
    control of the URL **at the time of file upload**, not at any later point.

The following subsections specify the different types of URLs that can be verified.

#### Self-links

PyPI considers any URL pointing to that project on PyPI as verified.
For example, the project page for `pip` will mark all of the
following as verified:

- `https://pypi.org/project/pip/`
- `https://pypi.org/p/pip/`
- `https://pypi.python.org/project/pip`
- `https://pypi.python.org/p/pip`
- `https://python.org/pypi/pip`

#### Via Trusted Publishing

[Trusted Publishing](trusted-publishers/index.md) allows PyPI to attest that the 
publishing workflow for a package is coming from a verified source.

The URLs that can be verified depend on the Trusted Publisher used:

- [GitHub Actions][gh-action-tab]: Packages uploaded using GHA from a repository will have the GitHub URLs for that
  repository verified. For example, for the `pypa/pip` repository, the following URLs will be verified:
    - `https://github.com/pypa/pip`
    - `https://github.com/pypa/pip/*` (all subpaths)
    - `https://github.com/pypa/pip.git`
    - `https://pypa.github.io/pip`
    - `https://pypa.github.io/pip/*` (all subpaths)
- [GitLab CI/CD][gitlab-tab]: Packages uploaded using GitLab CI/CD from a repository will have the GitLab URLs for that
  repository verified. For example, for the `pypa/pip` repository, the following URLs will be verified:
    - `https://gitlab.com/pypa/pip`
    - `https://gitlab.com/pypa/pip/*` (all subpaths)
    - `https://gitlab.com/pypa/pip.git`
- [Google Cloud][gc-tab]: No Google-specific URLs are currently verified.
- [ActiveState][active-tab]: Packages uploaded using ActiveState will have URLs linked to the project in ActiveState 
  verified:
    - `https://platform.activestate.com/pypa/pip`
    - `https://platform.activestate.com/pypa/pip/*` (all subpaths)


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

| Icon                                      | Name             | Description                | Aliases                                                       |
|:------------------------------------------|:-----------------|:---------------------------|:--------------------------------------------------------------|
| :fontawesome-solid-house-chimney:         | Homepage         | For the project homepage   |                                                               |
| :fontawesome-solid-cloud:                 | Download         | A download link            |                                                               |
| :fontawesome-solid-scroll:                | Changelog        | Changelog information      | Change log, Changes, Release notes, News, What's new, History |
| :fontawesome-solid-book:                  | Documentation^*^ | Project <br/>documentation | Docs^*^ or an URL pointing on [Read the Docs]: domains        |
| :fontawesome-solid-bug:                   | Bug^*^           | Bug/Issue report location  | Issue^*^, Tracker^*^, Report^*^                               |
| :fontawesome-solid-circle-dollar-to-slot: | Funding^*^       | Sponsoring information     | Sponsor^*^, Donation^*^, Donate^*^                            |

[Read the Docs]: https://about.readthedocs.com/

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
| :fontawesome-brands-slack:        | Slack^*^ |
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

[^]: _^*^ Or any name starting with this prefix_
