Warehouse codebase
==================

Warehouse uses the
`Pyramid`_ web framework, the
`SQLAlchemy <https://docs.sqlalchemy.org/en/latest/>`__ ORM, and
`Postgres <https://www.postgresql.org/docs/>`__ for its database.
Warehouse's front end uses `Jinja2 <http://jinja.pocoo.org/>`__ templates.

The production deployment for Warehouse is in progress and currently
does not use any containers, although we may change that in the
future. In the development environment, we use several `Docker`_  containers, and use `Docker Compose <https://docs.docker.com/compose/overview/>`__ to `manage <https://github.com/pypa/warehouse/blob/master/docker-compose.yml#L3>`__
running the containers and the connections between them. In the future
we will probably reduce that number to two containers, one of which
contains static files for the website, and the other which contains
the Python web application code running in a virtual environment and
the database.

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

Warehouse serves three main classes of users:

1. *People who are not logged in.* This accounts for the majority of
   browser traffic and all API download traffic.
2. *Owners/maintainers of one or more projects.* This accounts for
   almost all writes. A user must create and use a PyPI account to
   maintain or own a project, and there is no particular functionality
   available to a logged-in user other than to manage projects they
   own/maintain. As of March 2018, PyPI had about 270,000 users, and
   Test PyPI had about 30,000 users.
3. *PyPI application administrators*, e.g., Ernest W. Durbin III,
   Dustin Ingram, and Donald Stufft, who add classifiers, ban
   spam/malware projects, help users with account recovery, and so
   on. There are under ten such admins.

Since reads are *much* more common than writes (much more goes out than
goes in), we try to cache as much as possible. This is a big reason
that, although we have supported localization in the past, `we currently
don't <https://github.com/pypa/warehouse/issues/1453>`__.

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
-  ``runtime.txt`` for Heroku
-  ``Makefile``: commands to spin up Docker Compose and the Docker
   containers, run the linter and other tests, etc.
-  files associated with Warehouse's front end, e.g.,
   ``Gulpfile.babel.js``

Directories within the repository:

- bin/ - high-level scripts for Docker, Travis, and Makefile commands
- dev/ - assets for developer environment
- tests/ - tests
- warehouse/ - code in modules

  - legacy/ - most of the read-only APIs implemented here
  - forklift/ - :ref:`upload-api-forklift`
  - accounts/ - user accounts
  - admin/ - application-administrator-specific
  - cache/ - caching
  - classifiers/ - frame trove classifiers
  - cli/ - entry scripts and `the interactive shell <https://warehouse.readthedocs.io/development/getting-started/#running-the-interactive-shell>`_
  - i18n/ - internationalization
  - locales/ - internationalization
  - manage/ - logged-in user functionality (i.e., manage account &
    owned/maintained projects)
  - migrations/ - changes to the database schema
  - packaging/ - models
  - rate_limiting/ - rate limiting to prevent abuse
  - rss/ - RSS feeds: :doc:`api-reference/feeds`
  - sitemap/ - site maps
  - utils/ - various utilities Warehouse uses

.. _Pyramid: https://docs.pylonsproject.org/projects/pyramid/en/latest/index.html
.. _Docker: https://docs.docker.com/
.. _hybrid URL traversal and dispatch: https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hybrid.html
.. _This article: https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/muchadoabouttraversal.html

Historical context & deprecations
---------------------------------

For the history of Python packaging and distribution, please see `the
PyPA history page <https://www.pypa.io/en/latest/history/>`_.

From the early 2000s till April 2018, `the legacy PyPI codebase
<https://github.com/pypa/pypi-legacy>`_, not Warehouse, powered
PyPI. Warehouse deliberately does not provide some features that users
may be used to from the legacy site, such as:

- "hidden releases"

- uploading to pythonhosted.com documentation hosting (`discussion and
  plans <https://github.com/pypa/warehouse/issues/582>`_)

- `download counts visible in the API <https://warehouse.readthedocs.io/api-reference/xml-rpc/#changes-to-legacy-api>`_:
  instead, use `the Google BigQuery service <https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_)

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
