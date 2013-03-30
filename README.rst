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

3. Create a local configuration file

.. code:: bash

    $ warehouse init config.yaml

3. Start the development server

.. code:: bash

    $ warehouse runserver -c local.yaml

4. Run the tests

.. code:: bash

    $ py.test
