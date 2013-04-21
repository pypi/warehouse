Warehouse
=========

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

    $ py.test

Unit and functional tests have been marked and you may run either of by using:

..code:: bash

    # Run only the unit tests
    $ py.test -m unit

    # Run only the functional tests
    $ py.test -m functional
