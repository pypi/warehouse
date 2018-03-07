Integration guide
=================

We provide multiple APIs to help you integrate with PyPI; see
:doc:`index`.


Migrating to the new PyPI
-------------------------

If your site/service used to link or upload to pypi.python.org, you
should start using pypi.org instead.

Here are some tips.

.. note::
  ``{name}`` is the name of the package as represented in the URL;
  for ``https://pypi.org/project/arrow/``, you'd insert ``arrow``
  wherever you see ``{name}``.

* If your client correctly follows redirects, you can replace
  ``pypi.python.org`` in your links with ``pypi.org`` and everything
  should just work. ``https://pypi.org/pypi/{name}`` (with or
  without a trailing slash) redirects to
  ``https://pypi.org/project/{name}/``.

* In case you prefer a shorter URL: feel free to link to
  ``https://pypi.org/p/{name}/``, which will redirect to
  ``https://pypi.org/project/{name}/``.

* JSON API: ``https://pypi.org/pypi/{name}/json`` returns the
  expected JSON response directly -- see :doc:`json`.

* Package upload RSS feed: ``https://pypi.org/pypi?%3Aaction=rss``
  redirects to ``https://pypi.org/rss/updates.xml``. See
  :doc:`feeds`.

If you're a PyPI end user or packager looking to migrate to the new
PyPI, please see `the official Python Packaging User Guide on
migrating to PyPI
<https://packaging.python.org/guides/migrating-to-pypi-org/>`_.
