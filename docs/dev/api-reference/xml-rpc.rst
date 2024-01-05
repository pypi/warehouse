
PyPI's XML-RPC methods
======================

.. warning::
   The XML-RPC API will be deprecated in the future. Use of this API is not
   recommended, and existing consumers of the API should migrate to the RSS
   and/or JSON APIs instead.

   As a result, this API has a very restrictive rate limit and it may be
   necessary to pause between successive requests.

   Users of this API are **strongly** encouraged to subscribe to the
   pypi-announce_ mailing list for notices as we begin the process of removing
   XML-RPC from PyPI.

Example usage (Python 3)::

  >>> import xmlrpc.client
  >>> import pprint
  >>> import time
  >>> client = xmlrpc.client.ServerProxy('https://pypi.org/pypi')
  >>> client.package_releases('roundup')
  ['1.6.0']
  >>> time.sleep(1)  # Sleep to avoid rate limit
  >>> pprint.pprint(client.release_urls('roundup', '1.6.0'))
  [{'comment_text': '',
  'digests': {'md5': '54d587da7c3d9c83f13d04674cacdc2a',
              'sha256': '1814c74b40c4a6287e0a97b810f6adc6a3312168201eaa0badd1dd8c216b1bcb'},
  'downloads': -1,
  'filename': 'roundup-1.6.0.tar.gz',
  'has_sig': True,
  'md5_digest': '54d587da7c3d9c83f13d04674cacdc2a',
  'packagetype': 'sdist',
  'path': 'f0/07/6f4e2164ed82dfff873ee55181f782926bcb4a29f6a83fe4f8b9cbf5489c/roundup-1.6.0.tar.gz',
  'python_version': 'source',
  'sha256_digest': '1814c74b40c4a6287e0a97b810f6adc6a3312168201eaa0badd1dd8c216b1bcb',
  'size': 2893499,
  'upload_time_iso_8601': '2018-07-13T11:30:36.405653Z',
  'url': 'https://files.pythonhosted.org/packages/f0/07/6f4e2164ed82dfff873ee55181f782926bcb4a29f6a83fe4f8b9cbf5489c/roundup-1.6.0.tar.gz'}]

.. _changes-to-legacy-api:

Changes to XMLRPC API
---------------------

- ``search`` Permanently deprecated and disabled due to excessive traffic
  driven by unidentified traffic, presumably automated. `See historical
  incident <https://status.python.org/incidents/grk0k7sz6zkp>`_.

- ``package_releases`` As Warehouse does not support the concept of hidden
  releases, the `show_hidden` flag now controls whether the latest version or
  all versions are returned.

- ``release_data`` The `stable_version` flag is always an empty string. It was
  never fully supported anyway.

- ``release_downloads`` and ``top_packages`` No longer supported. Use
  :doc:`Google BigQuery <bigquery-datasets>` instead (`guidance
  <https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_,
  `tips <https://langui.sh/2016/12/09/data-driven-decisions/>`_).


.. _changelog-since:

Mirroring Support
-----------------

.. note::
  XML-RPC methods for mirroring support are currently the only methods we
  consider fully supported, until an improved mechanism for mirroring is
  implemented. Users of these methods should **certainly** subscribe to the
  pypi-announce_ mailing list to ensure they are aware of changes or
  deprecations related to these methods.

``changelog_last_serial()``
+++++++++++++++++++++++++++

Retrieve the last event's serial id (an ``int``).

``changelog_since_serial(since_serial)``
++++++++++++++++++++++++++++++++++++++++

Retrieve a list of `(name, version, timestamp, action, serial)` since the
event identified by the given ``since_serial``. All timestamps are UTC
values.

``list_packages_with_serial()``
+++++++++++++++++++++++++++++++

Retrieve a dictionary mapping package names to the last serial for each
package.


Package querying
----------------

``package_roles(package_name)``
+++++++++++++++++++++++++++++++

Retrieve a list of `[role, user]` for a given `package_name`.
Role is either `Maintainer` or `Owner`.

``user_packages(user)``
+++++++++++++++++++++++

Retrieve a list of `[role, package_name]` for a given `user`.
Role is either `Maintainer` or `Owner`.

``browse(classifiers)``
+++++++++++++++++++++++

Retrieve a list of `[name, version]` of all releases classified with all of
the given classifiers. `classifiers` must be a list of Trove classifier
strings.

``updated_releases(since)``
+++++++++++++++++++++++++++

Retrieve a list of package releases made since the given timestamp. The
releases will be listed in descending release date.

``changed_packages(since)``
+++++++++++++++++++++++++++

Retrieve a list of package names where those packages have been changed
since the given timestamp. The packages will be listed in descending date
of most recent change.


``list_packages()``
+++++++++++++++++++

.. warning::
  Migrate to using the :doc:`Simple API <legacy>`.

Retrieve a list of the package names registered with the package index.
Returns a list of name strings.

``package_releases(package_name, show_hidden=False)``
+++++++++++++++++++++++++++++++++++++++++++++++++++++

.. warning::
  Migrate to using the :doc:`json`.

Retrieve a list of the releases registered for the given `package_name`,
ordered by version.

If `show_hidden` is `False` (the default), only the latest version is
returned.  Otherwise, all versions are returned.

``release_urls(package_name, release_version)``
+++++++++++++++++++++++++++++++++++++++++++++++

.. warning::
  Migrate to using the :doc:`json`.

Retrieve a list of download URLs for the given `release_version`.
Returns a list of dicts with the following keys:

* filename
* packagetype ('sdist', 'bdist_wheel', etc)
* python_version (required version, or 'source', or 'any')
* size (an ``int``)
* md5_digest
* digests (a dict with two keys, "md5" and "sha256")
* has_sig (a boolean)
* upload_time_iso_8601 (a ``DateTime`` object)
* comment_text
* downloads (always says "-1")
* url

``release_data(package_name, release_version)``
+++++++++++++++++++++++++++++++++++++++++++++++

.. warning::
  Migrate to using the :doc:`json`.

Retrieve metadata describing a specific `release_version`.
Returns a dict with keys for:

* name
* version
* stable_version (always an empty string or None)
* bugtrack_url
* package_url
* release_url
* docs_url (URL of the packages.python.org docs if they've been supplied)
* home_page
* download_url
* project_url
* author
* author_email
* maintainer
* maintainer_email
* summary
* description (string, sometimes the entirety of a ``README``)
* license
* keywords
* platform
* classifiers (list of classifier strings)
* requires
* requires_dist
* provides
* provides_dist
* obsoletes
* obsoletes_dist
* requires_python
* requires_external
* _pypi_ordering
* _pypi_hidden
* downloads (``{'last_day': 0, 'last_week': 0, 'last_month': 0}``)

If the release does not exist, an empty dictionary is returned.


Deprecated Methods
------------------

.. warning::
  The following methods are permanently deprecated and will return a
  `RuntimeError`

``changelog(since, with_ids=False)``
++++++++++++++++++++++++++++++++++++

Deprecated in favor of ``changelog_since_serial``.

``package_data(package_name, version)``
+++++++++++++++++++++++++++++++++++++++

Deprecated in favor of ``release_data``, :doc:`json` should be used.

``package_urls(package_name, version)``
+++++++++++++++++++++++++++++++++++++++

Deprecated in favor of ``release_urls``, :doc:`json` should be used.

``top_packages(num=None)``
++++++++++++++++++++++++++

Use :doc:`Google BigQuery <bigquery-datasets>`
instead (`guidance <https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_,
`tips <https://langui.sh/2016/12/09/data-driven-decisions/>`_).

``search(spec[, operator])``
++++++++++++++++++++++++++++

Permanently deprecated and disabled due to excessive traffic
driven by unidentified traffic, presumably automated. `See historical incident
<https://status.python.org/incidents/grk0k7sz6zkp>`_.

.. _pypi-announce: https://mail.python.org/mailman3/lists/pypi-announce.python.org/
