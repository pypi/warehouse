Database Migrations
===================

Modifying database schemata will need database migrations (except for removing
and adding tables). To autogenerate migrations::

    $ docker-compose run web python -m warehouse db revision

Then migrate and test your migration::

    $ docker-compose run web python -m warehouse db upgrade head

Migrations are automatically run as part of the deployment process, but prior
to the old version of Warehouse from being shut down. This means that each
migration *must* be compatible with the current ``master`` branch of Warehouse.

This makes it more difficult to make breaking changes, since you must phase
them in over time (for example, to rename a column you must add the column in
one migration + start writing to that column/reading from both, then you must
make a migration that backfills all of the data, then switch the code to stop
using the old column all together, then finally you can remove the old column).
