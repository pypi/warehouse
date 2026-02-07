# Stats API

!!! important

    You **must** set `Accept: application/json` in your requests to this API.
    Without the `Accept` header, you will be returned an HTML page.

!!! tip

    An example stats API client can be found at @cooperlees/pypistats.

## Routes

### Project stats

Route: `GET /stats/`

Returns statistics in JSON format. This includes:

- Total size of PyPI packages in bytes
- Top 100 packages + their size in bytes

Status codes:

* `200 OK` - no error

Example request:

```http
GET /stats HTTP/1.1
Host: pypi.org
Accept: application/json
```

??? note "Example JSON response"

    ```json
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
        "...": "..."
      },
      "total_packages_size": 23965450269
    }
    ```
