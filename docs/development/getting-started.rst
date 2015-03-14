Getting started
===============

Working on Warehouse requires the installation of
`Docker Compose <https://docs.docker.com/compose/>`_, which Warehouse uses to
automate setting up a development environment that includes all of the required
external services. You can install Docker Compose using their provided
`installation instructions <https://docs.docker.com/compose/install/>`_.

Once you have Docker Compose installed, you also want to have `tox`_ installed.
This is a Python program which can be installed simply with `pip`_ using
``pip install tox``.

You are now ready to run Warehouse itself, run the tests, and build the
documentation.


Running Warehouse
~~~~~~~~~~~~~~~~~

Once you have Docker and Docker Compose installed, all you'll need to do is
run:

.. code-block:: console

    $ docker-compose up

This will pull down all of the required docker containers, build one for
Warehouse and run all of the needed services. The Warehouse repository will be
mounted inside of the docker container at ``/app/``.

Once you have all of the services running, you'll need to create a database and
run all of the migrations. Docker Compose will enable you to run a command
inside of a new docker container simply by running:

.. code-block:: console

    $ docker-compose run web <command>

In particular, you can create a new database, run migrations, and load some
example data by running:

.. code-block:: console

    $ docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
    $ docker-compose run web warehouse -c dev/config.yml db upgrade head
    $ xz -d -k dev/example.sql.xz
    $ docker-compose run web psql -h db -d warehouse -U postgres -f dev/example.sql
    $ rm dev/example.sql

The repository is exposed inside of the web container at ``/app/`` and
Warehouse will automatically reload when it detects any changes made to the
code. However editing the ``Dockerfile`` or adding new dependencies will
require building a new container which can be done by running
``docker-compose build`` before running ``docker-compose up`` again.

The example data located in ``dev/example.sql.xz`` is taken from
`Test PyPI <https://testpypi.python.org/>`_ and has been sanitized to remove
anything private. The password for every account has been set to the string
``password``.


Interactive Shell
~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~

The Warehouse tests are found in the ``tests/`` directory and are designed to
be run using tox. To run all of the tests all you have to do is:

.. code-block:: console

    $ tox
    ...
      py34: commands succeeded
      docs: commands succeeded
      pep8: commands succeeded
      packaging: commands succeeded
      congratulations :)

This will run the tests with the suported interpreter as well as all of the
additional testing that we require. You may not have all the required Python
versions installed, in which case you will see one or more
``InterpreterNotFound`` errors.


Building documentation
~~~~~~~~~~~~~~~~~~~~~~

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
