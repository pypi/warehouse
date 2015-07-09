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
    $ pip install tox
    $ docker start
    $ docker-compose up
    $ docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
    $ xz -d -k dev/example.sql.xz
    $ docker-compose run web psql -h db -d warehouse -U postgres -v ON_ERROR_STOP=1 -1 -f dev/example.sql
    $ rm dev/example.sql
    $ docker-compose run web warehouse db upgrade head

View Warehouse in the browser at ``http://localhost:80/`` (Linux) or
``http://boot2docker_ip_address:80/`` (for Mac OS X and Windows).

.. note:: Replace ``docker start`` with ``boot2docker up`` if you are using
          Windows or Mac OS X.


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
The Dockerfile and docker-compose.yml files include all the required steps for
installing and configuring all the required external services of the
development environment.

Installing Docker
~~~~~~~~~~~~~~~~~

* Install `Docker <https://docs.docker.com/installation/#installation>`_

On Mac OS X or Windows, the installation instructions will guide you to
install `boot2docker`:

  * Install `boot2docker` as directed in the operating system specific
    installation instructions.

  * Run ``boot2docker init``

  * Run ``boot2docker start``

  * To set the environment variables in your shell, run:
    ``$eval "$(boot2docker shellinit)"``

Verifying Docker Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Check that Docker is installed: ``docker -v``

* On Mac OS X and Windows: Verify that `boot2docker` is installed
  ``boot2docker -v``

Install Docker Compose
~~~~~~~~~~~~~~~~~~~~~~

Install Docker Compose using the Docker provided
`installation instructions <https://docs.docker.com/compose/install/>`_.

Verifying Docker Compose Installation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that Docker Compose is installed: ``docker-compose -v``

Installing tox
~~~~~~~~~~~~~~

Once you have Docker Compose installed, you should install `tox`_.
This is a Python program which can be installed simply with `pip`_ using
``pip install tox``.

You are now ready to run Warehouse itself, run the tests, and build the
documentation.


Building the Warehouse Container
--------------------------------

.. note:: docker-compose is supported on only Python 2.x while warehouse runs
          on Python 3

Once you have Docker and Docker Compose installed, run:

.. code-block:: console

    $ docker-compose up

This will pull down all of the required docker containers, build
Warehouse and run all of the needed services. The Warehouse repository will be
mounted inside of the docker container at ``/app/``.


Running the Warehouse Container and Services
--------------------------------------------

After building the Docker container, you'll need to create a Postgres database
and run all of the data migrations. Helpfully, Docker Compose lets you run a
command inside of a new Docker container simply by running:

.. code-block:: console

    $ docker-compose run web <command>

Next, you will:

* create a new Postgres database,
* install example data to the Postgres database,
* run migrations, and
* load some example data from `Test PyPI <https://testpypi.python.org/>`_

Run:

.. code-block:: console

    $ docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
    $ xz -d -k dev/example.sql.xz
    $ docker-compose run web psql -h db -d warehouse -U postgres -v ON_ERROR_STOP=1 -1 -f dev/example.sql
    $ rm dev/example.sql
    $ docker-compose run web warehouse db upgrade head

If running the second command raises an error, you may need to install the `xz
library`. This is highly likely on Mac OS X and Windows.

If running the last command raises
``pkg_resources.DistributionNotFound: warehouse==15.0.dev0``,
run ``docker-compose run web pip install -e .`` and then retry. See
`Issue 501 <https://github.com/pypa/warehouse/issues/501>`_.


Viewing Warehouse in a browser
------------------------------

Web container is listening on port 80. If you're using boot2docker run
`boot2docker ip` to figure out the ip where the web container is listening. On
Linux it's accessible at ``http://localhost/``.


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

Errors when executing ``docker-compose up``
-------------------------------------------

* If the ``Dockerfile`` is edited or new dependencies are added (either by you
  or a prior pull request), a new container will need to built. A new container
  can be built by running ``docker-compose build``. This should be done before
  running ``docker-compose up`` again.

* If ``docker-compose up`` hangs after a new build, you should stop any
  running containers and repeat ``docker-compose up``.


Building Styles
===============

Styles are written in the scss variant of Sass and compiled using Gulp. To
install Gulp you will need to install `npm`_. Now you can tell npm to install
Gulp and all the necessary plugins:

.. code-block:: console

    $ npm install

To watch for changes to the .scss files and build the styles run this command:

.. code-block:: console

    $ ./node_modules/.bin/gulp watch


.. todo:: Make Docker do this


Running the Interactive Shell
=============================

There is an interactive shell available in Warehouse which will automatically
configure Warehouse and create a database session and make them available as
variables in the interactive shell.

To run the interactive shell, simply run:

.. code-block:: console

    $ warehouse shell

By default this command will attempt to detect the best interactive shell that
is available by looking for either bpython or IPython and then falling back to
a plain shell if neither of those are available. You can force the type of
shell that is used with the ``--type`` option.

The interactive shell will have the following variables defined in it:

====== ========================================================================
config The Pyramid ``Configurator`` object which has already been configured by
       Warehouse.
db     The SQLAlchemy ORM ``Session`` object which has already been configured
       to connect to the database.
====== ========================================================================


Running tests
=============

.. note:: PostgreSQL 9.4 is required because of pgcrypto extension

The Warehouse tests are found in the ``tests/`` directory and are designed to
be run using tox.

On Debian/Ubuntu systems, these packages must be installed to run the tests:

.. code-block:: console

    $ apt-get install libffi-dev libpq-dev python3-dev postgresql postgresql-contrib

To use `Nix <http://nixos.org/nix/>`_ run:

.. code-block:: console

    $ bash <(curl https://nixos.org/nix/install)
    $ nix-shell -p libffi postgresql94 python34

On Mac, you can install PostgreSQL with Homebrew.

.. code-block:: console

    $ brew install postgresql

To run all tests, all you have to do is:

.. code-block:: console

    $ tox
    ...
      py34: commands succeeded
      docs: commands succeeded
      pep8: commands succeeded
      packaging: commands succeeded
      congratulations :)

This will run the tests with the supported interpreter as well as all of the
additional testing that we require. You may not have all the required Python
versions installed, in which case you will see one or more
``InterpreterNotFound`` errors.


Building documentation
======================

The Warehouse documentation is stored in the ``docs/`` directory. It is written
in `reStructured Text`_ and rendered using `Sphinx`_.

Use `tox`_ to build the documentation. For example:

.. code-block:: console

    $ tox -e docs
    ...
    docs: commands succeeded
    congratulations :)

The HTML documentation index can now be found at
``docs/_build/html/index.html``.

.. _`tox`: https://pypi.python.org/pypi/tox
.. _`pip`: https://pypi.python.org/pypi/pip
.. _`sphinx`: https://pypi.python.org/pypi/Sphinx
.. _`reStructured Text`: http://sphinx-doc.org/rest.html
.. _`npm`: https://nodejs.org/
