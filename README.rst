Warehouse
=========

Warehouse is a next generation Python Package Repository designed to replace
the legacy code base that currently powers `PyPI <https://pypi.python.org/>`_.


Running Locally
---------------

Warehouse has a local development environment which uses
`fig.sh <http://www.fig.sh/>`_ to run all of the required services such as
Warehouse itself, `PostgreSQL <http://www.postgresql.org/>`_, and
`redis <http://redis.io/>`_.


Install fig.sh
~~~~~~~~~~~~~~

First you'll need to `install fig.sh <http://www.fig.sh/install.html>`_ and
ensure it can connect to a Docker host. If you're running on OSX you may wish
to use the `Docker installer <https://docs.docker.com/installation/mac/>`_ to
install both docker and boot2docker.


Running Warehouse
~~~~~~~~~~~~~~~~~

Once you have Docker and fig.sh installed, all you'll need to do is run:

.. code-block:: console

    $ fig up

This will pull down all of the required docker containers, build one for
Warehouse and run all of the needed services. The Warehouse repository will be
mounted inside of the docker container at ``/app/``.

Once you have all of the services running, you'll need to create a database and
run all of the migrations. Fig will enable you to run a command inside of a
new docker container simply by running:

.. code-block:: console

    $ fig run web <command>

In particular, you can create a new database and run the migrations by running:

.. code-block:: console

    $ fig run web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
    $ fig run web warehouse -c dev/config.yml db upgrade head

The repository is exposed inside of the web container at ``/app/`` and
Warehouse will automatically reload when it detects any changes made to the
code. However editing the ``Dockerfile`` or adding new dependencies will
require building a new container which can be done by running ``fig build``
before running ``fig up`` again.


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
