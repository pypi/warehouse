Warehouse
=========

.. image:: https://readthedocs.org/projects/warehouse/badge/?version=latest
    :target: https://warehouse.readthedocs.org/
    :alt: Latest Docs

.. image:: https://travis-ci.org/pypa/warehouse.svg?branch=master
    :target: https://travis-ci.org/pypa/warehouse

.. image:: http://codecov.io/github/pypa/warehouse/coverage.svg?branch=master
    :target: http://codecov.io/github/pypa/warehouse?branch=master

.. image:: https://requires.io/github/pypa/warehouse/requirements.svg?branch=master
     :target: https://requires.io/github/pypa/warehouse/requirements/?branch=master
     :alt: Requirements Status

Warehouse is a next generation Python Package Repository designed to replace
the legacy code base that currently powers `PyPI <https://pypi.python.org/>`_.

You can find more information in the `documentation`_.

Getting Started
---------------

Running a copy of Warehouse locally requires using ``docker`` and
``docker-compose``. Assuming you have those two items, here are a number of
commands you can use:

.. code-block:: console

    $ # Start up a local environment
    $ make serve
    $ # Initialize the database and fill it with test data
    $ make initdb
    $ # Run the tests
    $ make tests
    $ # Build the documentation
    $ make docs
    $ # Run the various linters
    $ make lint


Discussion
----------

If you run into bugs, you can file them in our `issue tracker`_.

You can also join ``#pypa`` or ``#pypa-dev`` on Freenode to ask questions or
get involved.


.. _`documentation`: https://warehouse.readthedocs.org/
.. _`issue tracker`: https://github.com/pypa/warehouse/issues


Code of Conduct
---------------

Everyone interacting in the Warehouse project's codebases, issue trackers, chat
rooms, and mailing lists is expected to follow the `PyPA Code of Conduct`_.

.. _PyPA Code of Conduct: https://www.pypa.io/en/latest/code-of-conduct/
