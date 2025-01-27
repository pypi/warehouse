Updating Development Database
=============================

Occasionally, the database dump supplied for local development should be
refreshed.

This dump is created from the database behind test.pypi.org, not production.

Use ``pg_dump`` to create the initial file::

    pg_dump --no-owner $DATABASE_URL > dev/example.sql

Now create a database locally and load the result::

    createdb warehouse_dev_dump && \
    psql warehouse_dev_dump < dev/example.sql

With the database loaded, run the clean script to remove personal information::

    psql warehouse_dev_dump < dev/clean.sql

Dump the result, compress it, and clean up::

    pg_dump --no-owner warehouse_dev_dump > dev/example.sql && \
    xz -z -9 dev/example.sql && \
    dropdb warehouse_dev_dump

Now commit the result::

    git checkout -b update_dev_db_dump && \
    git add dev/example.sql.xz && \
    git commit -m "Update development database dump"


Connecting to the Development Database
======================================

To connect to the development database, use the following command::

    make dbshell

This will spawn a one-time container that connects to the database,
and opens a shell for you to interact with it.

If you want to use another tool from your host machine,
you can connect to the database using a connection string, like this::

    pgcli postgresql://postgres@localhost:5433/warehouse
