
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
  >>> client.changelog_last_serial()
  24891357
  >>> time.sleep(1)  # Sleep to avoid rate limit
  >>> client.changelog_since_serial(24891357)
  [['py-pcapplusplus', '1.0.0', 1725534675, 'remove release', 24891358]]
  >>> time.sleep(1)  # Sleep to avoid rate limit
  >>> pprint.pprint(client.list_packages_with_serial())
  {'0': 3075854,
   '0-._.-._.-._.-._.-._.-._.-0': 1448421,
   '0-core-client': 3242044,
   '0-orchestrator': 3242047,
   '0.0.1': 3430659,
   '0.618': 14863648,
  ...

.. _changes-to-legacy-api:

Changes to XMLRPC API
---------------------

- ``list_packages``, ``package_releases``, ``release_urls``, and ``release_data``
  permanently deprecated and disabled. See `Deprecated Methods`_ for alternatives.

- ``search`` Permanently deprecated and disabled due to excessive traffic
  driven by unidentified traffic, presumably automated. `See historical
  incident <https://status.python.org/incidents/grk0k7sz6zkp>`_.

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

Retrieve a list of ``(name, version, timestamp, action, serial)`` since the
event identified by the given ``since_serial``. All timestamps are UTC
values.

``list_packages_with_serial()``
+++++++++++++++++++++++++++++++

Retrieve a dictionary mapping package names to the last serial for each
package.


Package querying
----------------

.. warning::
  The following methods are considered unsupported and will be deprecated
  in the future.

``package_roles(package_name)``
+++++++++++++++++++++++++++++++

Retrieve a list of ``[role, user]`` for a given ``package_name``.
Role is either ``Maintainer`` or ``Owner``.

``user_packages(user)``
+++++++++++++++++++++++

Retrieve a list of ``[role, package_name]`` for a given ``user``.
Role is either ``Maintainer`` or ``Owner``.

``browse(classifiers)``
+++++++++++++++++++++++

Retrieve a list of ``[name, version]`` of all releases classified with all of
the given classifiers. ``classifiers`` must be a list of Trove classifier
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


Deprecated Methods
------------------

.. attention::
  The following methods are permanently deprecated and will return a
  ``RuntimeError``

``changelog(since, with_ids=False)``
++++++++++++++++++++++++++++++++++++

Deprecated in favor of ``changelog_since_serial``.

``package_data(package_name, version)``
+++++++++++++++++++++++++++++++++++++++

Deprecated, :doc:`json` should be used.

``package_urls(package_name, version)``
+++++++++++++++++++++++++++++++++++++++

Deprecated, :doc:`json` should be used.

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

``list_packages()``
+++++++++++++++++++

Use the :doc:`Simple API <legacy>`
to query for list of project names with releases on PyPI.

``package_releases(package_name, show_hidden=False)``
+++++++++++++++++++++++++++++++++++++++++++++++++++++

Use :doc:`json` or :doc:`Simple API <legacy>` to query for available releases
of a given project.

``release_urls(package_name, release_version)``
+++++++++++++++++++++++++++++++++++++++++++++++

Use :doc:`json` or :doc:`Simple API <legacy>` to query for file download URLs
for a given release.

``release_data(package_name, release_version)``
+++++++++++++++++++++++++++++++++++++++++++++++

Use :doc:`json` or :doc:`Simple API <legacy>` to query for metadata of a given
release.

.. _pypi-announce: https://mail.python.org/mailman3/lists/pypi-announce.python.org/
