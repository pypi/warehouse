Feeds
=====

PyPI offers three RSS feeds, the `Newest Packages Feed`_, the `Latest Updates
Feed`_, and the `Package Releases Feed`_. You can also call its APIs to get
more details on project activity.


Newest Packages Feed
--------------------

Available at https://pypi.org/rss/packages.xml, this feed provides the latest
newly created projects on PyPI, including the package name, description and a
link to the project page.


Latest Updates Feed
-------------------

Available at https://pypi.org/rss/updates.xml, this feed provides the latest
newly created releases for individual projects on PyPI, including the project
name and description, release version, and a link to the release page.


Package Releases Feed
---------------------

Available at https://pypi.org/rss/project/<project>/releases.xml for each
project, this feed provides the latest releases for the given project on
PyPI, including the package name and description, release version, and a link
to the release page.


Project and release activity details
------------------------------------

PyPI publishes a "journal" of all project, package, and release
activity (including Owner and Maintainer additions and removals, and
source file and release additions and removals). You can query it with
a mix of :ref:`changelog-since` and :ref:`simple-api`. Call
``changelog_last_serial()`` (in :doc:`xml-rpc`) to get the current
revision of the journal (the last event's serial ID), then look at
``/simple/`` to get a list of all packages that currently
exist. Subsequently, you can call
``changelog_since_serial(since_serial)`` with the serial ID you
retrieved, and get the list of all actions that have occurred since
then.

Example usage::

  >>> import xmlrpc.client
  >>> import arrow
  >>> client = xmlrpc.client.ServerProxy('https://test.pypi.org/pypi')
  >>> latefeb = arrow.get('2018-02-20 10:00:00')
  >>> latefeb.timestamp
  1519120800
  >>> latefebstamp = latefeb.timestamp
  >>> recentchanges = client.changelog(latefebstamp)
  >>> len(recentchanges)
  7322
  >>> for entry in recentchanges:
  ...     if entry[0] == 'twine':
  ...         print(entry[1], " ", entry[3], " ", entry[2])
  ...
  ...
  ...
  None   add Owner brainwane   1519952529
  1.10.0   add py2.py3 file twine-1.10.0-py2.py3-none-any.whl   1520023899
  1.10.0   new release   1520023899
  1.10.0rc1   add py2.py3 file twine-1.10.0rc1-py2.py3-none-any.whl   1520023900
  1.10.0rc1   new release   1520023900
  1.10.0rc1   add source file twine-1.10.0rc1.tar.gz   1520023902
  1.10.0   add source file twine-1.10.0.tar.gz   1520023903
  1.10.0   remove file twine-1.10.0.tar.gz   1520024758
  1.10.0   remove file twine-1.10.0-py2.py3-none-any.whl   1520024797
  1.10.0   remove   1520025270


You could also request ``GET /simple/``, and record the ``ETag``, and
then periodically do a conditional HTTP GET to ``/simple/`` with that
ETag included. A 200 OK response indicates something has been added or
removed; if you get a 304 Not Modified, then nothing has changed.
