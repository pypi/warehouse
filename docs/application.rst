The Warehouse codebase
======================

Warehouse uses the
`Pyramid <https://docs.pylonsproject.org/projects/pyramid/en/latest/index.html>`__
web framework, the
`SQLAlchemy <https://docs.sqlalchemy.org/en/latest/>`__ ORM, and
`Postgres <https://www.postgresql.org/docs/>`__ for its database.
Warehouse's front end uses Jinja2 templates.

The production deployment for Warehouse is in progress and currently
doesn't use any containers, although we may change that in the
future. In the development environment, we use several `Docker
<https://docs.docker.com/>`__ containers, and use `Docker Compose
<https://docs.docker.com/compose/overview/>`__ to `manage
<https://github.com/pypa/warehouse/blob/master/docker-compose.yml#L3>`__
running the containers and the connections between them. In the future
we will probably reduce that number to two containers, one of which
contains static files for the website, and the other which contains
the Python web application code running in a virtual environment and
the database.

Since Warehouse was built on top of a pre-existing database and
developers had to fit our ORM to the existing tables, some of the code
in the ORM may not look like code from SQLAlchemy’s documentation. There
are some places where joins are done using name-based logic instead of a
foreign key (but this may change in the future).

Warehouse also uses `Pyramid's hybrid URL traversal and dispatch
<https://docs.pylonsproject.org/projects/pyramid/en/latest/narr/hybrid.html>`__.
Using factory classes, resources are provided directly to the views
based on the URL pattern.

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

::

    bin/ - high-level scripts for Docker, Travis, and Makefile commands
    dev/ - assets for developer environment
    tests/ - tests
    warehouse/ - code in modules
        legacy/ - most of the read-only APIs implemented here
        forklift/ - APIs for upload
        accounts/ - user accounts
        admin/ - application-administrator-specific
        cache/ - caching
        classifiers/ - frame trove classifiers
        cli/ - entry scripts and [the interactive shell](https://warehouse.readthedocs.io/development/getting-started/#running-the-interactive-shell)
        i18n/ - internationalization
        locales/ - internationalization
        manage/ - logged-in user functionality (i.e., manage account & owned projects)
        migrations/ - DB
        packaging/ - models
        rate_limiting/ - rate limiting to prevent abuse
        rss/ - RSS feeds
        sitemap/ - site maps
        utils/ - various utilities Warehouse uses
