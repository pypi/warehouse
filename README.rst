Warehouse
=========

Warehouse is a next-generation Python Package Repository that powers
`PyPI`_. See `our development roadmap`_, `documentation`_, and
`architectural overview`_.

Getting Started
---------------

You can run Warehouse locally in a development environment using
``docker`` and ``docker-compose``. See `Getting started`_
documentation for instructions on how to set it up.

The canonical deployment of Warehouse is in production at `pypi.org`_.

Discussion
----------

If you run into bugs, you can file them in our `issue tracker`_.

You can also file specific types of issues:

- `Good First Issue`_: An easy issue reserved for people who haven't
  contributed before
- `Visual Design Issue`_: An issue related to the visual design of the site
- `Trove Classifier Issue`_: A request for a new trove classifier

You can also join the chat channels ``#pypa`` (general packaging
discussion and user support) and ``#pypa-dev`` (discussion about
development of packaging tools) `on Freenode`_, or the `pypa-dev
mailing list`_, to ask questions or get involved.

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
rooms, and mailing lists is expected to follow the `PyPA Code of Conduct`_.

.. _`PyPI`: https://pypi.org/
.. _`our development roadmap`: https://wiki.python.org/psf/WarehouseRoadmap
.. _`architectural overview`: https://warehouse.readthedocs.io/application/
.. _`documentation`: https://warehouse.readthedocs.io
.. _`Getting started`: https://warehouse.readthedocs.io/development/getting-started/
.. _`issue tracker`: https://github.com/pypa/warehouse/issues
.. _`pypi.org`: https://pypi.org/
.. _`Good First Issue`: https://github.com/pypa/warehouse/issues/new?template=good-first-issue.md
.. _`Visual Design Issue`: https://github.com/pypa/warehouse/issues/new?template=visual-design.md
.. _`Trove Classifier Issue`: https://github.com/pypa/warehouse/issues/new?title=Request+trove+classifier&template=new-trove-classifier.md
.. _`on Freenode`: https://webchat.freenode.net/?channels=%23pypa-dev,pypa
.. _`pypa-dev mailing list`: https://groups.google.com/forum/#!forum/pypa-dev
.. _`Running tests and linters section`: https://warehouse.readthedocs.io/development/getting-started/#running-tests-and-linters
.. _BrowserStack: https://browserstack.com/
.. _`supported browsers`: https://warehouse.readthedocs.io/development/frontend/#browser-support
.. |BrowserStackImg| image:: docs/_static/browserstack-logo.png
.. _BrowserStackImg: https://browserstack.com/
.. _`PyPA Code of Conduct`: https://www.pypa.io/en/latest/code-of-conduct/
