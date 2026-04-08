# Warehouse codebase

Warehouse uses the
[Pyramid](https://docs.pylonsproject.org/projects/pyramid/en/latest/index.html) web framework, the
[SQLAlchemy](https://docs.sqlalchemy.org/en/latest/) ORM, and
[Postgres](https://www.postgresql.org/docs/) for its database.
Warehouse's front end uses [Jinja2](https://jinja.palletsprojects.com/) templates.

The production deployment for Warehouse is deployed using
[Cabotage](https://github.com/cabotage/cabotage-app), which manages
[Docker](https://docs.docker.com/) containers deployed via [Kubernetes](https://kubernetes.io).

In the development environment, we use several [Docker](https://docs.docker.com/) containers
orchestrated by [Docker Compose](https://docs.docker.com/compose/overview/)
to [manage](https://github.com/pypi/warehouse/blob/main/docker-compose.yml#L3)
running the containers and the connections between them.

Since Warehouse was built on top of an existing database (for legacy
PyPI) and developers had to fit our ORM to the existing tables, some
of the code in the ORM may not look like code from the SQLAlchemy
documentation. There are some places where joins are done using
name-based logic instead of a foreign key (but this may change in the
future).

Warehouse also uses [hybrid URL traversal and dispatch](https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hybrid.html). Using
factory classes, resources are provided directly to the views based on the URL
pattern. This method of handling URLs may be unfamiliar to developers used to
other web frameworks, such as Django or Flask. [This article](https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/muchadoabouttraversal.html) has a helpful
discussion of the differences between URL dispatch and traversal in Pyramid.

## Usage assumptions and concepts

See [PyPI help](https://pypi.org/help/#packages) and the glossary
section of [UI Principles](ui-principles.md) to understand projects, releases,
packages, maintainers, authors, and owners.

Warehouse is specifically the codebase for the official Python Package
Index, and thus focuses on architecture and features for PyPI and Test
PyPI. People and groups who want to run their own package indexes
usually use other tools, like [devpi](https://pypi.org/project/devpi-server/).

Warehouse serves four main classes of users:

1. *People who are not logged in.* This accounts for the majority of
   browser traffic and all API download traffic.
2. *Owners/maintainers of one or more projects.* This accounts for
   almost all writes. A user must create and use a PyPI account to
   maintain or own a project, and there is no particular functionality
   available to a logged-in user other than to manage projects they
   own/maintain. As of March 2018, PyPI had about 270,000 users, and
   Test PyPI had about 30,000 users.
3. *PyPI application moderators*. These users have a subset of the
   permissions of *PyPI application administrators* to assist in some
   routine administration tasks such as adding new trove classifiers,
   and adjusting upload limits for distribution packages.
4. *PyPI application administrators*, e.g., Ee Durbin,
   Dustin Ingram, and Donald Stufft, who can ban
   spam/malware projects, help users with account recovery, and so
   on. There are fewer than ten such admins.

Since reads are *much* more common than writes (much more goes out than
goes in), we try to cache as much as possible.

## File and directory structure

The top-level directory of the Warehouse repo contains files including:

- `LICENSE`
- `CONTRIBUTING.rst` (the contribution guide)
- `README.rst`
- `requirements.txt` for the Warehouse virtual environment
- `Dockerfile`: creates the Docker containers that Warehouse runs in
- `docker-compose.yml` file configures Docker Compose
- `setup.cfg` for test configuration
- `Makefile`: commands to spin up Docker Compose and the Docker
  containers, run the linter and other tests, etc.
- files associated with Warehouse's front end, e.g.,
  `webpack.config.js`

Directories within the repository:

- [bin/](https://github.com/pypi/warehouse/tree/main/bin) - high-level scripts for Docker, Continuous Integration, and Makefile commands
- [dev/](https://github.com/pypi/warehouse/tree/main/dev) - assets for developer environment
- [tests/](https://github.com/pypi/warehouse/tree/main/tests) - tests
- [warehouse/](https://github.com/pypi/warehouse/tree/main/warehouse) - code in modules
    - [accounts/](https://github.com/pypi/warehouse/tree/main/warehouse/accounts) - user accounts
    - [admin/](https://github.com/pypi/warehouse/tree/main/warehouse/admin) - application-administrator-specific
    - [banners/](https://github.com/pypi/warehouse/tree/main/warehouse/banners) - notification banners
    - [cache/](https://github.com/pypi/warehouse/tree/main/warehouse/cache) - caching
    - [classifiers/](https://github.com/pypi/warehouse/tree/main/warehouse/classifiers) - frame trove classifiers
    - [cli/](https://github.com/pypi/warehouse/tree/main/warehouse/cli) - entry scripts and
      the interactive shell
    - [email/](https://github.com/pypi/warehouse/tree/main/warehouse/email) - services for sending emails
    - [forklift/](https://github.com/pypi/warehouse/tree/main/warehouse/forklift) - [upload API](https://docs.pypi.org/api/upload/)
    - [i18n/](https://github.com/pypi/warehouse/tree/main/warehouse/i18n) - internationalization
    - [integrations/](https://github.com/pypi/warehouse/tree/main/warehouse/integrations) - integrations with other services
    - [legacy/](https://github.com/pypi/warehouse/tree/main/warehouse/legacy) - most of the read-only APIs implemented here
    - [locale/](https://github.com/pypi/warehouse/tree/main/warehouse/locale) - internationalization
    - [macaroons/](https://github.com/pypi/warehouse/tree/main/warehouse/macaroons) - API token support
    - [manage/](https://github.com/pypi/warehouse/tree/main/warehouse/manage) - logged-in user functionality (i.e., manage account &
      owned/maintained projects)
    - [metrics/](https://github.com/pypi/warehouse/tree/main/warehouse/metrics) - services for recording metrics
    - [migrations/](https://github.com/pypi/warehouse/tree/main/warehouse/migrations) - changes to the database schema
    - [oidc/](https://github.com/pypi/warehouse/tree/main/warehouse/oidc) - [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) support
    - [organizations/](https://github.com/pypi/warehouse/tree/main/warehouse/organizations) - organization accounts
    - [packaging/](https://github.com/pypi/warehouse/tree/main/warehouse/packaging) - core packaging models (projects, releases, files)
    - [rate_limiting/](https://github.com/pypi/warehouse/tree/main/warehouse/rate_limiting) - rate limiting to prevent abuse
    - [rss/](https://github.com/pypi/warehouse/tree/main/warehouse/rss) - [RSS Feeds](https://docs.pypi.org/api/feeds/)
    - [search/](https://github.com/pypi/warehouse/tree/main/warehouse/search) - utilities for building and querying the search index
    - [sitemap/](https://github.com/pypi/warehouse/tree/main/warehouse/sitemap) - site maps
    - [sponsors/](https://github.com/pypi/warehouse/tree/main/warehouse/sponsors) - sponsors management
    - [static/](https://github.com/pypi/warehouse/tree/main/warehouse/static) - static site assets
    - [templates/](https://github.com/pypi/warehouse/tree/main/warehouse/templates) - Jinja templates for web pages, emails, etc.
    - [utils/](https://github.com/pypi/warehouse/tree/main/warehouse/utils) - various utilities Warehouse uses

## Historical context & deprecations

For the history of Python packaging and distribution, see [the PyPA history
page](https://www.pypa.io/en/latest/history/).

From the early 2000s till April 2018, [the legacy PyPI codebase](https://github.com/pypa/pypi-legacy), not Warehouse, powered
PyPI. Warehouse deliberately does not provide some features that users
may be used to from the legacy site, such as:

- "hidden releases"

- uploading to pythonhosted.com documentation hosting ([discussion and
  plans](https://github.com/pypi/warehouse/issues/582))

- download counts visible in the API
  (instead, use [the Google BigQuery service](https://packaging.python.org/guides/analyzing-pypi-package-downloads/))

- key management: PyPI no longer has a UI for users to manage GPG or
  SSH public keys

- uploading new releases via the web UI: instead, maintainers should
  use the command-line tool [Twine](https://twine.readthedocs.io/)

- updating release descriptions via the web UI: instead, to update
  release metadata, you need to upload a new release ([discussion](https://mail.python.org/pipermail/distutils-sig/2017-December/031826.html))

- [uploading a package without first verifying an email address](https://status.python.org/incidents/mgjw1g5yjy5j)

- [HTTP access to APIs; now it's HTTPS-only](https://mail.python.org/pipermail/distutils-sig/2017-October/031712.html)

- GPG/PGP signatures for packages (no longer visible in the web UI or index, but retrievable
  by appending an `.asc` if the signature exists)

- [OpenID and Google auth login](https://mail.python.org/pipermail/distutils-sig/2018-January/031855.html)
  are no longer supported.
