# PyPI's XML-RPC methods

!!! warning
    The XML-RPC API will be deprecated in the future. Use of this API is not
    recommended, and existing consumers of the API should migrate to the RSS
    and/or JSON APIs instead.

    As a result, this API has a very restrictive rate limit and it may be
    necessary to pause between successive requests.

    Users of this API are **strongly** encouraged to subscribe to the
    [pypi-announce](https://mail.python.org/mailman3/lists/pypi-announce.python.org/) mailing list for notices as we begin the process of removing
    XML-RPC from PyPI.

Example usage (Python 3):

```pycon
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
```

## Project and release activity details

PyPI publishes a "journal" of all project, package, and release
activity (including Owner and Maintainer additions and removals, and
source file and release additions and removals). You can query it with
a mix of [changelog_since_serial](#changelog_since_serialsince_serial) and the
[index API](https://docs.pypi.org/api/index-api/). Call
`changelog_last_serial()` to get the current
revision of the journal (the last event's serial ID), then look at
`/simple/` to get a list of all packages that currently
exist. Subsequently, you can call
`changelog_since_serial(since_serial)` with the serial ID you
retrieved, and get the list of all actions that have occurred since
then.

Example usage:

```pycon
>>> import time
>>> import xmlrpc.client
>>> client = xmlrpc.client.ServerProxy("https://test.pypi.org/pypi")
>>> serial = client.changelog_last_serial()
>>> serial
4601224
>>> while serial == client.changelog_last_serial():
...     time.sleep(5)
>>> recentchanges = client.changelog_since_serial(serial)
>>> for entry in recentchanges:
...     print(entry)
['openllm', '0.4.33.dev3', 1701280908, 'new release', 4601225]
['openllm', '0.4.33.dev3', 1701280908, 'add py3 file openllm-0.4.33.dev3-py3-none-any.whl', 4601226]
```

You could also request `GET /simple/`, and record the `ETag`, and
then periodically do a conditional HTTP GET to `/simple/` with that
ETag included. A 200 OK response indicates something has been added or
removed; if you get a 304 Not Modified, then nothing has changed.

## Changes to XMLRPC API

- `list_packages`, `package_releases`, `release_urls`, and `release_data`
  permanently deprecated and disabled. See [Deprecated Methods](#deprecated-methods) for alternatives.

- `search` Permanently deprecated and disabled due to excessive traffic
  driven by unidentified traffic, presumably automated. [See historical
  incident](https://status.python.org/incidents/grk0k7sz6zkp).

- `release_downloads` and `top_packages` No longer supported. Use
  [BigQuery Datasets](https://docs.pypi.org/api/bigquery/) instead ([guidance](https://packaging.python.org/guides/analyzing-pypi-package-downloads/),
  [tips](https://langui.sh/2016/12/09/data-driven-decisions/)).

## Mirroring Support

!!! note
    XML-RPC methods for mirroring support are currently the only methods we
    consider fully supported, until an improved mechanism for mirroring is
    implemented. Users of these methods should **certainly** subscribe to the
    [pypi-announce](https://mail.python.org/mailman3/lists/pypi-announce.python.org/) mailing list to ensure they are aware of changes or
    deprecations related to these methods.

### `changelog_last_serial()`

Retrieve the last event's serial id (an `int`).

### `changelog_since_serial(since_serial)`

Retrieve a list of `(name, version, timestamp, action, serial)` since the
event identified by the given `since_serial`. All timestamps are UTC
values.

### `list_packages_with_serial()`

Retrieve a dictionary mapping package names to the last serial for each
package.

## Package querying

!!! warning
    The following methods are considered unsupported and will be deprecated
    in the future.

### `user_packages(user)`

Retrieve a list of `[role, package_name]` for a given `user`.
Role is either `Maintainer` or `Owner`.

### `browse(classifiers)`

Retrieve a list of `[name, version]` of all releases classified with all of
the given classifiers. `classifiers` must be a list of Trove classifier
strings.

## Deprecated Methods

!!! danger "Permanently Deprecated"
    The following methods are permanently deprecated and will return a
    `RuntimeError`

### `changelog(since, with_ids=False)`

Deprecated in favor of `changelog_since_serial`.

### `package_data(package_name, version)`

Deprecated, the [JSON API](https://docs.pypi.org/api/json/) should be used.

### `package_urls(package_name, version)`

Deprecated, the [JSON API](https://docs.pypi.org/api/json/) should be used.

### `top_packages(num=None)`

Use [BigQuery Datasets](https://docs.pypi.org/api/bigquery/)
instead ([guidance](https://packaging.python.org/guides/analyzing-pypi-package-downloads/),
[tips](https://langui.sh/2016/12/09/data-driven-decisions/)).

### `search(spec[, operator])`

Permanently deprecated and disabled due to excessive traffic
driven by unidentified traffic, presumably automated. [See historical incident](https://status.python.org/incidents/grk0k7sz6zkp).

### `list_packages()`

Use the [Index API](https://docs.pypi.org/api/index-api/)
to query for list of project names with releases on PyPI.

### `package_releases(package_name, show_hidden=False)`

Use the [JSON API](https://docs.pypi.org/api/json/) or
[Index API](https://docs.pypi.org/api/index-api/) to query for available
releases of a given project.

### `release_urls(package_name, release_version)`

Use the [JSON API](https://docs.pypi.org/api/json/) or
[Index API](https://docs.pypi.org/api/index-api/) to query for file download
URLs for a given release.

### `release_data(package_name, release_version)`

Use the [JSON API](https://docs.pypi.org/api/json/) or
[Index API](https://docs.pypi.org/api/index-api/) to query for metadata of a
given release.

### `package_roles(package_name)`

Use the [JSON API](https://docs.pypi.org/api/json/) `ownership` key to
query for roles of a given project.
