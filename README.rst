Warehouse
=========

Warehouse is a reimplementation of the Python Package Index using modern
web development frameworks and methodologies.

Its current focus is on modeling and importing the data from the current
database and Pull Requests not focused on that are likely to be declined. Once
the project has matured and is more open to external contributions, it will be
migrated to the `Python Packaging Authority`_ account.

.. _Python Packaging Authority: https://github.com/pypa/

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
