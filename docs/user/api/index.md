# Introduction

<!--[[ preview('user-api-docs') ]]-->

PyPI has several API endpoints and public datasets, each of which is referenced
in the table of contents for this hierarchy.

## API policies

Please be aware of these PyPI API policies.

### Caching

All API requests are cached. Requests to the JSON, RSS or Index APIs are
cached by our CDN provider. You can determine if you've hit the cache based on
the `X-Cache` and `X-Cache-Hits` headers in the response.

Requests to the JSON, RSS and Index APIs also provide an `ETag` header. If
you're making a lot of repeated requests, ensure your API consumer will respect
this header to determine whether to actually repeat a request or not.

The XML-RPC API does not have the ability to indicate cached responses.

### Rate limiting

Due to the heavy caching and CDN use, there is currently no rate limiting of
PyPI APIs at the edge. The XML-RPC API may be rate limited if usage is causing
degradation of service.

In addition, PyPI reserves the right to temporarily or permanently prohibit a
consumer based on irresponsible activity.

If you plan to make a lot of requests to a PyPI API, adhere to these
suggestions:

* Set your consumer's `User-Agent` header to uniquely identify your requests.
  Adding your contact information to this value would be helpful as well.
* Try not to make a lot of requests (thousands) in a short amount of time
  (minutes). Generally PyPI can handle it, but it's preferred to make requests
  in serial over a longer amount of time if possible.
* If your consumer is actually an organization or service that will be
  downloading a lot of packages from PyPI, consider
  [using your own index mirror or cache].

### API Preference

For periodically checking for new packages or updates to existing packages,
use our RSS feeds.

No new integrations should use the XML-RPC APIs as they are planned for
deprecation. Existing consumers should migrate to JSON/RSS/[Index APIs].

[Index APIs]: ./index-api.md
[using your own index mirror or cache]: https://packaging.python.org/guides/index-mirrors-and-caches/

## Integration guide

Many tools already integrate with PyPI, uploading packages or
retrieving data; see [the Python Packaging Guide's tool recommendations].

### Migrating to the new PyPI

Warehouse has now replaced the legacy PyPI site that was deployed at
<https://pypi.python.org/>. If your site/service
used to link or upload to pypi.python.org, it may continue to work due
to redirects, but you should use <https://pypi.org> instead.

You should also watch [our status page] and subscribe to
[the PyPI blog] and
[the PyPI announcement list (low-traffic)] to find out about future changes.

Here are some tips.

!!! note

    `{name}` is the name of the package as represented in the URL;
    for `https://pypi.org/project/arrow/`, you'd insert `arrow`
    wherever you see `{name}`.

* If your client correctly follows redirects, you can replace
  `pypi.python.org` in your links with `pypi.org` and everything
  should just work. For instance, the project detail page
  `https://pypi.org/pypi/{name}` (with or without a trailing slash)
  redirects to `https://pypi.org/project/{name}/`.

* Shorter URL: `https://pypi.org/p/{name}/` will redirect to
  `https://pypi.org/project/{name}/`.

* All APIs: [access is HTTPS-only]
  (changed in October 2017). Furthermore, `pypi.org` honors an
  `Accept-Encoding: gzip` header, whereas `pypi.python.org` ignored it.

* JSON API: `https://pypi.org/pypi/{name}/json` returns the
  expected JSON response directly. See [JSON API].

* XML-RPC API: See [Changes to XMLRPC API]. Will be deprecated in
  the future (no specific end date set yet); switch to the [RSS Feeds],
  [Index API], or [JSON API].

* Packages/updates RSS feeds: `https://pypi.org/pypi?%3Aaction=rss`
  redirects to `https://pypi.org/rss/updates.xml`, and
  `https://pypi.org/pypi?%3Aaction=packages_rss` redirects to
  `https://pypi.org/rss/packages.xml`. See [RSS Feeds] for
  descriptions. The data differs from the legacy feed data because
  the new feeds are standards-compliant and fix inaccuracies in the
  publication date; see #3248 for more information.

* Documentation upload: Users can no longer use `doc_upload` in the
  API to upload documentation ZIP files, separate from packages, to be
  hosted at `pythonhosted.org`. See #509 for more information.

* `User-Agent` Filtering: Some client user agents were filtered to
  always use `legacy.pypi.org`, a temporary deployment of the legacy
  PyPI codebase, regardless of brownouts or redirects, in order to
  give them extra time to migrate. On 30 April 2018,
  `legacy.pypi.org` was shut down, so all clients use `pypi.org`
  regardless of their `User-Agent`.

* Subscribe to [the PyPI blog] and [the PyPI announcement list (low-traffic)].

If you're a PyPI end user or packager looking to migrate to the new
PyPI, [see the official Python Packaging User Guide on migrating to PyPI].

### Querying PyPI for Package URLs

When copying a download link from <https://pypi.org>, you get a URL with a
random hash value in it.

This hash value is calculated from the checksum of the file. The URLs on
PyPI for individual files are static and do not change.

### Official guidance

Query PyPI's [Index API] or [JSON API] to determine where to download files
from.

### Predictable URLs

You can use our conveyor service to fetch this file, which exists for
cases where using the API is impractical or impossible. This is for
example the case for Linux package maintainers, as package build scripts
or package metadata expect static URLs in some cases.

URLs can be constructed as follows, with wheel file names following
[PEP 491's file name convention].

```python
host = 'https://files.pythonhosted.org'

def source_url(name, version):
    return f'{host}/packages/source/{name[0]}/{name}/{name}-{version}.tar.gz'

def wheel_url(name, version, build_tag, python_tag, abi_tag, platform_tag):
    # https://www.python.org/dev/peps/pep-0491/#file-name-convention
    wheel_parts = {
        tag: re.sub(r'[^\w\d.]+', '_', part, re.UNICODE)
        for tag, part in locals().items()
    }
    wheel_parts['optional_build_tag'] = f'-{wheel_parts["build_tag"]}' if build_tag else ''
    filename = '{name}-{version}{optional_build_tag}-{python_tag}-{abi_tag}-{platform_tag}.whl'\
               .format_map(wheel_parts)
    return f'{host}/packages/{python_tag}/{name[0]}/{name}/{filename}'
```

Example predicable URL use:

```bash
$ curl -I https://files.pythonhosted.org/packages/source/v/virtualenv/virtualenv-15.2.0.tar.gz
HTTP/2 302
location: https://files.pythonhosted.org/packages/b1/72/2d70c5a1de409ceb3a27ff2ec007ecdd5cc52239e7c74990e32af57affe9/virtualenv-15.2.0.tar.gz
```

As you’ll note, it is just a redirect to the canonical file.

[the Python Packaging Guide's tool recommendations]: https://packaging.python.org/guides/tool-recommendations/

[our status page]: https://status.python.org/

[the PyPI announcement list (low-traffic)]: https://mail.python.org/mailman3/lists/pypi-announce.python.org/

[access is HTTPS-only]: https://mail.python.org/pipermail/distutils-sig/2017-October/031712.html

[RSS Feeds]: ./feeds.md

[see the official Python Packaging User Guide on migrating to PyPI]: https://packaging.python.org/guides/migrating-to-pypi-org/

[PEP 491's file name convention]: https://peps.python.org/pep-0491/#file-name-convention

[Index API]: ./index-api.md

[JSON API]: https://warehouse.pypa.io/api-reference/json/

[Changes to XMLRPC API]: https://warehouse.pypa.io/api-reference/xml-rpc.html#changes-to-xmlrpc-api

[the PyPI blog]: https://blog.pypi.org/
