.. _getting-started:

Getting started
===============

We're pleased that you are interested in working on Warehouse.

Your first pull request
-----------------------

After you set up your development environment and ensure you can run
the tests and build the documentation (using the instructions in this
document), please take a look at :doc:`our guide to the Warehouse
codebase <../application>`. Then, look at our `open issues that are
labelled "good first issue"`_, find one you want to work on, comment
on it to say you're working on it, then submit a pull request. Use our
:doc:`submitting-patches` documentation to help.

Setting up a development environment to work on Warehouse should be a
straightforward process. If you have any difficulty, please contact us
so we can improve the process:

- For bug reports or general problems, file an issue on `GitHub`_;
- For real-time chat with other PyPA developers, join ``#pypa-dev`` `on
  Freenode`_;
- For longer-form questions or discussion, message the `pypa-dev mailing
  list`_.

.. _dev-env-install:

Detailed Installation Instructions
----------------------------------

Getting the Warehouse source code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Clone the Warehouse repository from `GitHub`_:

.. code-block:: console

    git clone git@github.com:pypa/warehouse.git


Configure the development environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Why Docker?
~~~~~~~~~~~

Docker simplifies development environment set up.

Warehouse uses Docker and `Docker Compose <https://docs.docker.com/compose/>`_
to automate setting up a "batteries included" development environment.
The Dockerfile and :file:`docker-compose.yml` files include all the required steps
for installing and configuring all the required external services of the
development environment.


Installing Docker
~~~~~~~~~~~~~~~~~

* Install `Docker Engine <https://docs.docker.com/engine/installation/>`_

The best experience for building Warehouse on Windows 10 is to use the
`Windows Subsystem for Linux`_ (WSL) in combination with both
`Docker for Windows`_ and `Docker for Linux`_. Follow the instructions
for both platforms, and see `Docker and Windows Subsystem
for Linux Quirks`_ for extra configuration instructions.

.. _Docker for Mac: https://docs.docker.com/engine/installation/mac/
.. _Docker for Windows: https://docs.docker.com/engine/installation/windows/
.. _Docker for Linux: https://docs.docker.com/engine/installation/linux/
.. _Windows Subsystem for Linux: https://docs.microsoft.com/windows/wsl/


Verifying Docker Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker is installed: ``docker -v``


Install Docker Compose
~~~~~~~~~~~~~~~~~~~~~~

Install Docker Compose using the Docker-provided
`installation instructions <https://docs.docker.com/compose/install/>`_.

.. note::
   Docker Compose will be installed by `Docker for Mac`_ and
   `Docker for Windows`_ automatically.


Verifying Docker Compose Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker Compose is installed: ``docker-compose -v``


Verifying the Neccessary Ports are Available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Warehouse needs access to a few local ports in order to run, namely ports
``80``, ``5433``, and ``9000``. You should check each of these for availability
with the ``lsof`` command.

For example, checking port ``80``:

.. code-block:: console

    lsof -i:80 | grep LISTEN

If the port is in use, the command will produce output, and you will need to
determine what is occupying the port and shut down the corresponding service.
Otherwise, the port is available for Warehouse to use, and you can continue.


Building the Warehouse Container
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once you have Docker and Docker Compose installed, run:

.. code-block:: console

    make build

in the repository root directory.

This will pull down all of the required docker containers, build
Warehouse and run all of the needed services. The Warehouse repository will be
mounted inside of the Docker container at :file:`/opt/warehouse/src/`.


Running the Warehouse Container and Services
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You have to start the Docker services that make up the Warehouse
application. These need ~4 GB of RAM dedicated to Docker to work. This is more
than the default setting of the Docker Engine of 2 GB. Thus, you need to
increase the memory allocated to Docker in
`Docker Preferences <https://docs.docker.com/docker-for-mac/#memory>`_ (on Mac)
or `Docker Settings <https://docs.docker.com/docker-for-windows/#advanced>`_
(on Windows) by moving the slider to 4 GB in the GUI.

Then, in a terminal run the command:

.. code-block:: console

    make serve

This command will produce output for a while, and will not exit. While it runs,
open a second terminal, and run:

.. code-block:: console

    make initdb

This command will:

* create a new Postgres database,
* install example data to the Postgres database,
* run migrations,
* load some example data from `Test PyPI`_, and
* index all the data for the search database.

.. note::

    If you get an error about xz, you may need to install the ``xz`` utility.
    This is highly likely on Mac OS X and Windows.

Once the ``make initdb`` command has finished, you are ready to continue.


Viewing Warehouse in a browser
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Eventually the output of the ``make serve`` command will cease, and you will
see a log message indicating that either the ``web`` service has started
listening:

.. code-block:: console

    web_1 | [2018-05-01 20:28:14 +0000] [6] [INFO] Starting gunicorn 19.7.1
    web_1 | [2018-05-01 20:28:14 +0000] [6] [INFO] Listening at: http://0.0.0.0:8000 (6)
    web_1 | [2018-05-01 20:28:14 +0000] [6] [INFO] Using worker: sync
    web_1 | [2018-05-01 20:28:14 +0000] [15] [INFO] Booting worker with pid: 15

or that the ``static`` container has finished compiling the static assets:

.. code-block:: console

    static_1 | [20:28:37] Starting 'dist:compress'...
    static_1 | [20:28:37] Finished 'dist:compress' after 14 μs
    static_1 | [20:28:37] Finished 'dist' after 43 s
    static_1 | [20:28:37] Starting 'watch'...
    static_1 | [20:28:37] Finished 'watch' after 11 ms

This means that all the services are up, and web container is listening on port
80. It's accessible at <http://localhost:80/>.

.. note::

    If you are using ``docker-machine`` on an older version of Mac OS or
    Windows, the warehouse application might be accessible at
    ``https://<docker-ip>:80/`` instead. You can get information about the
    docker container with ``docker-machine env``


Logging in to Warehouse
^^^^^^^^^^^^^^^^^^^^^^^

In the development environment, the password for every account has been set to
the string ``password``. You can log in as any account at
<http://localhost:80/account/login/>.

To log in as an admin user, log in as ``ewdurbin`` with the password
``password`` at <http://localhost:80/admin/login/>.


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

View Warehouse in the browser at <http://localhost:80/>.


Troubleshooting
---------------

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

"no space left on device" when using ``docker-compose``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:command:`docker-compose` may leave orphaned volumes during
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
container and run ``make initdb`` again.

Docker and Windows Subsystem for Linux Quirks
---------------------------------------------

Once you have installed Docker for Windows, the Windows Subsystem for
Linux, and Docker and Docker Compose in WSL, there are some extra
configuration steps to deal with current quirks in WSL.
`Nick Janetakis`_ has a detailed blog post on these steps, including
installation, but this is a summary of the required steps:

1. In WSL, run ``sudo mkdir /c`` and ``sudo mount --bind /mnt/c /c``
to mount your root drive at :file:`/c` (or whichever drive you are
using).  You should clone into this mount and run
:command:`docker-compose` from within it, to ensure that when volumes
are linked into the container they can be found by Hyper-V.

2. In Windows, configure Docker to enable "Expose daemon on
``tcp://localhost:2375`` without TLS". Note that this may expose your
machine to certain remote code execution attacks, so use with
caution.

3. Add ``export DOCKER_HOST=tcp://0.0.0.0:2375`` to your
:file:`.bashrc` file in WSL, and/or run it directly to enable for the
current session.  Without this, the :command:`docker` command in WSL
will not be able to find the daemon running in Windows.

.. _Nick Janetakis: https://nickjanetakis.com/blog/setting-up-docker-for-windows-and-wsl-to-work-flawlessly


Building Styles
---------------

Styles are written in the scss variant of Sass and compiled using
:command:`gulp`. They will be automatically built when changed when
``make serve`` is running.


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

This will run the tests with the supported interpreter as well as all of the
additional testing that we require.

.. tip::
   Currently, running ``make tests`` from a clean checkout of
   Warehouse (namely, before trying to compile any static assets) will
   fail multiple tests because the tests depend on a file
   (:file:`/app/warehouse/static/dist/manifest.json`) that gets
   created during deployment. So until we fix `bug 1536
   <https://github.com/pypa/warehouse/issues/1536>`_, you'll need to
   install Warehouse in a developer environment and run ``make serve``
   before running tests; see :ref:`dev-env-install` for instructions.

If you want to run a specific test, you can use the ``T`` variable:

.. code-block:: console

    T=tests/unit/i18n/test_filters.py make tests

You can run linters, programs that check the code, with:

.. code-block:: console

    make lint


Building documentation
----------------------

The Warehouse documentation is stored in the :file:`docs/`
directory. It is written in `reStructured Text`_ and rendered using
`Sphinx`_.

Use :command:`make` to build the documentation. For example:

.. code-block:: console

    make docs

The HTML documentation index can now be found at
:file:`docs/_build/html/index.html`.

Building the docs requires Python 3.6. If it is not installed, the
:command:`make` command will give the following error message:

.. code-block:: console

  make: python3.6: Command not found
  Makefile:53: recipe for target '.state/env/pyvenv.cfg' failed
  make: *** [.state/env/pyvenv.cfg] Error 127

What next?
----------

Please look at our `open issues that are labelled "good first
issue"`_, find one you want to work on, comment on it to say you're
working on it, then submit a pull request. Use our
:doc:`submitting-patches` documentation to help.

Talk with us
^^^^^^^^^^^^

You can find us via a `GitHub`_ issue, ``#pypa`` or ``#pypa-dev`` `on
Freenode`_, or the `pypa-dev mailing list`_, to ask questions or get
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
.. _`reStructured Text`: http://sphinx-doc.org/rest.html
.. _`open issues that are labelled "good first issue"`: https://github.com/pypa/warehouse/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22
.. _`GitHub`: https://github.com/pypa/warehouse
.. _`on Freenode`: https://webchat.freenode.net/?channels=%23pypa-dev,pypa
.. _`pypa-dev mailing list`: https://groups.google.com/forum/#!forum/pypa-dev
.. _`Test PyPI`: https://test.pypi.org/
.. _`packaging sprints`: https://wiki.python.org/psf/PackagingSprints
