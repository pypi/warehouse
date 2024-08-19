# Projects metadata


## Project-URL

A package can contain optional [Project URL](https://packaging.python.org/en/latest/specifications/core-metadata/#project-url-multiple-use) 
keys.

PyPI renders these URLs on the package project page. They are also available in 
the JSON data when requesting the package information.

### Verified details

![Verified details](assets/verified_details.png){ loading=lazy }


[Trusted Publishing](trusted-publishers) allow PyPI to verify certain 
information submitted by the package maintainer. Verified information appears in
a separate section of the package detail page. A verified URL will have a green 
checkmark attached (:fontawesome-solid-circle-check:{ .checked }).

!!! warning

    An URL being verified only attest that the _provenance_ of the build has 
    been verified, i.e. the packages sources are coming from the URL specified.

    PyPI does not check the package content itself.


### Icons

![Unverified details](assets/unverified_details.png){ loading=lazy }

While the labels can be arbitrary, `warehouse` recognizes the one from the
lists below and changes the default icon from
:fontawesome-solid-square-up-right: to a customized one.

#### General URL

| Icon                              | Name      | Description               | Aliases                                                   |
|:----------------------------------|:----------|:--------------------------|:----------------------------------------------------------|
| :fontawesome-solid-house-chimney: | Homepage  | For the project homepage  |                                                           |
| :fontawesome-solid-cloud:         | Download  | A download link           |                                                           |
| :fontawesome-solid-scroll:        | Changelog | Changelog information     |                                                           |
| :fontawesome-solid-book:          | Documentation | Project documentation     | :fontawesome-solid-info:{ title="Docs" }                  |
| :fontawesome-solid-bug:           | Bug | Bug/Issue report location | :fontawesome-solid-info:{ title="Issue, Tracker, Report"} |
| :fontawesome-solid-circle-dollar-to-slot: | Funding | Sponsoring information | :fontawesome-solid-info:{ title="Sponsor, Donation, Donate"}                               |


#### Hosting Platforms

| Icon                           | Name      |
|:-------------------------------|:----------|
| :fontawesome-brands-github:    | GitHub    |
| :fontawesome-brands-gitlab:    | Gitlab    |
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

| Icon                              | Name      |
|:----------------------------------|:----------|
| :fontawesome-solid-list-check: | AppVeyor  |
| :fontawesome-solid-list-check: | CircleCI  |
| :fontawesome-solid-list-check: | Codecov   |
| :fontawesome-solid-list-check: | Coveralls |
| :fontawesome-solid-list-check: | Travis CI  |

#### Python Ecosystem

| Icon                              | Name      | Alias                                         |
|:----------------------------------|:----------|:----------------------------------------------|
| :fontawesome-solid-cube:         | PyPI    | :fontawesome-solid-info:{ title="Cheeseshop"} |
| :fontawesome-brands-python: | Python |                                               |

