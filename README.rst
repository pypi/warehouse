Warehouse
=========

.. image:: https://travis-ci.org/dstufft/warehouse.png?branch=master
   :target: https://travis-ci.org/dstufft/warehouse

.. image:: https://coveralls.io/repos/dstufft/warehouse/badge.png?branch=master
   :target: https://coveralls.io/r/dstufft/warehouse?branch=master


Warehouse is a next generation Python Package Repository designed to replace
the legacy code base that currently powers `PyPI <https://pypi.python.org>`_.

Setting up a development environment
------------------------------------

Warehouse requires an operating PostgreSQL server running version 9.2 or later.
The default development configuration shipped as part of this repository
assumes that you have it running locally, with a database named ``warehouse``,
and that no password is required.

To work on Warehouse you can gain a checkout of the repository and run the
development web server using:

1. Get a checkout of the source

.. code:: bash

    $ git clone https://github.com/dstufft/warehouse.git warehouse


2. Install the requirements

.. code:: bash

    $ pip install -r requirements.txt

3. Run the development server

.. code:: bash

    $ warehouse -c dev/config.yml serve


Running the tests
-----------------

Warehouse uses tox to run the test suite. You can run all the tests by using:

.. code:: bash

    $ tox


Contributing
------------

Currently focusing on modeling and reconstructing the data from the current
PyPI database. Pull Requests that are not focused on that are likely to be
declined.

1. Fork the `repository`_ on GitHub.
2. Make a branch off of master and commit your changes to it.
3. Ensure that your name is added to the end of the AUTHORS file using the
   format ``Name <email@domain.com> (url)``, where the ``(url)`` portion is
   optional.
4. Submit a Pull Request to the master branch on GitHub.

.. _repository: https://github.com/dstufft/warehouse
