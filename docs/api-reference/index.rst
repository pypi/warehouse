API Reference
=============

Warehouse has several API endpoints. See :doc:`../application` for the
parts of Warehouse that generate them.

.. contents:: :local:

API Policies
------------

Please be aware of the following PyPI API Policies:

Caching
~~~~~~~

All API requests are cached. Requests to the JSON, RSS or Legacy APIs are
cached by our CDN provider. You can determine if you've hit the cache based on
the ``X-Cache`` and ``X-Cache-Hist`` headers in the response.

All API requests also provide an ``ETag`` header. If you're making a lot of
repeated requests, please ensure your API consumer will respect this header to
determine whether to actually repeat a request or not.

Rate Limiting
~~~~~~~~~~~~~

Due to the heavy caching and CDN use, there is currently no rate limiting of
PyPI APIs.

However, if you plan to make a lot of requests to a PyPI API, please adhere to
the following suggestions:

* Set your consumer's ``User-Agent`` header to uniquely identify your requests
* Try not to make a lot of requests (thousands) in a short amount of time
  (minutes). Generally PyPI can handle it, but it's preferred to make requests
  in serial over a longer amount of time if possible.

API Preference
~~~~~~~~~~~~~~

For periodically checking for new packages or updates to existing packages,
please use our RSS feeds.

If at all possible, it is recommended to use the JSON/RSS/Legacy APIs over
XML-RPC.

Available APIs
--------------

.. toctree::
    :maxdepth: 2

    feeds
    json
    legacy
    xml-rpc
    integration-guide
