Installation Instructions for Non-Python Dependencies
=====================================================

Ubuntu 14.04 / Debian-based Environment
---------------------------------------


Redis
-----

.. code-block:: console
    
    $ sudo apt-get install redis-server


Compass
-------

.. code-block:: console
    
    # Install Ruby dependencies. 
    $ sudo apt-get install git-core curl zlib1g-dev build-essential libssl-dev
      libreadline-dev libyaml-dev libsqlite3-dev sqlite3 libxml2-dev
      libxslt1-dev libcurl4-openssl-dev python-software-properties

    # Install Ruby and Rubygems.
    $ cd
    $ git clone git://github.com/sstephenson/rbenv.git .rbenv
    $ echo 'export PATH="$HOME/.rbenv/bin:$PATH"' >> ~/.bashrc
    $ echo 'eval "$(rbenv init -)"' >> ~/.bashrc
    $ exec $SHELL

    $ git clone git://github.com/sstephenson/ruby-build.git ~/.rbenv/plugins/ruby-build
    $ echo 'export PATH="$HOME/.rbenv/plugins/ruby-build/bin:$PATH"' >> ~/.bashrc
    $ exec $SHELL

    # Setup Ruby.
    $ rbenv install 2.1.2
    $ rbenv global 2.1.2
    $ ruby -v
    $ echo "gem: --no-ri --no-rdoc" > ~/.gemrc

    # Install non-python dependency ``compass``
    $ gem install compass


Grunt
-----

.. code-block:: console

    $ sudo apt-get install python-software-properties g++
    $ sudo add-apt-repository ppa:chris-lea/node.js
    $ sudo apt-get update
    $ sudo apt-get install nodejs
    $ sudo nmp install -g grunt


Elasticsearch
-------------

.. code-block:: console

    $ sudo apt-get install openjdk-7-jre-headless -y

    # Download elasiticsearch-x.x.x.deb
    $ sudo dpkg -i elasticsearch-x.x.x.deb

    # Start elasticsearch server.
    $ sudo /etc/init.d/elasticsearch start

    # If elasticsearch should start on bootup.
    $ sudo update-rc.d elasticsearch defaults 95 10


Postgresql
----------

.. code-block:: console

    $ sudo sh -c "echo 'deb http://apt.postgresql.org/pub/repos/apt/ trusty-pgdg main' > /etc/apt/sources.list.d/pgdg.list"
    $ wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
    $ sudo apt-get update
    $ sudo apt-get install postgresql-common
    $ sudo apt-get install postgresql-contrib-9.3
    $ sudo apt-get install postgresql-9.3 libpq-dev

    # Setup warehouse db username.  Warehouse db unit tests expect
    # ``username`` to be the local username.
    $ sudo -u postgres createuser username -s

    $ sudo -u postgres psql
    postgres# ALTER USER username CREATEDB
    
    # Edit ``pg_hba.conf``.  You can locate the ``pg_hba.conf`` with ``show``.
    postgres# show hba-file;
    etc/postgresql/9.3/main/pg_hba.conf
    
    # Modify the ``local`` and ``host`` fields to:
    local   all             all                                     trust
    
    # IPv4 local connections:
    host    all             all             127.0.0.1/32            trust
    
    # IPv6 local connections:
    host    all             all             ::1/128                 trust

    # Start ``postgresql`` 
    $ sudo service postgresql restart
