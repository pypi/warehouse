Database Migrations
===================

Modifying database schema will need database migrations (except for removing
and adding tables). To autogenerate migrations::

    $ docker-compose run web warehouse -c dev/config.yml db revision -m

Then migrate and test your migration::

    $ docker-compose run web warehouse -c dev/config.yml db upgrade head
