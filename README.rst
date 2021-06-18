
Warehouse
=========

Warehouse is the software that powers `PyPI`_.
See `our development roadmap`_, `documentation`_, and
`architectural overview`_.

Getting Started
---------------

You can run Warehouse locally in a development environment using
``docker`` and ``docker-compose``. See `Getting started`_
documentation for instructions on how to set it up.

The canonical deployment of Warehouse is in production at `pypi.org`_.

Discussion
----------


You can find help or get involved on:

- `Github issue tracker`_ for reporting issues
- IRC: on `Libera`_, channel ``#pypa`` for general packaging discussion
  and user support, and ``#pypa-dev`` for
  discussions about development of packaging tools
- The `PyPA Discord`_ for live discussions
- The Packaging category on `Discourse`_ for discussing
  new ideas and community initiatives


Testing
----------

Read the `running tests and linters section`_ of our documentation to
learn how to test your code.  For cross-browser testing, we use an
open source account from `BrowserStack`_. If your pull request makes
any change to the user interface, it will need to be tested to confirm
it works in our `supported browsers`_.

|BrowserStackImg|_

Code of Conduct
---------------

Everyone interacting in the Warehouse project's codebases, issue trackers, chat
rooms, and mailing lists is expected to follow the `PSF Code of Conduct`_.

.. _`PyPI`: https://pypi.org/
.. _`our development roadmap`: https://warehouse.readthedocs.io/roadmap/
.. _`architectural overview`: https://warehouse.readthedocs.io/application/
.. _`documentation`: https://warehouse.readthedocs.io
.. _`Getting started`: https://warehouse.readthedocs.io/development/getting-started/
.. _`Github issue tracker`: https://github.com/pypa/warehouse/issues
.. _`pypi.org`: https://pypi.org/
.. _`distutils-sig mailing list`: https://mail.python.org/mailman3/lists/distutils-sig.python.org/
.. _`Running tests and linters section`: https://warehouse.readthedocs.io/development/getting-started/#running-tests-and-linters
.. _BrowserStack: https://browserstack.com/
.. _`supported browsers`: https://warehouse.readthedocs.io/development/frontend/#browser-support
.. |BrowserStackImg| image:: docs/_static/browserstack-logo.png
.. _BrowserStackImg: https://browserstack.com/
.. _`PSF Code of Conduct`: https://github.com/pypa/.github/blob/main/CODE_OF_CONDUCT.md
.. _`Libera`: https://web.libera.chat/#pypa,#pypa-dev
.. _`PyPA Discord`: https://discord.gg/pypa
.. _`Discourse`: https://discuss.python.org/c/packaging/14
