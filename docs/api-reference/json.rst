JSON API
========

PyPI offers two JSON endpoints.

Project
-------

.. http:get:: /pypi/<project_name>/json

    Returns metadata (info) about an individual project at the latest version,
    a list of all releases for that project, and project URLs. Releases include
    the release name, URL, and MD5 and SHA256 hash digests, and are keyed by
    the release version string.

    **Example Request**:

    .. code:: http

        GET /pypi/sampleproject/json HTTP/1.1
        Host: pypi.org
        Accept: application/json

    **Example response**:

    .. code:: http

        HTTP/1.1 200 OK
        Content-Type: application/json; charset="UTF-8"

        {
            "info": {
                "author": "The Python Packaging Authority",
                "author_email": "pypa-dev@googlegroups.com",
                "bugtrack_url": "",
                "classifiers": [
                    "Development Status :: 3 - Alpha",
                    "Intended Audience :: Developers",
                    "License :: OSI Approved :: MIT License",
                    "Programming Language :: Python :: 2",
                    "Programming Language :: Python :: 2.6",
                    "Programming Language :: Python :: 2.7",
                    "Programming Language :: Python :: 3",
                    "Programming Language :: Python :: 3.2",
                    "Programming Language :: Python :: 3.3",
                    "Programming Language :: Python :: 3.4",
                    "Topic :: Software Development :: Build Tools"
                ],
                "description": "...",
                "description_content_type": null,
                "docs_url": null,
                "download_url": "UNKNOWN",
                "downloads": {
                    "last_day": -1,
                    "last_month": -1,
                    "last_week": -1
                },
                "home_page": "https://github.com/pypa/sampleproject",
                "keywords": "sample setuptools development",
                "license": "MIT",
                "maintainer": null,
                "maintainer_email": null,
                "name": "sampleproject",
                "package_url": "https://pypi.org/project/sampleproject/",
                "platform": "UNKNOWN",
                "project_url": "https://pypi.org/project/sampleproject/",
                "project_urls": {
                    "Download": "UNKNOWN",
                    "Homepage": "https://github.com/pypa/sampleproject"
                },
                "release_url": "https://pypi.org/project/sampleproject/1.2.0/",
                "requires_dist": null,
                "requires_python": null,
                "summary": "A sample Python project",
                "version": "1.2.0",
                "yanked": false,
                "yanked_reason": null
            },
            "last_serial": 1591652,
            "releases": {
                "1.0": [],
                "1.2.0": [
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "bab8eb22e6710eddae3c6c7ac3453bd9",
                            "sha256": "7a7a8b91086deccc54cac8d631e33f6a0e232ce5775c6be3dc44f86c2154019d"
                        },
                        "downloads": -1,
                        "filename": "sampleproject-1.2.0-py2.py3-none-any.whl",
                        "has_sig": false,
                        "md5_digest": "bab8eb22e6710eddae3c6c7ac3453bd9",
                        "packagetype": "bdist_wheel",
                        "python_version": "2.7",
                        "size": 3795,
                        "upload_time_iso_8601": "2015-06-14T14:38:05.093750Z",
                        "url": "https://files.pythonhosted.org/packages/30/52/547eb3719d0e872bdd6fe3ab60cef92596f95262e925e1943f68f840df88/sampleproject-1.2.0-py2.py3-none-any.whl",
                        "yanked": false,
                        "yanked_reason": null
                    },
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "d3bd605f932b3fb6e91f49be2d6f9479",
                            "sha256": "3427a8a5dd0c1e176da48a44efb410875b3973bd9843403a0997e4187c408dc1"
                        },
                        "downloads": -1,
                        "filename": "sampleproject-1.2.0.tar.gz",
                        "has_sig": false,
                        "md5_digest": "d3bd605f932b3fb6e91f49be2d6f9479",
                        "packagetype": "sdist",
                        "python_version": "source",
                        "size": 3148,
                        "upload_time_iso_8601": "2015-06-14T14:37:56Z",
                        "url": "https://files.pythonhosted.org/packages/eb/45/79be82bdeafcecb9dca474cad4003e32ef8e4a0dec6abbd4145ccb02abe1/sampleproject-1.2.0.tar.gz",
                        "yanked": false,
                        "yanked_reason": null
                    }
                ]
            },
            "urls": [
                {
                    "comment_text": "",
                    "digests": {
                        "md5": "bab8eb22e6710eddae3c6c7ac3453bd9",
                        "sha256": "7a7a8b91086deccc54cac8d631e33f6a0e232ce5775c6be3dc44f86c2154019d"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-1.2.0-py2.py3-none-any.whl",
                    "has_sig": false,
                    "md5_digest": "bab8eb22e6710eddae3c6c7ac3453bd9",
                    "packagetype": "bdist_wheel",
                    "python_version": "2.7",
                    "size": 3795,
                    "upload_time_iso_8601": "2015-06-14T14:38:05.234526",
                    "url": "https://files.pythonhosted.org/packages/30/52/547eb3719d0e872bdd6fe3ab60cef92596f95262e925e1943f68f840df88/sampleproject-1.2.0-py2.py3-none-any.whl",
                    "yanked": false,
                    "yanked_reason": null
                },
                {
                    "comment_text": "",
                    "digests": {
                        "md5": "d3bd605f932b3fb6e91f49be2d6f9479",
                        "sha256": "3427a8a5dd0c1e176da48a44efb410875b3973bd9843403a0997e4187c408dc1"
                    },
                    "downloads": -1,
                    "filename": "sampleproject-1.2.0.tar.gz",
                    "has_sig": false,
                    "md5_digest": "d3bd605f932b3fb6e91f49be2d6f9479",
                    "packagetype": "sdist",
                    "python_version": "source",
                    "size": 3148,
                    "upload_time_iso_8601": "2015-06-14T14:37:56.000001Z",
                    "url": "https://files.pythonhosted.org/packages/eb/45/79be82bdeafcecb9dca474cad4003e32ef8e4a0dec6abbd4145ccb02abe1/sampleproject-1.2.0.tar.gz",
                    "yanked": false,
                    "yanked_reason": null
                }
            ]
        }

    :statuscode 200: no error

Release
-------

.. http:get:: /pypi/<project_name>/<version>/json

    Returns metadata about an individual release at a specific version,
    otherwise identical to ``/pypi/<project_name>/json``.

    **Example Request**:

    .. code:: http

        GET /pypi/sampleproject/1.0/json HTTP/1.1
        Host: pypi.org
        Accept: application/json

    **Example response**:

    .. code:: http

        HTTP/1.1 200 OK
        Content-Type: application/json; charset="UTF-8"

        {
            "info": {
                "author": "",
                "author_email": "",
                "bugtrack_url": "",
                "classifiers": [],
                "description": "",
                "description_content_type": null,
                "docs_url": null,
                "download_url": "",
                "downloads": {
                    "last_day": -1,
                    "last_month": -1,
                    "last_week": -1
                },
                "home_page": "",
                "keywords": "",
                "license": "",
                "maintainer": "",
                "maintainer_email": "",
                "name": "sampleproject",
                "package_url": "https://pypi.org/project/sampleproject/",
                "platform": "",
                "project_url": "https://pypi.org/project/sampleproject/",
                "release_url": "https://pypi.org/project/sampleproject/1.0/",
                "requires_dist": null,
                "requires_python": null,
                "summary": "",
                "version": "1.0",
                "yanked": false,
                "yanked_reason": null
            },
            "last_serial": 1591652,
            "releases": {
                "1.0": [],
                "1.2.0": [
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "bab8eb22e6710eddae3c6c7ac3453bd9",
                            "sha256": "7a7a8b91086deccc54cac8d631e33f6a0e232ce5775c6be3dc44f86c2154019d"
                        },
                        "downloads": -1,
                        "filename": "sampleproject-1.2.0-py2.py3-none-any.whl",
                        "has_sig": false,
                        "md5_digest": "bab8eb22e6710eddae3c6c7ac3453bd9",
                        "packagetype": "bdist_wheel",
                        "python_version": "2.7",
                        "size": 3795,
                        "upload_time_iso_8601": "2015-06-14T14:38:05.869374Z",
                        "url": "https://files.pythonhosted.org/packages/30/52/547eb3719d0e872bdd6fe3ab60cef92596f95262e925e1943f68f840df88/sampleproject-1.2.0-py2.py3-none-any.whl",
                        "yanked": false,
                        "yanked_reason": null
                    },
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "d3bd605f932b3fb6e91f49be2d6f9479",
                            "sha256": "3427a8a5dd0c1e176da48a44efb410875b3973bd9843403a0997e4187c408dc1"
                        },
                        "downloads": -1,
                        "filename": "sampleproject-1.2.0.tar.gz",
                        "has_sig": false,
                        "md5_digest": "d3bd605f932b3fb6e91f49be2d6f9479",
                        "packagetype": "sdist",
                        "python_version": "source",
                        "size": 3148,
                        "upload_time_iso_8601": "2015-06-14T14:37:56.394783Z",
                        "url": "https://files.pythonhosted.org/packages/eb/45/79be82bdeafcecb9dca474cad4003e32ef8e4a0dec6abbd4145ccb02abe1/sampleproject-1.2.0.tar.gz",
                        "yanked": false,
                        "yanked_reason": null
                    }
                ]
            },
            "urls": []
        }

    :statuscode 200: no error


    .. _api_json_latest:

    There are three special ``<version>`` names that can be passed for any
    ``<project_name>``, to obtain a `Release`_ JSON response for various flavors
    of the latest available release for that project:

    * ``/pypi/<project_name>/latest/json``

        Redirects to the latest non-prerelease version of ``<project_name>``,
        if any exists. If none does exist, redirects instead to the latest
        pre-release version of ``<project_name>``.

        As of Oct 2020, this behavior is identical to that of the
        `Project`_ endpoint, and should return an identical JSON response.

    * ``/pypi/<project_name>/latest-stable/json``

        Redirects to the latest non-prerelease version of ``<project_name>``.
        If no non-prerelease versions exist, returns |http404|_.

    * ``/pypi/<project_name>/latest-unstable/json``

        Redirects to a JSON query for the latest version of ``<project_name>``,
        regardless of pre-release status.



.. |http404| replace:: ``404 Not Found``

.. _http404: https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.5
