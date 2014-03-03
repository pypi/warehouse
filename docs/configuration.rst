Configuration
=============

Warehouse uses a YAML based configuration format. You can specify which file to
load using either the environment variable ``WAREHOUSE_CONF`` or by using the
``-c`` option on the ``warehouse`` cli. The default configuration for Warehouse
is inside of the ``warehouse/config.yml`` file. Warehouse will do a nested
dictionary merge of the config file into the default configuration file, making
it simple to override a default setting even inside of another dictionary.


Configuration Options
---------------------

debug
~~~~~

:Type: Boolean
:Default: ``True``
:Required: No
:Description:
    Determines whether Warehouse is in debug mode or not, primarily this acts
    as an optimization in production as it turns off things like auto reloading
    of the Jinja2 templates or using the hashed filenames for static files.

site.name
~~~~~~~~~

:Type: String
:Default: ``"Warehouse"``
:Required: No
:Description:
    The name of this instance of Warehouse. This will be used in the title tags
    and headers of Warehouse.

site.url
~~~~~~~~

:Type: URL
:Default: ``"/"``
:Required: No
:Description:
    The base url of this Warehouse instance.

paths.documentation
~~~~~~~~~~~~~~~~~~~

:Type: Path
:Default: ``None``
:Required: Yes
:Description:
    The base filesystem path where uploaded package documentation should be
    saved to. This path **must** be readable and writable by the user running
    Warehouse.

paths.packages
~~~~~~~~~~~~~~

:Type: Path
:Default: ``None``
:Required: Yes
:Description:
    The base filesystem path where uploaded package distributions should be
    saved to. This path **must** be readable and writable by the user running
    Warehouse.

urls.documentation
~~~~~~~~~~~~~~~~~~

:Type: URL
:Default: ``None``
:Required: Yes
:Description:
    The base URL where uploaded documentation is hosted at, this should
    correspond to the path in ``paths.documentation``.

database.url
~~~~~~~~~~~~

:Type: URL
:Default: ``None``
:Required: Yes
:Description:
    The URL for the primary database. This must be a PostgreSQL 9.3+ database
    and must be in the form of ``postgresql://hostname[:port]/databasename``.

redis.url
~~~~~~~~~

:Type: URL
:Default: ``None``
:Required: Yes
:Description:
    This is the URL for the primary redis database. It must be an url of the
    form ``redis://hostname:port/dbnum``.

search.index
~~~~~~~~~~~~

:Type: String
:Default: ``"warehouse"``
:Required: No
:Description:
    This is the name of the elastic search index that this instance of
    Warehouse will use. Note that if you use the ``warehouse search reindex``
    command that Warehouse will actually create an index named
    ``warehouse-random_data`` and will create an alias with this setting name
    pointing at that randomly named index.

search.hosts
~~~~~~~~~~~~

:Type: List of Dictionaries
:Default: ``[]``
:Required: Yes
:Description:
    This is a list of elasticsearch hosts that Warehouse should attempt to use.
    Each list entry should be a dictionary with a ``host`` and ``port`` key.

logging
~~~~~~~

:Type: Dictionary
:Default: See warehouse/config.yml
:Required: No
:Description:
    This is a ``logging.config.dictConfig`` style dictionary that will be used
    to configure the Python logging system.



Example Configuration
---------------------

.. code:: yaml

    debug: false

    site:
        name: Warehouse
        url: /

    paths:
        documentation: data/packagedocs
        packages: "data/packages"

    urls:
        documentation: "https://pythonhosted.org"

    database:
        url: "postgresql://localhost/warehouse"

    redis:
        url: "redis://localhost:6379/0"

    search:
        index: warehouse
        hosts:
            - host: 127.0.0.1
              port: 9200

    logging:
        version: 1
        formatters:
            default:
                format: '[%(asctime)s %(levelname)s] %(message)s'
                datefmt: '%Y-%m-%d %H:%M:%S'
        handlers:
            console:
                class: logging.StreamHandler
                formatter: default
                level: DEBUG
                stream: ext://sys.stdout
        root:
            level: INFO
            handlers: [console]
