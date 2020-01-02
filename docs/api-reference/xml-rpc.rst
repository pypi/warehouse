
PyPI's XML-RPC methods
======================

.. note::
   The XML-RPC API will be deprecated in the future. Use of this API is not
   recommended, and existing consumers of the API should migrate to the RSS
   and/or JSON APIs instead.

   Users of this API are **strongly** encouraged to subscribe to the
   pypi-announce_ mailing list for notices as we begin the process of removing
   XML-RPC from PyPI.

Example usage (Python 3)::

  >>> import xmlrpc.client
  >>> import pprint
  >>> client = xmlrpc.client.ServerProxy('https://pypi.org/pypi')
  >>> client.package_releases('roundup')
  ['1.6.0']
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

Changes to Legacy API
---------------------

``package_releases`` As Warehouse does not support the concept of hidden
releases, the `show_hidden` flag now controls whether the latest version or all
versions are returned.

``release_data`` The `stable_version` flag is always an empty string. It was
never fully supported anyway.

``release_downloads`` and ``top_packages`` No longer supported. Use
`Google BigQuery
<https://mail.python.org/pipermail/distutils-sig/2016-May/028986.html>`_
instead (`guidance
<https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_,
`tips <https://langui.sh/2016/12/09/data-driven-decisions/>`_).

Package querying
----------------

``list_packages()``
  Retrieve a list of the package names registered with the package index.
  Returns a list of name strings.

``package_releases(package_name, show_hidden=False)``
  Retrieve a list of the releases registered for the given `package_name`,
  ordered by version.

  If `show_hidden` is `False` (the default), only the latest version is
  returned.  Otherwise, all versions are returned.

``package_roles(package_name)``
  Retrieve a list of `[role, user]` for a given `package_name`.
  Role is either `Maintainer` or `Owner`.

``user_packages(user)``
  Retrieve a list of `[role, package_name]` for a given `user`.
  Role is either `Maintainer` or `Owner`.

``release_urls(package_name, release_version)``
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

``search(spec[, operator])``
  Search the package database using the indicated search `spec`.

  Returns at most 100 results.

  The `spec` may include any of the keywords described in the above list
  (except 'stable_version' and 'classifiers'), for example:
  {'description': 'spam'} will search description fields. Within the spec, a
  field's value can be a string or a list of strings (the values within the
  list are combined with an OR), for example: {'name': ['foo', 'bar']}. Valid
  keys for the spec dict are listed here. Invalid keys are ignored:

  * name
  * version
  * author
  * author_email
  * maintainer
  * maintainer_email
  * home_page
  * license
  * summary
  * description
  * keywords
  * platform
  * download_url

  Arguments for different fields are combined using either "and" (the default)
  or "or". Example: `search({'name': 'foo', 'description': 'bar'}, 'or')`.
  The results are returned as a list of dicts `{'name': package name,
  'version': package release version, 'summary': package release summary}`

``browse(classifiers)``
  Retrieve a list of `[name, version]` of all releases classified with all of
  the given classifiers. `classifiers` must be a list of Trove classifier
  strings.

``updated_releases(since)``
  Retrieve a list of package releases made since the given timestamp. The
  releases will be listed in descending release date.

``changed_packages(since)``
  Retrieve a list of package names where those packages have been changed
  since the given timestamp. The packages will be listed in descending date
  of most recent change.

.. _changelog-since:

Mirroring Support
-----------------

``changelog(since, with_ids=False)``
  Retrieve a list of `[name, version, timestamp, action]`, or `[name,
  version, timestamp, action, id]` if `with_ids=True`, since the given
  `since`. All `since` timestamps are UTC values. The argument is a
  UTC integer seconds since the epoch (e.g., the ``timestamp`` method
  to a ``datetime.datetime`` object).

``changelog_last_serial()``
  Retrieve the last event's serial id (an ``int``).

``changelog_since_serial(since_serial)``
  Retrieve a list of `(name, version, timestamp, action, serial)` since the
  event identified by the given ``since_serial``. All timestamps are UTC
  values.

``list_packages_with_serial()``
  Retrieve a dictionary mapping package names to the last serial for each
  package.

.. _pypi-announce: https://mail.python.org/mm3/mailman3/lists/pypi-announce.python.org/
