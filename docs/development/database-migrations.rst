Database Migrations
===================

Modifying database schema will need database migrations (except for removing
and adding tables). To autogenerate migrations::

    $ docker-compose run web python -m warehouse db revision

Then migrate and test your migration::

    $ docker-compose run web python -m warehouse db upgrade head
