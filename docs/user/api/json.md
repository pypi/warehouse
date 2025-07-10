# JSON API

!!! tip

    This page documents the **PyPI-specific** JSON API.
    If all you need is a JSON index API (e.g. for retrieving)
    all distributions or all versions for a package, you
    can use the [Index API].

## Routes

### Get a project

Route: `GET /pypi/<project>/json`

Returns metadata (info) about an individual project at the latest version,
a list of all releases for that project, and project URLs. Releases include
the release name, URL, and hash digests for MD5, SHA256, and BLAKE2b-256,
and are keyed by the release version string. Metadata returned comes from
the values provided at upload time and does not necessarily match the
content of the uploaded files. The first uploaded data for a release is
stored, subsequent uploads do not update it.

On this endpoint, the `vulnerabilities` array provides a listing for
any known vulnerabilities in the most recent release (none, for the example
above). Use the release-specific endpoint documented below for precise
control over this field.

!!! warning "Deprecated keys"

    The following keys are considered deprecated:

    * `releases`: projects should shift to using the [Index API] to
      get this information, where possible.
    * `downloads`: this key is always `-1` and should not be used.
    * `has_sig`: this key is always `false` and should not be used.
    * `bugtrack_url`: this key is always `null` and should not be used.

    In the future, each of these keys may be removed entirely from
    this API response.

Status codes:

* `200 OK` - no error

Example request:

```http
GET /pypi/sampleproject/json HTTP/1.1
Host: pypi.org
Accept: application/json
```

??? "Example JSON response"

    ```http
    HTTP/1.1 200 OK
    Content-Type: application/json; charset="UTF-8"

    {
        "info": {
            "author": "",
            "author_email": "\"A. Random Developer\" <author@example.com>",
            "bugtrack_url": null,
            "classifiers": [
                "Development Status :: 3 - Alpha",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3 :: Only",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.11",
                "Programming Language :: Python :: 3.7",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Topic :: Software Development :: Build Tools"
            ],
            "description": "...",
            "description_content_type": "text/markdown",
            "docs_url": null,
            "download_url": "",
            "downloads": {
                "last_day": -1,
                "last_month": -1,
                "last_week": -1
            },
            "dynamic": [
                "requires_dist"
            ],
            "home_page": "",
            "keywords": "sample,setuptools,development",
            "license": "...",
            "maintainer": "",
            "maintainer_email": "\"A. Great Maintainer\" <maintainer@example.com>",
            "name": "sampleproject",
            "package_url": "https://pypi.org/project/sampleproject/",
            "platform": null,
            "project_url": "https://pypi.org/project/sampleproject/",
            "project_urls": {
                "Bug Reports": "https://github.com/pypa/sampleproject/issues",
                "Funding": "https://donate.pypi.org",
                "Homepage": "https://github.com/pypa/sampleproject",
                "Say Thanks!": "http://saythanks.io/to/example",
                "Source": "https://github.com/pypa/sampleproject/"
            },
            "provides_extra": [
                "dev",
                "test"
            ],
            "release_url": "https://pypi.org/project/sampleproject/3.0.0/",
            "requires_dist": [
                "peppercorn",
                "check-manifest ; extra == 'dev'",
                "coverage ; extra == 'test'"
            ],
            "requires_python": ">=3.7",
            "summary": "A sample Python project",
            "version": "3.0.0",
            "yanked": false,
            "yanked_reason": null
        },
        "last_serial": 15959178,
        "releases": {
            "1.0": [],
            "1.2.0": [
                {
                    "comment_text": "",
                    "digests": {
                        "blake2b_256": "3052547eb3719d0e872bdd6fe3ab60cef92596f95262e925e1943f68f840df88",
                        "md5": "bab8eb22e6710eddae3c6c7ac3453bd9",
                        "sha256": "7a7a8b91086deccc54cac8d631e33f6a0e232ce5775c6be3dc44f86c2154019d"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-1.2.0-py2.py3-none-any.whl",
                    "has_sig": false,
                    "md5_digest": "bab8eb22e6710eddae3c6c7ac3453bd9",
                    "packagetype": "bdist_wheel",
                    "python_version": "2.7",
                    "requires_python": null,
                    "size": 3795,
                    "upload_time": "2015-06-14T14:38:05",
                    "upload_time_iso_8601": "2015-06-14T14:38:05.875222Z",
                    "url": "https://files.pythonhosted.org/packages/30/52/547eb3719d0e872bdd6fe3ab60cef92596f95262e925e1943f68f840df88/sampleproject-1.2.0-py2.py3-none-any.whl",
                    "yanked": false,
                    "yanked_reason": null
                },
                {
                    "comment_text": "",
                    "digests": {
                        "blake2b_256": "eb4579be82bdeafcecb9dca474cad4003e32ef8e4a0dec6abbd4145ccb02abe1",
                        "md5": "d3bd605f932b3fb6e91f49be2d6f9479",
                        "sha256": "3427a8a5dd0c1e176da48a44efb410875b3973bd9843403a0997e4187c408dc1"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-1.2.0.tar.gz",
                    "has_sig": false,
                    "md5_digest": "d3bd605f932b3fb6e91f49be2d6f9479",
                    "packagetype": "sdist",
                    "python_version": "source",
                    "requires_python": null,
                    "size": 3148,
                    "upload_time": "2015-06-14T14:37:56",
                    "upload_time_iso_8601": "2015-06-14T14:37:56.383366Z",
                    "url": "https://files.pythonhosted.org/packages/eb/45/79be82bdeafcecb9dca474cad4003e32ef8e4a0dec6abbd4145ccb02abe1/sampleproject-1.2.0.tar.gz",
                    "yanked": false,
                    "yanked_reason": null
                }
            ],
            "1.3.0": [
                "..."
            ],
            "1.3.1": [
                "..."
            ],
            "2.0.0": [
                "..."
            ],
            "3.0.0": [
                {
                    "comment_text": "",
                    "digests": {
                        "blake2b_256": "eca85ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c",
                        "md5": "e46bfece301c915db29ade44a4932039",
                        "sha256": "2e52702990c22cf1ce50206606b769fe0dbd5646a32873916144bd5aec5473b3"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-3.0.0-py3-none-any.whl",
                    "has_sig": false,
                    "md5_digest": "e46bfece301c915db29ade44a4932039",
                    "packagetype": "bdist_wheel",
                    "python_version": "py3",
                    "requires_python": ">=3.7",
                    "size": 4662,
                    "upload_time": "2022-12-01T18:51:00",
                    "upload_time_iso_8601": "2022-12-01T18:51:00.007372Z",
                    "url": "https://files.pythonhosted.org/packages/ec/a8/5ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c/sampleproject-3.0.0-py3-none-any.whl",
                    "yanked": false,
                    "yanked_reason": null
                },
                {
                    "comment_text": "",
                    "digests": {
                        "blake2b_256": "672a9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca",
                        "md5": "46a92a8a919062028405fdf232b508b0",
                        "sha256": "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-3.0.0.tar.gz",
                    "has_sig": false,
                    "md5_digest": "46a92a8a919062028405fdf232b508b0",
                    "packagetype": "sdist",
                    "python_version": "source",
                    "requires_python": ">=3.7",
                    "size": 5330,
                    "upload_time": "2022-12-01T18:51:01",
                    "upload_time_iso_8601": "2022-12-01T18:51:01.420127Z",
                    "url": "https://files.pythonhosted.org/packages/67/2a/9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca/sampleproject-3.0.0.tar.gz",
                    "yanked": false,
                    "yanked_reason": null
                }
            ]
        },
        "urls": [
            {
                "comment_text": "",
                "digests": {
                    "blake2b_256": "eca85ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c",
                    "md5": "e46bfece301c915db29ade44a4932039",
                    "sha256": "2e52702990c22cf1ce50206606b769fe0dbd5646a32873916144bd5aec5473b3"
                },
                "downloads": -1,
                "filename": "sampleproject-3.0.0-py3-none-any.whl",
                "has_sig": false,
                "md5_digest": "e46bfece301c915db29ade44a4932039",
                "packagetype": "bdist_wheel",
                "python_version": "py3",
                "requires_python": ">=3.7",
                "size": 4662,
                "upload_time": "2022-12-01T18:51:00",
                "upload_time_iso_8601": "2022-12-01T18:51:00.007372Z",
                "url": "https://files.pythonhosted.org/packages/ec/a8/5ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c/sampleproject-3.0.0-py3-none-any.whl",
                "yanked": false,
                "yanked_reason": null
            },
            {
                "comment_text": "",
                "digests": {
                    "blake2b_256": "672a9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca",
                    "md5": "46a92a8a919062028405fdf232b508b0",
                    "sha256": "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
                },
                "downloads": -1,
                "filename": "sampleproject-3.0.0.tar.gz",
                "has_sig": false,
                "md5_digest": "46a92a8a919062028405fdf232b508b0",
                "packagetype": "sdist",
                "python_version": "source",
                "requires_python": ">=3.7",
                "size": 5330,
                "upload_time": "2022-12-01T18:51:01",
                "upload_time_iso_8601": "2022-12-01T18:51:01.420127Z",
                "url": "https://files.pythonhosted.org/packages/67/2a/9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca/sampleproject-3.0.0.tar.gz",
                "yanked": false,
                "yanked_reason": null
            }
        ],
        "vulnerabilities": []
    }
    ```

### Get a release

Route: `GET /pypi/<project>/<version>/json`

Returns metadata about an individual release at a specific version,
otherwise identical to `/pypi/<project_name>/json` minus the
`releases` key.

!!! tip

    This response previously included the `releases` key, which had the URLs
    for *all* files for every release of this project on PyPI. Due to stability
    concerns, this had to be removed from the release specific page, which now
    **only** serves data specific to that release.

    To access all files, you should preferably use the [Index API], or otherwise
    use the project-level JSON api at `/pypi/<project_name>/json`.


!!! warning "Deprecated keys"

    The following keys are considered deprecated:

    * `downloads`: this key is always `-1` and should not be used.
    * `has_sig`: this key is always `false` and should not be used.
    * `bugtrack_url`: this key is always `null` and should not be used.

    In the future, each of these keys may be removed entirely from
    this API response.

Status codes:

* `200 OK` - no error

Example request:

```http
GET /pypi/sampleproject/3.0.0/json HTTP/1.1
Host: pypi.org
Accept: application/json
```

??? "Example JSON response"

    ```http
    HTTP/1.1 200 OK
    Content-Type: application/json; charset="UTF-8"

    {
        "info": {
            "author": "",
            "author_email": "\"A. Random Developer\" <author@example.com>",
            "bugtrack_url": null,
            "classifiers": [
                "Development Status :: 3 - Alpha",
                "Intended Audience :: Developers",
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3 :: Only",
                "Programming Language :: Python :: 3.10",
                "Programming Language :: Python :: 3.11",
                "Programming Language :: Python :: 3.7",
                "Programming Language :: Python :: 3.8",
                "Programming Language :: Python :: 3.9",
                "Topic :: Software Development :: Build Tools"
            ],
            "description": "...",
            "description_content_type": "text/markdown",
            "docs_url": null,
            "download_url": "",
            "downloads": {
                "last_day": -1,
                "last_month": -1,
                "last_week": -1
            },
            "home_page": "",
            "keywords": "sample,setuptools,development",
            "license": "... ",
            "maintainer": "",
            "maintainer_email": "\"A. Great Maintainer\" <maintainer@example.com>",
            "name": "sampleproject",
            "package_url": "https://pypi.org/project/sampleproject/",
            "platform": null,
            "project_url": "https://pypi.org/project/sampleproject/",
            "project_urls": {
                "Bug Reports": "https://github.com/pypa/sampleproject/issues",
                "Funding": "https://donate.pypi.org",
                "Homepage": "https://github.com/pypa/sampleproject",
                "Say Thanks!": "http://saythanks.io/to/example",
                "Source": "https://github.com/pypa/sampleproject/"
            },
            "release_url": "https://pypi.org/project/sampleproject/3.0.0/",
            "requires_dist": [
                "peppercorn",
                "check-manifest ; extra == 'dev'",
                "coverage ; extra == 'test'"
            ],
            "requires_python": ">=3.7",
            "summary": "A sample Python project",
            "version": "3.0.0",
            "yanked": false,
            "yanked_reason": null
        },
        "last_serial": 15959178,
        "urls": [
            {
                "comment_text": "",
                "digests": {
                    "blake2b_256": "eca85ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c",
                    "md5": "e46bfece301c915db29ade44a4932039",
                    "sha256": "2e52702990c22cf1ce50206606b769fe0dbd5646a32873916144bd5aec5473b3"
                },
                "downloads": -1,
                "filename": "sampleproject-3.0.0-py3-none-any.whl",
                "has_sig": false,
                "md5_digest": "e46bfece301c915db29ade44a4932039",
                "packagetype": "bdist_wheel",
                "python_version": "py3",
                "requires_python": ">=3.7",
                "size": 4662,
                "upload_time": "2022-12-01T18:51:00",
                "upload_time_iso_8601": "2022-12-01T18:51:00.007372Z",
                "url": "https://files.pythonhosted.org/packages/ec/a8/5ec62d18adde798d33a170e7f72930357aa69a60839194c93eb0fb05e59c/sampleproject-3.0.0-py3-none-any.whl",
                "yanked": false,
                "yanked_reason": null
            },
            {
                "comment_text": "",
                "digests": {
                    "blake2b_256": "672a9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca",
                    "md5": "46a92a8a919062028405fdf232b508b0",
                    "sha256": "117ed88e5db073bb92969a7545745fd977ee85b7019706dd256a64058f70963d"
                },
                "downloads": -1,
                "filename": "sampleproject-3.0.0.tar.gz",
                "has_sig": false,
                "md5_digest": "46a92a8a919062028405fdf232b508b0",
                "packagetype": "sdist",
                "python_version": "source",
                "requires_python": ">=3.7",
                "size": 5330,
                "upload_time": "2022-12-01T18:51:01",
                "upload_time_iso_8601": "2022-12-01T18:51:01.420127Z",
                "url": "https://files.pythonhosted.org/packages/67/2a/9f056e5fa36e43ef1037ff85581a2963cde420457de0ef29c779d41058ca/sampleproject-3.0.0.tar.gz",
                "yanked": false,
                "yanked_reason": null
            }
        ],
        "vulnerabilities": []
    }
    ```

#### Known vulnerabilities

In the example above, the combination of the requested project and version
had no [known vulnerabilities].

An example of a response for a project with known vulnerabilities is
provided below, with unrelated fields collapsed for readability.

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset="UTF-8"

{
    "info": {},
    "last_serial": 12089094,
    "releases": {},
    "urls": [],
    "vulnerabilities": [
        {
            "aliases": [
                "CVE-2021-3281"
            ],
            "details": "In Django 2.2 before 2.2.18, 3.0 before 3.0.12, and 3.1 before 3.1.6, the django.utils.archive.extract method (used by \"startapp --template\" and \"startproject --template\") allows directory traversal via an archive with absolute paths or relative paths with dot segments.",
            "summary": "A shorter summary of the vulnerability",
            "fixed_in": [
                "2.2.18",
                "3.0.12",
                "3.1.6"
            ],
            "id": "PYSEC-2021-9",
            "link": "https://osv.dev/vulnerability/PYSEC-2021-9",
            "source": "osv",
            "withdrawn": null
        },
    ]
}
```

The `withdrawn` field is of particular interest: when non-`null`, it
contains the RFC 3339 timestamp when the vulnerability was withdrawn by an
upstream vulnerability reporting source. API consumers can use this field to
retract vulnerability reports that are later determined to be invalid.

For example, here is what a withdrawn vulnerability might look like:

```json
{
    "aliases": [
        "CVE-2022-XXXXX"
    ],
    "details": "A long description.",
    "summary": "A shorter summary.",
    "fixed_in": [
        "1.2.3"
    ],
    "id": "PYSEC-2022-XXX",
    "link": "https://osv.dev/vulnerability/PYSEC-2022-XXX",
    "source": "osv",
    "withdrawn": "2022-06-28T16:39:06Z"
}
```


[Index API]: ./index-api.md
[known vulnerabilities]: https://github.com/pypa/advisory-database
