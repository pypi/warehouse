Warehouse
=========

.. image:: https://travis-ci.org/dstufft/warehouse.png?branch=master
   :target: https://travis-ci.org/dstufft/warehouse


Warehouse is a next generation Python Package Repository designed to replace
the legacy code base that currently powers `PyPI <https://pypi.python.org>`_.

Setting up a development environment
------------------------------------

Warehouse requires an operating PostgreSQL server running version 9.2 or later.
The default development configuration shipped as part of this repository
assumes that you have it running locally, with a database named ``warehouse``,
and that no password is required.

You may have to enable `CITEXT <http://www.postgresql.org/docs/9.2/static/citext.html>`_ extension:

.. code:: bash

    $ psql warehouse -c "CREATE EXTENSION IF NOT EXISTS citext"

Warehouse also uses less.css. This is typically installed using (for the
easiest, global installation)

.. code:: bash

    npm install -g less

This will probably mean you need to install node.js as well. "brew install
node" on OS X or whatever on other platforms.

To work on Warehouse you can gain a checkout of the repository and run the
development web server using:


1. Get a checkout of the source

.. code:: bash

    $ git clone https://github.com/dstufft/warehouse.git warehouse && cd warehouse

2. Create `virtualenv`

.. code:: bash

    $ virtualenv .

3. Install the requirements

.. code:: bash

    $ bin/pip install -r requirements.txt

4. Populate database

.. code:: bash

    $ bin/warehouse -c dev/config.yml migrate upgrade head


5. Run the development server

.. code:: bash

    $ bin/warehouse -c dev/config.yml serve

6. Open browser at `http://localhost:9000/ <http://localhost:9000/>`_


Running the tests
-----------------

Warehouse uses tox to run the test suite. You can run all the tests by using:

.. code:: bash

    $ tox


Resources
---------

* `Documentation <https://warehouse.readthedocs.org/>`_
* `IRC <http://webchat.freenode.net?channels=%23warehouse>`_
  (#warehouse - irc.freenode.net)


Contributing
------------

1. Fork the `repository`_ on GitHub.
2. Make a branch off of master and commit your changes to it.
3. Ensure that your name is added to the end of the AUTHORS file using the
   format ``Name <email@domain.com> (url)``, where the ``(url)`` portion is
   optional.
4. Submit a Pull Request to the master branch on GitHub.

.. _repository: https://github.com/dstufft/warehouse
