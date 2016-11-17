Warehouse
=========

Warehouse is a next generation Python Package Repository designed to replace
the legacy code base that currently powers `PyPI <https://pypi.python.org/>`_
(whose source code `lives on Github <https://github.com/pypa/pypi-legacy/>`_).

You can find more information in the `documentation`_.

Getting Started
---------------

Running a copy of Warehouse locally requires using ``docker`` and
``docker-compose``. Assuming you have those two items, here are a number of
commands you can use:

.. code-block:: console

    # Start up a local environment
    make serve
    # Start up a local environment in debug mode (pdb enabled)
    make debug
    # Initialize the database and fill it with test data
    make initdb
    # Run the tests
    make tests
    # Build the documentation
    make docs
    # Run the various linters
    make lint

.. note:: reCaptcha is featured in authentication and registration pages. To
          enable it, pass ``RECAPTCHA_SITE_KEY`` and ``RECAPTCHA_SECRET_KEY``
          through to ``serve`` and ``debug`` targets.


Discussion
----------

If you run into bugs, you can file them in our `issue tracker`_.

You can also join ``#pypa`` or ``#pypa-dev`` on Freenode to ask questions or
get involved.


.. _`documentation`: https://warehouse.readthedocs.io/
.. _`issue tracker`: https://github.com/pypa/warehouse/issues


Code of Conduct
---------------

Everyone interacting in the Warehouse project's codebases, issue trackers, chat
rooms, and mailing lists is expected to follow the `PyPA Code of Conduct`_.

.. _PyPA Code of Conduct: https://www.pypa.io/en/latest/code-of-conduct/
