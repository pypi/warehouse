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

* Documentation upload: Users can no longer use ``doc_upload`` in the
  API to upload documentation ZIP files, separate from packages, to be
  hosted at pythonhosted.org (`discussion
  <https://github.com/pypa/warehouse/issues/509>`_).

* All APIs: `access is HTTPS-only
  <https://mail.python.org/pipermail/distutils-sig/2017-October/031712.html>`_
  (changed in October 2017). And pypi.org honors an ``Accept-Encoding:
  gzip`` header, whereas pypi.python.org ignored it.

* JSON API: ``https://pypi.org/pypi/{name}/json`` returns the
  expected JSON response directly. See :doc:`json`.

* XML-RPC API: see :ref:`changes-to-legacy-api`.

* Packages/updates RSS feeds: ``https://pypi.org/pypi?%3Aaction=rss``
  redirects to ``https://pypi.org/rss/updates.xml``, and
  ``https://pypi.org/pypi?%3Aaction=packages_rss`` redirects to
  ``https://pypi.org/rss/packages.xml``. See :doc:`feeds` for
  descriptions. `The data differs from the legacy feed data because
  the new feeds are standards-compliant and fix inaccuracies in the
  publication date <https://github.com/pypa/warehouse/issues/3238>`_.

* Subscribe to `the PyPI announcement list (low-traffic)
  <https://mail.python.org/mm3/mailman3/lists/pypi-announce.python.org/>`_.

If you're a PyPI end user or packager looking to migrate to the new
PyPI, please see `the official Python Packaging User Guide on
migrating to PyPI
<https://packaging.python.org/guides/migrating-to-pypi-org/>`_.
