Warehouse
=========

.. image:: https://travis-ci.org/dstufft/warehouse.png?branch=master
   :target: https://travis-ci.org/dstufft/warehouse

.. image:: https://coveralls.io/repos/dstufft/warehouse/badge.png?branch=master
   :target: https://coveralls.io/r/dstufft/warehouse?branch=master


Warehouse is a reimplementation of the Python Package Index using modern
web development frameworks and methodologies.

Setting up a development environment
------------------------------------

Warehouse requires Redis and PostgreSQL and by default will assume they are
running locally and are configured to not require passwords.

1. Get a checkout of the source

.. code:: bash

    $ git clone git@github.com:dstufft/warehouse.git warehouse

2. Install the requirements

.. code:: bash

    $ pip install -r requirements.txt

3. *(Optional)* Create a configuration file

.. code:: bash

    $ warehouse init config.py

4. Start the development server

.. code:: bash

    # If you created a configuration file in 3.
    $ warehouse runserver --settings=config --configuration=Development

    # If you want to use the default development configuration
    $ warehouse runserver --settings=configs.dev --configuration=Development

    # If you have the excellent envdir library installed and you want to use
    # the default configurations
    $ envdir configs/env warehouse runserver


Running the tests
-----------------

Warehouse uses pytest to run the test suite. You can run all the tests by using:

.. code:: bash

    $ invoke tests

Unit and functional tests have been marked and you may run either of by using:

.. code:: bash

    # Run only the unit tests
    $ invoke tests -s unit

    # Run only the functional tests
    $ invoke tests -s functional


Contributing
------------

Currently focusing on modeling and importing the data from the current PyPI
database. Pull Requests that are not focused on that are likely to be declined.
Once the project has matured and is more open to external contributions, it
will be migrated to the `Python Packaging Authority`_ account.

1. Fork the `repository`_ on GitHub.
2. Make a branch off of master and commit your changes to it.
3. Ensure that your name is added to the end of the CONTRIBUTORS file using the
   format ``Name <email@domain.com> (url)``, where the ``(url)`` portion is
   optional.
4. Submit a Pull Request to the master branch on GitHub.

.. _Python Packaging Authority: https://github.com/pypa/
.. _repository: https://github.com/dstufft/warehouse
