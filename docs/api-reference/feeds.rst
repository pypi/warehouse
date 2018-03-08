Feeds
=====

PyPI offers two RSS feeds, the `Newest Packages Feed`_ and the `Latest Updates
Feed`_. You can also call its APIs to get more details on project activity.


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

Project and release activity details
------------------------------------

PyPI publishes a "journal" of all project, package, and release
activity (including release deletions). You can query it with a mix of
:ref:`changelog-since` and :ref:`simple-api`. Call
``changelog_last_serial()`` (in :doc:`xml-rpc`) to get the current
revision of the journal (the last event's serial ID), then look at
``/simple/`` to get a list of all packages that currently
exist. Subsequently, you can call
``changelog_since_serial(since_serial)`` with the serial ID you
retrieved, and get the list of all actions that have occurred since
then.

You could also request ``GET /simple/``, and record the ``ETag``, and
then periodically do a conditional HTTP GET to ``/simple/`` with that
ETag included. A 200 OK response indicates something has been added or
removed; if you get a 304 Not Modified, then nothing has changed.
