Integration guide
=================

We provide multiple APIs to help you integrate with PyPI; see
:doc:`index`.

Many tools already integrate with PyPI, uploading packages or
retrieving data; see `the Python Packaging Guide's tool
recommendations
<https://packaging.python.org/guides/tool-recommendations/>`_.


Migrating to the new PyPI
-------------------------

Warehouse has now replaced `the legacy PyPI site that was deployed at
pypi.python.org <https://pypi.python.org/>`_. If your site/service
used to link or upload to pypi.python.org, it may continue to work due
to redirects, but you should use pypi.org instead.

You should also watch `our status page <https://status.python.org/>`__
and subscribe to `the PyPI announcement list (low-traffic)
<https://mail.python.org/mm3/mailman3/lists/pypi-announce.python.org/>`_
to find out about future changes.

Here are some tips.

.. note::
  ``{name}`` is the name of the package as represented in the URL;
  for ``https://pypi.org/project/arrow/``, you'd insert ``arrow``
  wherever you see ``{name}``.

* If your client correctly follows redirects, you can replace
  ``pypi.python.org`` in your links with ``pypi.org`` and everything
  should just work. For instance, the project detail page
  ``https://pypi.org/pypi/{name}`` (with or without a trailing slash)
  redirects to ``https://pypi.org/project/{name}/``.

* Shorter URL: ``https://pypi.org/p/{name}/`` will redirect to
  ``https://pypi.org/project/{name}/``.

* All APIs: `access is HTTPS-only
  <https://mail.python.org/pipermail/distutils-sig/2017-October/031712.html>`_
  (changed in October 2017). And pypi.org honors an ``Accept-Encoding:
  gzip`` header, whereas pypi.python.org ignored it.

* JSON API: ``https://pypi.org/pypi/{name}/json`` returns the
  expected JSON response directly. See :doc:`json`.

* XML-RPC API: see :ref:`changes-to-legacy-api`. Will be deprecated in
  the future (no specific end date set yet); switch to the RSS or JSON
  APIs. If you depend on an XML-RPC call that our other APIs do not
  support, please `tell us <https://pypi.org/help/#feedback>`_.

* Packages/updates RSS feeds: ``https://pypi.org/pypi?%3Aaction=rss``
  redirects to ``https://pypi.org/rss/updates.xml``, and
  ``https://pypi.org/pypi?%3Aaction=packages_rss`` redirects to
  ``https://pypi.org/rss/packages.xml``. See :doc:`feeds` for
  descriptions. `The data differs from the legacy feed data because
  the new feeds are standards-compliant and fix inaccuracies in the
  publication date <https://github.com/pypa/warehouse/issues/3238>`_.

* Documentation upload: Users can no longer use ``doc_upload`` in the
  API to upload documentation ZIP files, separate from packages, to be
  hosted at pythonhosted.org (`discussion
  <https://github.com/pypa/warehouse/issues/509>`_).

* ``User-Agent`` Filtering: Some client user agents were filtered to
  always use ``legacy.pypi.org``, a temporary deployment of the legacy
  PyPI codebase, regardless of brownouts or redirects, in order to
  give them extra time to migrate. On 30 April 2018,
  ``legacy.pypi.org`` was shut down, so all clients use ``pypi.org``
  regardless of their ``User-Agent``.

* Subscribe to `the PyPI announcement list (low-traffic)
  <https://mail.python.org/mm3/mailman3/lists/pypi-announce.python.org/>`_.

If you're a PyPI end user or packager looking to migrate to the new
PyPI, please see `the official Python Packaging User Guide on
migrating to PyPI
<https://packaging.python.org/guides/migrating-to-pypi-org/>`_.
