#############
Documentation
#############

Developer documentation
=======================

The developer documentation is hosted at `warehouse.pypa.io`_. It's written in
`reStructuredText`_ or `Markdown`_ (via `MyST`_) and built using
`Sphinx`_.

.. _warehouse.pypa.io: https://warehouse.pypa.io
.. _reStructuredText: https://docutils.sourceforge.io/rst.html
.. _Markdown: https://www.markdownguide.org/
.. _MyST: https://myst-parser.readthedocs.io/en/latest/
.. _Sphinx: https://www.sphinx-doc.org/

.. _dev-docs-layout:

Layout
------

The developer documentation is located in the ``docs/dev`` directory.

.. _dev-docs-local-dev:

Local development
-----------------

To run a single local build of the dev docs, you can use the ``dev-docs``
Makefile target:

.. code-block:: console

    make dev-docs

That will produce a local build under ``docs/dev/_build/``.

To run a local development server, you can use ``docker compose``:

.. code-block:: console

    docker compose up dev-docs

Once running, you can visit a local build of the pages at `localhost:10002`_.

.. _localhost\:10002: http://localhost:10002

User documentation
==================

The user documentation is hosted at `docs.pypi.org`_. It's written in
`Markdown`_ and built using `MkDocs`_.

.. _docs.pypi.org: https://docs.pypi.org
.. _MkDocs: https://www.mkdocs.org/

.. _user-docs-layout:

Layout
------

The user documentation is located in the ``docs/user`` directory.

.. _user-docs-local-dev:

Local development
-----------------

To run a single local build of the user docs, you can use the ``user-docs``
Makefile target:

.. code-block:: console

    make user-docs

That will produce a local build under ``docs/user-site/``.

To run a local development server, you can use ``docker compose``:

.. code-block:: console

    docker compose up user-docs

Once running, you can visit a local build of the user documentation at `localhost:10000`_.

.. _localhost\:10000: http://localhost:10000

PyPI blog
=========

The PyPI blog is hosted at `blog.pypi.org`_. Like the user documentation,
it's written in `Markdown`_ and built using `MkDocs`_.

.. _blog.pypi.org: https://blog.pypi.org

.. _blog-layout:

Layout
------

The blog is located in the ``docs/blog`` directory.

.. _blog-local-dev:

Local development
-----------------

To run a single local build of the blog, you can use the ``blog``
Makefile target:

.. code-block:: console

    make blog

That will produce a local build under ``docs/blog-site/``.

To run a local development server, you can use ``docker compose``:

.. code-block:: console

    docker compose up blog

Once running, you can visit a local build of the blog at `localhost:10001`_.

.. _localhost\:10001: http://localhost:10001
