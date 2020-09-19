Warehouse codebase
==================

Warehouse uses the
`Pyramid`_ web framework, the
`SQLAlchemy <https://docs.sqlalchemy.org/en/latest/>`__ ORM, and
`Postgres <https://www.postgresql.org/docs/>`__ for its database.
Warehouse's front end uses `Jinja2 <http://jinja.pocoo.org/>`__ templates.

The production deployment for Warehouse is deployed using
`Cabotage <https://github.com/cabotage/cabotage-app>`__, which manages
`Docker`_ containers deployed via `Kubernetes <https://kubernetes.io>`__.

In the development environment, we use several `Docker`_  containers
orchestrated by `Docker Compose <https://docs.docker.com/compose/overview/>`__
to `manage <https://github.com/pypa/warehouse/blob/master/docker-compose.yml#L3>`__
running the containers and the connections between them.

Since Warehouse was built on top of an existing database (for legacy
PyPI) and developers had to fit our ORM to the existing tables, some
of the code in the ORM may not look like code from the SQLAlchemy
documentation. There are some places where joins are done using
name-based logic instead of a foreign key (but this may change in the
future).

Warehouse also uses `hybrid URL traversal and dispatch`_. Using
factory classes, resources are provided directly to the views based on the URL
pattern. This method of handling URLs may be unfamiliar to developers used to
other web frameworks, such as Django or Flask. `This article`_ has a helpful
discussion of the differences between URL dispatch and traversal in Pyramid.

Usage assumptions and concepts
------------------------------

See `PyPI help <https://pypi.org/help/#packages>`_ and the glossary
section of :doc:`ui-principles` to understand projects, releases,
packages, maintainers, authors, and owners.

Warehouse is specifically the codebase for the official Python Package
Index, and thus focuses on architecture and features for PyPI and Test
PyPI. People and groups who want to run their own package indexes
usually use other tools, like `devpi
<https://pypi.org/project/devpi-server/>`_.

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
   adjusting upload limits for distribution packages, and reviewing
   malware verdicts.
4. *PyPI application administrators*, e.g., Ernest W. Durbin III,
   Dustin Ingram, and Donald Stufft, who can ban
   spam/malware projects, help users with account recovery, and so
   on. There are under ten such admins.

Since reads are *much* more common than writes (much more goes out than
goes in), we try to cache as much as possible.

File and directory structure
----------------------------

The top-level directory of the Warehouse repo contains files including:

-  ``LICENSE``
-  ``CONTRIBUTING.rst`` (the contribution guide)
-  ``README.rst``
-  ``requirements.txt`` for the Warehouse virtual environment
-  ``Dockerfile``: creates the Docker containers that Warehouse runs in
-  ``docker-compose.yml`` file configures Docker Compose
-  ``setup.cfg`` for test configuration
-  ``Makefile``: commands to spin up Docker Compose and the Docker
   containers, run the linter and other tests, etc.
-  files associated with Warehouse's front end, e.g.,
   ``webpack.config.js``

Directories within the repository:

- `bin/ <https://github.com/pypa/warehouse/tree/master/bin>`_ - high-level scripts for Docker, Travis, and Makefile commands
- `dev/ <https://github.com/pypa/warehouse/tree/master/dev>`_ - assets for developer environment
- `tests/ <https://github.com/pypa/warehouse/tree/master/tests>`_ - tests
- `warehouse/ <https://github.com/pypa/warehouse/tree/master/warehouse>`_ - code in modules

  - `accounts/ <https://github.com/pypa/warehouse/tree/master/warehouse/accounts>`_ - user accounts
  - `admin/ <https://github.com/pypa/warehouse/tree/master/warehouse/admin>`_ - application-administrator-specific
  - `cache/ <https://github.com/pypa/warehouse/tree/master/warehouse/cache>`_ - caching
  - `classifiers/ <https://github.com/pypa/warehouse/tree/master/warehouse/classifiers>`_ - frame trove classifiers
  - `cli/ <https://github.com/pypa/warehouse/tree/master/warehouse/cli>`_ - entry scripts and
    `the interactive shell <https://warehouse.readthedocs.io/development/getting-started/#running-the-interactive-shell>`_
  - `email/ <https://github.com/pypa/warehouse/tree/master/warehouse/email>`_ - services for sending emails
  - `forklift/ <https://github.com/pypa/warehouse/tree/master/warehouse/forklift>`_ - :ref:`upload-api-forklift`
  - `i18n/ <https://github.com/pypa/warehouse/tree/master/warehouse/i18n>`_ - internationalization
  - `legacy/ <https://github.com/pypa/warehouse/tree/master/warehouse/legacy>`_ - most of the read-only APIs implemented here
  - `locales/ <https://github.com/pypa/warehouse/tree/master/warehouse/locales>`_ - internationalization
  - `malware/ <https://github.com/pypa/warehouse/tree/master/warehouse/malware>`_ - automated malware checks
  - `manage/ <https://github.com/pypa/warehouse/tree/master/warehouse/manage>`_ - logged-in user functionality (i.e., manage account &
    owned/maintained projects)
  - `metrics/ <https://github.com/pypa/warehouse/tree/master/warehouse/metrics>`_ - services for recording metrics
  - `migrations/ <https://github.com/pypa/warehouse/tree/master/warehouse/migrations>`_ - changes to the database schema
  - `packaging/ <https://github.com/pypa/warehouse/tree/master/warehouse/packaging>`_ - models
  - `rate_limiting/ <https://github.com/pypa/warehouse/tree/master/warehouse/rate_limiting>`_ - rate limiting to prevent abuse
  - `rss/ <https://github.com/pypa/warehouse/tree/master/warehouse/rss>`_ - RSS feeds: :doc:`api-reference/feeds`
  - `search/ <https://github.com/pypa/warehouse/tree/master/warehouse/search>`_ - utilities for building and querying the search index
  - `sitemap/ <https://github.com/pypa/warehouse/tree/master/warehouse/sitemap>`_ - site maps
  - `templates/ <https://github.com/pypa/warehouse/tree/master/warehouse/templates>`_ - Jinja templates for web pages, emails, etc.
  - `utils/ <https://github.com/pypa/warehouse/tree/master/warehouse/utils>`_ - various utilities Warehouse uses

.. _Pyramid: https://docs.pylonsproject.org/projects/pyramid/en/latest/index.html
.. _Docker: https://docs.docker.com/
.. _hybrid URL traversal and dispatch: https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hybrid.html
.. _This article: https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/muchadoabouttraversal.html

Historical context & deprecations
---------------------------------

For the history of Python packaging and distribution, see `the PyPA history
page <https://www.pypa.io/en/latest/history/>`_.

From the early 2000s till April 2018, `the legacy PyPI codebase
<https://github.com/pypa/pypi-legacy>`_, not Warehouse, powered
PyPI. Warehouse deliberately does not provide some features that users
may be used to from the legacy site, such as:

- "hidden releases"

- uploading to pythonhosted.com documentation hosting (`discussion and
  plans <https://github.com/pypa/warehouse/issues/582>`_)

- `download counts visible in the API <https://warehouse.readthedocs.io/api-reference/xml-rpc/#changes-to-legacy-api>`_
  (instead, use `the Google BigQuery service <https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_)

- key management: PyPI no longer has a UI for users to manage GPG or
  SSH public keys

- uploading new releases via the web UI: instead, maintainers should
  use the command-line tool `Twine <http://twine.readthedocs.io/>`_

- updating release descriptions via the web UI: instead, to update
  release metadata, you need to upload a new release (`discussion
  <https://mail.python.org/pipermail/distutils-sig/2017-December/031826.html>`_)

- `uploading a package without first verifying an email address <https://status.python.org/incidents/mgjw1g5yjy5j>`_

- `HTTP access to APIs; now it's HTTPS-only <https://mail.python.org/pipermail/distutils-sig/2017-October/031712.html>`_

- GPG/PGP signatures for packages (still visible in the :doc:`../api-reference/legacy/`
  per `PEP 503 <https://www.python.org/dev/peps/pep-0503/>`_, but no
  longer visible in the web UI)

- `OpenID and Google auth login <https://mail.python.org/pipermail/distutils-sig/2018-January/031855.html>`_
  are no longer supported.
