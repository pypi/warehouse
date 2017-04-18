Getting started
===============

We're pleased that you are interested in working on Warehouse.

Setting up a development environment to work on Warehouse should be a
straightforward process. If you have any difficulty, please contact us so
we can improve the process.


Quickstart for Developers with Docker experience
================================================

.. code-block:: console

    $ git clone git@github.com:pypa/warehouse.git
    $ cd warehouse
    $ make serve
    $ make initdb
    $ docker start

View Warehouse in the browser at ``http://localhost:80/``.


Detailed Installation Instructions
==================================

Getting the warehouse source code
---------------------------------

Clone the warehouse repository from GitHub:

.. code-block:: console

    $ git clone git@github.com:pypa/warehouse.git


Configure the development environment
-------------------------------------

Why Docker?
~~~~~~~~~~~

Docker simplifies development environment set up.

Warehouse uses Docker and `Docker Compose <https://docs.docker.com/compose/>`_
to automate setting up a "batteries included" development environment.
The Dockerfile and ``docker-compose.yml`` files include all the required steps
for installing and configuring all the required external services of the
development environment.


Installing Docker
~~~~~~~~~~~~~~~~~

* Install `Docker Engine <https://docs.docker.com/engine/installation/>`_

.. _Docker for Mac: https://docs.docker.com/engine/installation/mac/
.. _Docker for Windows: https://docs.docker.com/engine/installation/windows/
.. _Docker for Linux: https://docs.docker.com/engine/installation/linux/


Verifying Docker Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker is installed: ``docker -v``


Install Docker Compose
~~~~~~~~~~~~~~~~~~~~~~

Install Docker Compose using the Docker provided
`installation instructions <https://docs.docker.com/compose/install/>`_.

.. note::
   Docker Compose will be installed by `Docker for Mac`_ and
   `Docker for Windows`_ automatically.


Verifying Docker Compose Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker Compose is installed: ``docker-compose -v``


Building the Warehouse Container
--------------------------------

Once you have Docker and Docker Compose installed, run:

.. code-block:: console

    $ make build

This will pull down all of the required docker containers, build
Warehouse and run all of the needed services. The Warehouse repository will be
mounted inside of the docker container at ``/app/``.


Running the Warehouse Container and Services
--------------------------------------------

After building the Docker container, you'll need to create a Postgres database
and run all of the data migrations.

First start the Docker services that make up the Warehouse application.  In
one terminal run the command:

.. code-block:: console

    $ make serve

Next, you will:

* create a new Postgres database,
* install example data to the Postgres database,
* run migrations, and
* load some example data from `Test PyPI <https://testpypi.python.org/>`_

In a second terminal, separate from the make serve command above, run:

.. code-block:: console

    $ make initdb

If you get an error about xz, you may need to install the `xz` utility. This is
highly likely on Mac OS X and Windows.

.. note:: reCaptcha is featured in authentication and registration pages. To
          enable it, pass ``RECAPTCHA_SITE_KEY`` and ``RECAPTCHA_SECRET_KEY``
          through to ``serve`` and ``debug`` targets.


Viewing Warehouse in a browser
------------------------------

Web container is listening on port 80. It's accessible at
``http://localhost:80/``.

.. note::

    If you are using ``docker-machine`` on an older version of Mac OS or
    Windows, the warehouse application might be accessible at
    ``https://<docker-ip>:80/`` instead. You can get information about the
    docker container with ``docker-machine env``


What did we just do and what is happening behind the scenes?
------------------------------------------------------------

The repository is exposed inside of the web container at ``/app/`` and
Warehouse will automatically reload when it detects any changes made to the
code.

The example data located in ``dev/example.sql.xz`` is taken from
`Test PyPI <https://testpypi.python.org/>`_ and has been sanitized to remove
anything private. The password for every account has been set to the string
``password``.


Troubleshooting
===============

Errors when executing ``make serve``
------------------------------------

* If the ``Dockerfile`` is edited or new dependencies are added (either by you
  or a prior pull request), a new container will need to built. A new container
  can be built by running ``make build``. This should be done before
  running ``make serve`` again.

* If ``make serve`` hangs after a new build, you should stop any
  running containers and repeat ``make serve``.

* To run Warehouse behind a proxy set the appropriate proxy settings in the
  ``Dockerfile``.

"no space left on device" when using ``docker-compose``
-------------------------------------------------------

``docker-compose`` may leave orphaned volumes during teardown. If you run
into the message "no space left on device", try running the following command
(assuming Docker >= 1.9):

.. code-block:: console

   docker volume rm $(docker volume ls -qf dangling=true)

.. note:: This will delete orphaned volumes as well as directories that are not
   volumes in /var/lib/docker/volumes

(Solution found and further details available at
https://github.com/chadoe/docker-cleanup-volumes)


Building Styles
===============

Styles are written in the scss variant of Sass and compiled using Gulp. They
will be automatically built when changed when ``make serve`` is running.


Running the Interactive Shell
=============================

There is an interactive shell available in Warehouse which will automatically
configure Warehouse and create a database session and make them available as
variables in the interactive shell.

To run the interactive shell, simply run:

.. code-block:: console

    $ make shell

The interactive shell will have the following variables defined in it:

====== ========================================================================
config The Pyramid ``Configurator`` object which has already been configured by
       Warehouse.
db     The SQLAlchemy ORM ``Session`` object which has already been configured
       to connect to the database.
====== ========================================================================


Running tests and linters
=========================

.. note:: PostgreSQL 9.4 is required because of pgcrypto extension

The Warehouse tests are found in the ``tests/`` directory and are designed to
be run using make.

To run all tests, all you have to do is:

.. code-block:: console

    $ make tests

This will run the tests with the supported interpreter as well as all of the
additional testing that we require.

If you want to run a specific test, you can use the ``T`` variable:

.. code-block:: console

    $ T=tests/unit/i18n/test_filters.py make tests

You can run linters, programs that check the code, with:

.. code-block:: console

    $ make lint


Building documentation
======================

The Warehouse documentation is stored in the ``docs/`` directory. It is written
in `reStructured Text`_ and rendered using `Sphinx`_.

Use `make` to build the documentation. For example:

.. code-block:: console

    $ make docs

The HTML documentation index can now be found at
``docs/_build/html/index.html``.

.. _`pip`: https://pypi.python.org/pypi/pip
.. _`sphinx`: https://pypi.python.org/pypi/Sphinx
.. _`reStructured Text`: http://sphinx-doc.org/rest.html
