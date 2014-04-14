Contributing
============

Process
-------

As an open source project, Warehouse welcomes contributions of many forms.
Contributions can include:

* Bug reports and feature requests
* Pull requests for both code and documentation
* Patch reviews

You can file bugs and submit pull requests on `GitHub`_.


Code
----

When in doubt, refer to `PEP 8`_ for Python code.

Every code file must start with the boilerplate notice of the Apache License.


SQL
---

SQL statements should use uppercase statement names and lowercase names for
tables, columns, etc. If a SQL statement must be split over multiple lines
it should use

.. code-block:: python

    query = \
        """ SELECT *
            FROM table_name
            WHERE foo != 'bar'
        """

Furthermore, you *MUST* use parametrized queries and should use the named
interpolation format (``%(foo)s``) instead of the positional interpolation
format (``%s``).


Development Environment
-----------------------

Warehouse development requires Python3.4 and the installation of several external non-Python
dependencies. These are:

* `PostgreSQL`_ 9.2+
* `Redis`_
* `Elasticsearch`_
* `Compass`_ (used only for design development)
* `Grunt`_ (used only for design development)

Once you have all of the above you can install Warehouse, all of its install
dependencies, and the Python development dependencies using:

.. code-block:: console

    $ pip install -r dev-requirements.txt

Finally you can setup the project:

.. code-block:: console

    $ # Create a Database
    $ createdb warehouse

    $ # Install the CIText extension
    $ psql warehouse -c 'CREATE EXTENSION IF NOT EXISTS citext'

    $ # Install the UUID extension
    $ psql warehouse -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'

    $ # Migrate the database to the latest schema
    $ warehouse -c dev/config.yml migrate upgrade head

    $ # Serve Warehouse at http://localhost:9000/
    $ warehouse -c dev/config.yml serve


Design Development
------------------

Warehouse design development uses `Compass`_ and `Grunt`_ as its asset
pipeline. You can install the required dependencies by running:

.. code-block:: console

    $ # Install Compass
    $ gem install compass

    $ # Install Grunt
    $ npm install

Once you have the dependencies install you can iterate on the theme by editing
the files located in ``warehouse/static/source``. After each edit you'll need
to compile the files by running:

.. code-block:: console

    $ grunt

If you're iterating on the design and wish to have the compilation step called
automatically you can watch the ``warehouse/static/source`` directory for
changes and auto-compile by running:

.. code-block:: console

    $ grunt watch


Running Tests
-------------

Warehouse unit tests are found in the ``tests/`` directory and are designed to
be run using `pytest`_. `pytest`_ will discover the tests automatically, so all
you have to do is:

.. code-block:: console

    $ py.test

This runs the tests with the default Python interpreter and require an empty
database to exist named ``test_warehouse`` by default. The name of the test
database may be overridden using the ``WAREHOUSE_DATABASE_URL`` environment
variable.

You can also verify that the tests pass on other supported Python interpreters.
For this we use `tox`_, which will automatically create a `virtualenv`_ for
each supported Python version and run the tests.  For example:

.. code-block:: console

   $ tox
   ...
    py34: commands succeeded
    docs: commands succeeded
    pep8: commands succeeded

You may not have all the required Python versions installed, in which case you
will see one or more ``InterpreterNotFound`` errors.

If you want to run all of the tests except the ones that do not need the
database, you can run:

.. code-block:: console

    $ tox -e py34 -- -k "not db"

By default the database driven tests will attempt to create an isolated
PostgreSQL instance using ``initdb`` and ``postgres`` which it will tear down
at the end of the test run. If you wish to specify an already running
PostgreSQL instead of this, you can simply do:

.. code-block:: console

    $ # via command line
    $ tox -e py34 -- --database-url postgresql:///test_warehouse
    $ $ via environment variable
    $ WAREHOUSE_DATABASE_URL='postgresql:///test_warehouse' tox -e py34


Building Documentation
----------------------

Warehouse documentation is stored in the ``docs/`` directory. It is written in
`reStructured Text`_ and rendered using `Sphinx`_.

Use `tox`_ to build the documentation. For example:

.. code-block:: console

   $ tox -e docs
   ...
   docs: commands succeeded
   congratulations :)

The HTML documentation index can now be found at ``docs/_build/html/index.html``


.. _`GitHub`: https://github.com/pypa/warehouse
.. _`PEP 8`: http://www.peps.io/8/
.. _`PostgreSQL`: https://github.com/postgres/postgres
.. _`Redis`: https://github.com/antirez/redis
.. _`Elasticsearch`: http://www.elasticsearch.org/
.. _`Compass`: https://github.com/chriseppstein/compass
.. _`Grunt`: http://gruntjs.com/
.. _`syntax`: http://sphinx-doc.org/domains.html#info-field-lists
.. _`pytest`: https://pypi.python.org/pypi/pytest
.. _`tox`: https://pypi.python.org/pypi/tox
.. _`virtualenv`: https://pypi.python.org/pypi/virtualenv
.. _`pip`: https://pypi.python.org/pypi/pip
.. _`sphinx`: https://pypi.python.org/pypi/sphinx
.. _`reStructured Text`: http://docutils.sourceforge.net/rst.html
