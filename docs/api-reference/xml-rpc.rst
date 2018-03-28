
PyPI's XML-RPC methods
======================

.. note::
   The XML-RPC API will be deprecated in the future. Use of this API is not
   recommended, and existing consumers of the API should migrate to the RSS
   and/or JSON APIs instead.

Example usage::

  >>> import xmlrpclib
  >>> import pprint
  >>> client = xmlrpclib.ServerProxy('https://pypi.org/pypi')
  >>> client.package_releases('roundup')
  ['1.4.10']
  >>> pprint.pprint(client.release_urls('roundup', '1.4.10'))
  [{'comment_text': '',
    'downloads': 3163,
    'filename': 'roundup-1.1.2.tar.gz',
    'has_sig': True,
    'md5_digest': '7c395da56412e263d7600fa7f0afa2e5',
    'packagetype': 'sdist',
    'python_version': 'source',
    'size': 876455,
    'upload_time': <DateTime '20060427T06:22:35' at 912fecc>,
    'url': 'https://pypi.org/packages/source/r/roundup/roundup-1.1.2.tar.gz'},
   {'comment_text': '',
    'downloads': 2067,
    'filename': 'roundup-1.1.2.win32.exe',
    'has_sig': True,
    'md5_digest': '983d565b0b87f83f1b6460e54554a845',
    'packagetype': 'bdist_wininst',
    'python_version': 'any',
    'size': 614270,
    'upload_time': <DateTime '20060427T06:26:04' at 912fdec>,
    'url': 'https://pypi.org/packages/any/r/roundup/roundup-1.1.2.win32.exe'}]

.. _changes-to-legacy-api:

Changes to Legacy API
---------------------

``package_releases`` The `show_hidden` flag is now ignored. All versions are
returned.

``release_data`` The `stable_version` flag is always an empty string. It was
never fully supported anyway.

``release_downloads`` and ``top_packages`` No longer supported. Please
use `Google BigQuery
<https://mail.python.org/pipermail/distutils-sig/2016-May/028986.html>`_
instead (`guidance
<https://packaging.python.org/guides/analyzing-pypi-package-downloads/>`_,
`tips <https://langui.sh/2016/12/09/data-driven-decisions/>`_).

Package Querying
----------------

``list_packages()``
  Retrieve a list of the package names registered with the package index.
  Returns a list of name strings.

``package_releases(package_name, show_hidden=False)``
  Retrieve a list of the releases registered for the given `package_name`,
  ordered by version.

  The `show_hidden` flag is now ignored. All versions are returned.

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
  * upload_time (a ``DateTime`` object)
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
  or "or". Example: search({'name': 'foo', 'description': 'bar'}, 'or'). The
  results are returned as a list of dicts {'name': package name, 'version':
  package release version, 'summary': package release summary}

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
  values. The argument is a UTC integer seconds since the epoch.

``list_packages_with_serial()``
  Retrieve a dictionary mapping package names to the last serial for each
  package.
