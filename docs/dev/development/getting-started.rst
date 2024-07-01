.. _getting-started:

Getting started
===============

We're pleased that you are interested in working on Warehouse.

Your first pull request
-----------------------

After you set up your development environment and ensure you can run
the tests and build the documentation (using the instructions in this
document), take a look at :doc:`our guide to the Warehouse codebase
<../application>`. Then, look at our `open issues that are labelled "good first
issue"`_, find one you want to work on, comment on it to say you're working on
it, then submit a pull request. Use our :doc:`submitting-patches` documentation
to help.

Setting up a development environment to work on Warehouse should be a
straightforward process. If you have any difficulty, contact us so we can
improve the process:

- For bug reports or general problems, file an issue on `GitHub`_;
- For real-time chat with other PyPA developers, join ``#pypa-dev`` `on
  Libera`_, or the `PyPA Discord`_;
- For longer-form questions or discussion, visit `Discourse`_.

.. _dev-env-install:

Detailed installation instructions
----------------------------------

Getting the Warehouse source code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
`Fork <https://docs.github.com/en/get-started/quickstart/fork-a-repo>`_ the repository
on `GitHub`_ and
`clone <https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository>`_ it to
your local machine:

.. code-block:: console

    git clone git@github.com:YOUR-USERNAME/warehouse.git

Add a `remote
<https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/configuring-a-remote-for-a-fork>`_ and
regularly `sync <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork>`_ to make sure
you stay up-to-date with our repository:

.. code-block:: console

    git remote add upstream https://github.com/pypi/warehouse.git
    git checkout main
    git fetch upstream
    git merge upstream/main


Configure the development environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. note::
   In case you are used to using a virtual environment for Python development:
   it's unnecessary for Warehouse development. Our Makefile scripts execute all
   developer actions inside Docker containers.

Verifying Make Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Verify that you have make installed in your environment

.. code-block:: console

    make --version

If you do not have it installed,
consult your OS documentation on how to install ``make``.


Why Docker?
~~~~~~~~~~~

Docker simplifies development environment set up.

Warehouse uses Docker and `Docker Compose <https://docs.docker.com/compose/>`_
to automate setting up a "batteries included" development environment. The
:file:`Dockerfile` and :file:`docker-compose.yml` files include all the
required steps for installing and configuring all the required external
services of the development environment.


Installing Docker
~~~~~~~~~~~~~~~~~

* Install `Docker Engine <https://docs.docker.com/engine/installation/>`_

The best experience for building Warehouse on Windows 10 is to use the
`Windows Subsystem for Linux`_ (WSL) in combination with both
`Docker for Windows`_ and `Docker for Linux`_. Follow the instructions
for both platforms.

.. _Docker for Mac: https://docs.docker.com/engine/installation/mac/
.. _Docker for Windows: https://docs.docker.com/engine/installation/windows/
.. _Docker for Linux: https://docs.docker.com/engine/installation/linux/
.. _Windows Subsystem for Linux: https://docs.microsoft.com/windows/wsl/


Verifying Docker installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker is installed: ``docker -v``


Install Docker Compose
~~~~~~~~~~~~~~~~~~~~~~

Install Docker Compose using the Docker-provided
`installation instructions <https://docs.docker.com/compose/install/>`_.

.. note::
   Docker Compose will be installed by `Docker for Mac`_ and
   `Docker for Windows`_ automatically.


Verifying Docker Compose installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker Compose is installed: ``docker compose version``


Verifying the necessary ports are available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Warehouse needs access to a few local ports in order to run, namely ports
``80``, ``5433``, and ``9000``. You should check each of these for availability
with the ``lsof`` command.

For example, checking port ``80``:

.. code-block:: console

    sudo lsof -i:80 | grep LISTEN

If the port is in use, the command will produce output, and you will need to
determine what is occupying the port and shut down the corresponding service.
Otherwise, the port is available for Warehouse to use, and you can continue.

Alternately, you may set the ``WEB_PORT`` environment variable for
``docker compose`` to use instead. An example:

.. code-block:: console

    export WEB_PORT=8080
    make ...

    # or inline:
    WEB_PORT=8080 make ...

Building the Warehouse Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once you have Docker and Docker Compose installed, run:

.. code-block:: console

    make build

in the repository root directory.

This will pull down all of the required docker containers, build Warehouse and
run all of the needed services. The Warehouse repository will be mounted inside
the Docker container at :file:`/opt/warehouse/src/`. After the initial build,
you should not have to run this command again.

.. _running-warehouse-containers:

Running the Warehouse container and services
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You have to start the Docker services that make up the Warehouse
application.

.. tip::

   These services need ~4 GB of RAM dedicated to Docker to work. This is more
   than the default setting of the Docker Engine of 2 GB. Thus, you
   need to increase the memory allocated to Docker in
   `Docker Preferences <https://docs.docker.com/docker-for-mac/#memory>`_
   (on Mac by moving the slider to 4 GB in the GUI) or `Docker Settings <https://docs.docker.com/docker-for-windows/#advanced>`_
   (on Windows by editing the config file found at ``C:\Users\<USER>\AppData\Local\Docker\wsl``).

   If you are using Linux, you may need to configure the maximum map count to get
   the `opensearch` up and running. According to the
   `documentation <https://opensearch.org/docs/2.15/install-and-configure/install-opensearch/index/#important-settings>`_
   this can be set temporarily:

   .. code-block:: console

       # sysctl -w vm.max_map_count=262144

   or permanently by modifying the ``vm.max_map_count`` setting in your
   :file:`/etc/sysctl.conf`.

   Also check that you have more than 5% disk space free, otherwise
   opensearch will become read only. See ``flood_stage`` in the
   `opensearch disk allocation docs
   <https://opensearch.org/docs/latest/install-and-configure/configuring-opensearch/cluster-settings/#cluster-level-routing-and-allocation-settings>`_.


Once ``make build`` has finished,  run the command:

.. code-block:: console

    make serve

This command will:

* ensure the db is prepared,
* run migrations,
* load some example data from `Test PyPI`_, and
* index all the data for the search database.
* start up the containers needed to run Warehouse

After the initial build process, you will only need this command each time you
want to startup Warehouse locally.

``make serve`` will produce output for a while, and will not exit. Eventually
the output will cease, and you will see a log message indicating that either
the ``web`` service has started listening:

.. code-block:: console

    warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Starting gunicorn 20.1.0
    warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
    warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Using worker: sync
    warehouse-web-1   | [2022-12-26 19:27:12 +0000] [7] [INFO] Booting worker with pid: 7

or that the ``static`` container has finished compiling the static assets:

.. code-block:: console

    warehouse-static-1  |
    warehouse-static-1  | webpack 5.75.0 compiled with 1 warning in 6610 ms

or maybe something else.

Bootstrapping the TUF Metadata Repository
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable PyPI Index Signing (`PEP 458 <https://peps.python.org/pep-0458/>`_),
you have to first bootstrap the TUF metadata repository.

.. code-block:: console

    make inittuf

You should see the following line at the bottom of the output:

.. code-block:: console

    Bootstrap completed using `dev/rstuf/bootstrap.json`. 🔐 🎉


This command sends a static *bootstrap payload* to the RSTUF API. The payload
includes the TUF trust root for development and other configuration.

By calling this API, RSTUF creates the TUF metadata repository, installs the
TUF trust root for development, and creates the initial set of TUF metadata.

.. note::

    The RSTUF API is exposed only for development purposes and will not be
    available in production. Currently, no upload hooks or automatic metadata
    update tasks are configured to interact with RSTUF.

    Take a look at the `RSTUF API documentation
    <https://repository-service-tuf.readthedocs.io/en/stable/guide/general/usage.html#adding-artifacts>`_
    to see how you can simulate artifact upload or removal, and how they affect
    the TUF metadata repository:

    * RSTUF API: http://localhost:8001
    * TUF Metadata Repository: http://localhost:9001/tuf-metadata/


Resetting the development database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

    make resetdb

This command will fully reset the development database.


Viewing Warehouse in a browser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

At this point all the services are up, and web container is listening on port
80. It's accessible at http://localhost:80/.

.. note::

    If you are using ``docker-machine`` on an older version of macOS or
    Windows, the warehouse application might be accessible at
    ``https://<docker-ip>:80/`` instead. You can get information about the
    docker container with ``docker-machine env``

.. note::

    On Firefox, the logos might show up as black rectangles due to  the
    *Content Security Policy* used and an implementation bug in Firefox (see
    `this bug report <https://bugzilla.mozilla.org/show_bug.cgi?id=1262842>`_
    for more info).

If you've set a different port via the ``WEB_PORT`` environment variable,
use that port instead.

Logging in to Warehouse
^^^^^^^^^^^^^^^^^^^^^^^

In the development environment, the password for every account has been set to
the string ``password``. You can log in as any account at
http://localhost:80/account/login/.

To log in as an admin user, log in as ``ewdurbin`` with the password
``password``. Due to session invalidation, you may have to login twice.


Stopping Warehouse and other services
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the terminal where ``make serve`` is running, you can use ``Control-C``
to gracefully stop all Docker containers, and thus the one running the
Warehouse application.

Or, from another terminal, use ``make stop`` in the Warehouse
repository root; that'll stop all the Docker processes with
``warehouse`` in the name.


What did we just do and what is happening behind the scenes?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The repository is exposed inside of the web container at
:file:`/opt/warehouse/src/` and Warehouse will automatically reload
when it detects any changes made to the code.

The example data located in :file:`dev/example.sql.xz` is taken from
`Test PyPI`_ and has been sanitized to remove anything private.


Running your developer environment after initial setup
------------------------------------------------------

You won't have to initialize the database after the first time you do
so, and you will rarely have to re-run ``make build``. Ordinarily, to
access your developer environment, you'll:

.. code-block:: console

    make serve

View Warehouse in the browser at http://localhost:80/.

Debugging the webserver
^^^^^^^^^^^^^^^^^^^^^^^

If you would like to use a debugger like pdb that allows you to drop
into a shell, you can use ``make debug`` instead of ``make serve``.

Troubleshooting
---------------

Errors when executing ``make build``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* If you are using Ubuntu and ``invalid reference format`` error is displayed,
  you can fix it by installing Docker through `Snap <https://snapcraft.io/docker>`_.

  .. code-block:: console

      snap install docker

Errors when executing ``make serve``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* If the :file:`Dockerfile` is edited or new dependencies are added
  (either by you or a prior pull request), a new container will need
  to built. A new container can be built by running ``make
  build``. This should be done before running ``make serve`` again.

* If ``make serve`` hangs after a new build, you should stop any
  running containers and repeat ``make serve``.

* To run Warehouse behind a proxy set the appropriate proxy settings in the
  :file:`Dockerfile`.

* If ``sqlalchemy.exec.OperationalError`` is displayed in ``localhost`` after
  ``make serve`` has been executed, shut down the Docker containers. When the
  containers have shut down, run ``make serve`` in one terminal window while
  running ``make initdb`` in a separate terminal window.

Errors when executing ``make purge``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* If ``make purge`` fails with a permission error, check ownership
  and permissions on ``warehouse/static``. ``docker compose`` is spawning
  containers with docker. Generally on Linux that process is running as root.
  So when it writes files back to the file system as the static container
  does those are owned by root. So your docker daemon would be running as root,
  so your user doesn't have permission to remove the files written by the
  containers. ``sudo make purge`` will work.

Errors when executing ``make initdb``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* If ``make initdb`` fails with a timeout like::

    urllib3.exceptions.ConnectTimeoutError: (<urllib3.connection.HTTPConnection object at 0x8beca733c3c8>, 'Connection to opensearch timed out. (connect timeout=30)')

  you might need to increase the amount of memory allocated to docker, since
  opensearch wants a lot of memory (Dustin gives warehouse ~4GB locally).
  Refer to the tip under :ref:`running-warehouse-containers` section for more details.


"no space left on device" when using ``docker compose``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:command:`docker compose` may leave orphaned volumes during
teardown. If you run into the message "no space left on device", try
running the following command (assuming Docker >= 1.9):

.. code-block:: console

   docker volume rm $(docker volume ls -qf dangling=true)

.. note:: This will delete orphaned volumes as well as directories that are not
   volumes in ``/var/lib/docker/volumes``

(Solution found and further details available at
https://github.com/chadoe/docker-cleanup-volumes)


``make initdb`` is slow or appears to make no progress
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This typically occur when Docker is not allocated enough memory to perform the
migrations. Try modifying your Docker configuration to allow more RAM for each
container, temporarily stop ``make_serve`` and run ``make initdb`` again.


``make initdb`` complains about PostgreSQL Version
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You built a Warehouse install some time ago and PostgreSQL has been updated.
If you do not need the data in your databases, it might be best to just blow
away your builds + ``docker`` containers and start again:
``make purge``
``docker volume rm $(docker volume ls -q --filter dangling=true)``


Compilation errors in non-Docker development
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

While Warehouse is designed to be developed in using Docker, you may
have tried to install Warehouse's requirements in your
system or virtual environment. This is discouraged as it can result in
compilation errors due to your system not including libraries
or binaries required by some of Warehouse's dependencies.

An example of such dependency is
`psycopg <https://www.psycopg.org/psycopg3/docs/basic/install.html#local-installation>`_
which requires PostgreSQL binaries and will fail if not present.

If there's a specific use case you think requires development outside
Docker please raise an issue in
`Warehouse's issue tracker <https://github.com/pypi/warehouse/issues>`_.


Disabling services locally
^^^^^^^^^^^^^^^^^^^^^^^^^^

Some services, such as OpenSearch, consume a lot of resources when running
locally, but might not always be necessary when doing local development.

To disable these locally, you can create a ``docker-compose.override.yaml``
file to override any settings in the ``docker-compose.yaml`` file. To
individually disable services, modify their entrypoint to do something else:

.. code-block:: yaml

    version: "3"

    services:
      opensearch:
        entrypoint: ["echo", "OpenSearch disabled"]

Note that disabling services might cause things to fail in unexpected ways.

This file is ignored in Warehouse's ``.gitignore`` file, so it's safe to keep
in the root of your local repo.

See the annotated file ``docker-compose.override.yaml-sample`` for ideas.

Building Styles
---------------

Styles are written in the scss variant of Sass and compiled using
:command:`webpack`. They will be automatically built when changed when
``make serve`` is running.


.. _running-the-interactive-shell:

Running the Interactive Shell
-----------------------------

There is an interactive shell available in Warehouse which will automatically
configure Warehouse and create a database session and make them available as
variables in the interactive shell.

To run the interactive shell, simply run:

.. code-block:: console

    make shell

The interactive shell will have the following variables defined in it:

====== ========================================================================
config The Pyramid ``Configurator`` object which has already been configured by
       Warehouse.
db     The SQLAlchemy ORM ``Session`` object which has already been configured
       to connect to the database.
====== ========================================================================

To use the ``db`` object in the interactive shell, import the class you're
planning to use. For example, if I wanted to use the User object, I would
do this:

.. code-block:: console

    $ make shell
    docker compose run --rm web python -m warehouse shell
    Starting warehouse_redis_1 ...
    ...
    (InteractiveConsole)
    >>>
    >>> from warehouse.accounts.models import User
    >>> db.query(User).filter_by(username='test').all()
    [User(username='test')]

You can also run the IPython shell as the interactive shell. To do so export
the environment variable WAREHOUSE_IPYTHON_SHELL *prior to running the*
``make build`` *step*:

.. code-block:: console

    export WAREHOUSE_IPYTHON_SHELL=1

Now you will be able to run the ``make shell`` command to get the IPython
shell.

Running tests and linters
-------------------------

.. note:: PostgreSQL 9.4 is required because of ``pgcrypto`` extension

The Warehouse tests are found in the :file:`tests/` directory and are
designed to be run using make.

To run all tests, in the root of the repository:

.. code-block:: console

    make tests
    make static_tests

This will run the tests with the supported interpreter as well as all of the
additional testing that we require.

If you want to run a specific test, you can use the ``T`` variable:

.. code-block:: console

    T=tests/unit/i18n/test_filters.py make tests

You can add arguments to the test runner by using the ``TESTARGS`` variable:

.. code-block:: console

    TESTARGS="-vvv -x" make tests

This will pass the arguments ``-vvv`` and ``-x`` down to ``pytest``.

This is useful in scenarios like passing a
`random seed <https://pypi.org/project/pytest-randomly/>`_ to the test runner:

.. code-block:: console

    TESTARGS="--randomly-seed=1234" make tests

You can run linters, programs that check the code, with:

.. code-block:: console

    make lint

Warehouse uses `black <https://github.com/psf/black>`_ for opinionated
formatting and linting. You can reformat with:

.. code-block:: console

    make reformat


Building documentation
----------------------

The Warehouse documentation is stored in the :file:`docs/`
directory. It is written in `reStructured Text`_ and rendered using
`Sphinx`_.

Use :command:`make` to build the documentation. For example:

.. code-block:: console

    make user-docs dev-docs

The HTML index for the user documentation can now be found at
:file:`docs/user-site/index.html`, and the index for the developer
documentation at :file:`docs/dev/_build/html/index.html`.

Building the docs requires Python 3.8. If it is not installed, the
:command:`make` command will give the following error message:

.. code-block:: console

  make: python3.8: Command not found
  Makefile:53: recipe for target '.state/env/pyvenv.cfg' failed
  make: *** [.state/env/pyvenv.cfg] Error 127


Building translations
---------------------

Warehouse is translated into a number of different locales, which are stored in
the :file:`warehouse/locale/` directory.

These translation files contain references to untranslated text in source code
and HTML templates, as well as the translations which have been submitted by
our volunteer translators.

When making changes to files with strings marked for translation, it's
necessary to update these references any time source strings are change, or the
line numbers of the source strings in the source files.

Use :command:`make` to build the translations. For example:

.. code-block:: console

    make translations


What next?
----------

Look at our `open issues that are labelled "good first issue"`_, find one you
want to work on, comment on it to say you're working on it, then submit a pull
request. Use our :doc:`submitting-patches` documentation to help.

Talk with us
^^^^^^^^^^^^

You can find us via a `GitHub`_ issue, ``#pypa`` or ``#pypa-dev`` `on
Libera`_, the `PyPA Discord`_ or `Discourse`_, to ask questions or get
involved. And you can meet us in person at `packaging sprints`_.

Learn about Warehouse and packaging
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Resources to help you learn Warehouse's context:

-  :doc:`../roadmap`
-  `blog posts, mailing list messages, and notes from our core developer
   meetings <https://wiki.python.org/psf/PackagingWG>`__
- :doc:`../application`
-  `the PyPA's list of presentations and
   articles <https://www.pypa.io/en/latest/presentations/>`__
-  `PyPA's history of Python
   packaging <https://www.pypa.io/en/latest/history/>`__


.. _`pip`: https://pypi.org/project/pip
.. _`sphinx`: https://pypi.org/project/Sphinx
.. _`reStructured Text`: https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html
.. _`open issues that are labelled "good first issue"`: https://github.com/pypi/warehouse/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22
.. _`GitHub`: https://github.com/pypi/warehouse
.. _`on Libera`: https://web.libera.chat/#pypa,#pypa-dev
.. _`Discourse` : https://discuss.python.org/c/packaging/14
.. _`PyPA Discord` : https://discord.gg/pypa
.. _`Test PyPI`: https://test.pypi.org/
.. _`packaging sprints`: https://wiki.python.org/psf/PackagingSprints
