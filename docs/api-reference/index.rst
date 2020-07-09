API reference
=============

Warehouse has several API endpoints. See :doc:`../application` for the
parts of Warehouse that generate them.

.. contents:: :local:

API policies
------------

Please be aware of these PyPI API policies:

Caching
~~~~~~~

All API requests are cached. Requests to the JSON, RSS or Legacy APIs are
cached by our CDN provider. You can determine if you've hit the cache based on
the ``X-Cache`` and ``X-Cache-Hits`` headers in the response.

Requests to the JSON, RSS and Legacy APIs also provide an ``ETag`` header. If
you're making a lot of repeated requests, ensure your API consumer will respect
this header to determine whether to actually repeat a request or not.

The XML-RPC API does not have the ability to indicate cached responses.

Rate limiting
~~~~~~~~~~~~~

Due to the heavy caching and CDN use, there is currently no rate limiting of
PyPI APIs at the edge. The XML-RPC API may be rate limited if usage is causing
degradation of service.

In addition, PyPI reserves the right to temporarily or permanently prohibit a
consumer based on irresponsible activity.

If you plan to make a lot of requests to a PyPI API, adhere to these
suggestions:

* Set your consumer's ``User-Agent`` header to uniquely identify your requests.
  Adding your contact information to this value would be helpful as well.
* Try not to make a lot of requests (thousands) in a short amount of time
  (minutes). Generally PyPI can handle it, but it's preferred to make requests
  in serial over a longer amount of time if possible.
* If your consumer is actually an organization or service that will be
  downloading a lot of packages from PyPI, consider `using your own index
  mirror or cache
  <https://packaging.python.org/guides/index-mirrors-and-caches/>`_.

API Preference
~~~~~~~~~~~~~~

For periodically checking for new packages or updates to existing packages,
use our RSS feeds.

No new integrations should use the XML-RPC APIs as they are planned for
deprecation. Existing consumers should migrate to JSON/RSS/Legacy APIs.

Available APIs & Datasets
-------------------------

.. toctree::
    :maxdepth: 2

    feeds
    json
    legacy
    stats
    xml-rpc
    integration-guide
    bigquery-dataset
