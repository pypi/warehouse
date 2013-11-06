Contributing
============

Process
-------

As an open source project, Warehouse welcomes contributions of all
forms. These can include:

* Bug reports and feature requests
* Pull requests for both code and documentation
* Patch reviews

You can file bugs and submit pull requests on `GitHub`_.


Code
----

When in doubt, refer to `PEP 8`_ for Python code.

Every code file must start with the boilerplate notice of the Apache License.
Additionally, every Python code file must contain

.. code-block:: python

    from __future__ import absolute_import, division, print_function
    from __future__ import unicode_literals


Development Environment
-----------------------

Workong on Warehouse requires the installation of a few external non Python
dependencies. These are:

* PostgreSQL 9.2+
* Redis
* Elasticsearch
* Compass (Only for design development)
* Wake (Only for design development)

Once you have all of the above you can install Warehouse, all of it's
dependencies, and the Python development dependencies using:

.. code-block:: console

    $ pip install -r requirements.txt

Finally you can setup the project:

..code-block:: console

    $ # Create a Database
    $ createdb warehouse
    $ # Install the CIText extension
    $ psql warehouse -c "CREATE EXTENSION IF NOT EXISTS citext"
    $ # Migrate the database to the latest schema
    $ warehouse -c dev/config.yml migrate upgrade head
    $ # Serve Warehouse at http://localhost:9000/
    $ warehouse -c dev/config.yml serve


Running Tests
-------------

Warehouse unit tests are found in the ``tests/`` directory and are designed to
be run using `pytest`_. `pytest`_ will discover the tests automatically, so all
you have to do is:

.. code-block:: console

    $ py.test

This runs the tests with the default Python interpreter and require an empty
database to exist named test_warehouse by default. The name of the test
database may be overridden using the ``WAREHOUSE_DATABASE_URL`` environment
variable.

You can also verify that the tests pass on other supported Python interpreters.
For this we use `tox`_, which will automatically create a `virtualenv`_ for
each supported Python version and run the tests. For example:

.. code-block:: console

   $ tox
   ...
    py27: commands succeeded
   ERROR:   pypy: InterpreterNotFound: pypy
    docs: commands succeeded
    pep8: commands succeeded

You may not have all the required Python versions installed, in which case you
will see one or more ``InterpreterNotFound`` errors.

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


.. _`GitHub`: https://github.com/dstufft/warehouse
.. _`PEP 8`: http://www.peps.io/8/
.. _`syntax`: http://sphinx-doc.org/domains.html#info-field-lists
.. _`pytest`: https://pypi.python.org/pypi/pytest
.. _`tox`: https://pypi.python.org/pypi/tox
.. _`virtualenv`: https://pypi.python.org/pypi/virtualenv
.. _`pip`: https://pypi.python.org/pypi/pip
.. _`sphinx`: https://pypi.python.org/pypi/sphinx
.. _`reStructured Text`: http://docutils.sourceforge.net/rst.html
