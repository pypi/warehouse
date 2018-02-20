
PyPI's XML-RPC methods
======================

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

Changes to Legacy API
---------------------

``package_releases`` The `show_hidden` flag is now ignored. All versions are
returned.

``release_data`` The `stable_version` flag is always an empty string. It was
never fully supported anyway.


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

``release_downloads(package_name, release_version)``
  Retrieve a list of `[filename, download_count]` for a given `package_name`
  and `release_version`.

``release_urls(package_name, release_version)``
  Retrieve a list of download URLs for the given `release_version`.
  Returns a list of dicts with the following keys:

  * url
  * packagetype ('sdist', 'bdist_wheel', etc)
  * filename
  * size
  * md5_digest
  * downloads
  * has_sig
  * python_version (required version, or 'source', or 'any')
  * comment_text

``release_data(package_name, release_version)``
  Retrieve metadata describing a specific `release_version`.
  Returns a dict with keys for:

  * name
  * version
  * stable_version (always an empty string)
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
  * classifiers (list of classifier strings)
  * requires
  * requires_dist
  * provides
  * provides_dist
  * requires_external
  * requires_python
  * obsoletes
  * obsoletes_dist
  * project_url
  * docs_url (URL of the packages.python.org docs if they've been supplied)

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

``top_packages([number])``
  Retrieve the sorted list of packages ranked by number of downloads.
  Optionally limit the list to the `number` given.

``updated_releases(since)``
  Retrieve a list of package releases made since the given timestamp. The
  releases will be listed in descending release date.

``changed_packages(since)``
  Retrieve a list of package names where those packages have been changed
  since the given timestamp. The packages will be listed in descending date
  of most recent change.


Mirroring Support
-----------------

``changelog(since, with_ids=False)``
  Retrieve a list of `[name, version, timestamp, action]`, or
  `[name, version, timestamp, action, id]` if `with_ids=True`, since the given
  `since`. All `since` timestamps are UTC values. The argument is a UTC integer
  seconds since the epoch.

``changelog_last_serial()``
  Retrieve the last event's serial id.

``changelog_since_serial(since_serial)``
  Retrieve a list of `(name, version, timestamp, action, serial)` since the
  event identified by the given `since_serial` All timestamps are UTC
  values. The argument is a UTC integer seconds since the epoch.

``list_packages_with_serial()``
  Retrieve a dictionary mapping package names to the last serial for each
  package.
