Stats API
=========

PyPI offers a JSON stats endpoint via a ``Accept: application/json`` GET
request. Without the ``Accept`` header set, you will be returned a HTML page.

**Example Client**: https://github.com/cooperlees/pypistats

Project
-------

.. http:get:: /stats/

    Returns statistics in JSON format. This includes:
    - Total size of PyPI packages in bytes
    - Top 100 packages + their size in bytes

    **Example Request**:

    - `curl -H "Content-Type: application/json" -H "Accept: application/json" https://pypi.org/stats/`

    .. code:: http

        GET /stats HTTP/1.1
        Host: pypi.org
        Accept: application/json
        Content-Type: application/json

    **Example response**:

    .. code:: json

      {
        "top_packages": {
          "CodeIntel": {
            "size": 23767329521
          },
          "Fiona": {
            "size": 6209535709
          },
          "FlexGet": {
            "size": 4387002448
          },
          ...
        },
        "total_packages_size": 23965450269
      }

    :statuscode 200: no error
