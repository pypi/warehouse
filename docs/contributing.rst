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

Finally you can setup a dev environment and run the dev server:

.. code-block:: console

    $ ./dev-setup-env
    $ ./dev-start-server


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

This runs the tests with the default Python interpreter and require that the
local user has the necessary privileges to create the test database (named
``warehouse_unittest``). This is easy to set up by creating a PostgreSQL user
account matching the local user and giving it the ``CREATEDB`` privilege.

Alternatively you can create the test database beforehand and set the
``WAREHOUSE_DATABASE_URL`` environment variable to point to it. In that case,
you have to manually drop the database after running the tests.

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


Writing Tests
-------------

See :doc:`testing` for more information about writing tests.


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
