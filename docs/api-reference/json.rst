JSON API
========

PyPI offers two JSON endpoints.

Project
-------

.. attention::
    The ``releases`` key on this response should be considered deprecated,
    and projects should shift to using the simple API (which can be accessed
    as JSON via PEP 691) to get this information where possible.

    In the future, the ``releases`` key may be removed from this response.


.. http:get:: /pypi/<project_name>/json

    Returns metadata (info) about an individual project at the latest version,
    a list of all releases for that project, and project URLs. Releases include
    the release name, URL, and MD5 and SHA256 hash digests, and are keyed by
    the release version string. Metadata returned comes from the values provided
    at upload time and does not necessarily match the content of the uploaded
    files. The first uploaded data for a release is stored, subsequent uploads
    do not update it.

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
            ],
            "vulnerabilities": []
        }

    :statuscode 200: no error

    On this endpoint, the ``vulnerabilities`` array provides a listing for
    any known vulnerabilities in the most recent release (none, for the example
    above). Use the release-specific endpoint documented below for precise
    control over this field.

Release
-------

.. attention::
    Previously this response included the ``releases`` key, which had the URLs
    for *all* files for every release of this project on PyPI. Due to stability
    concerns, this had to be removed from the release specific page, which now
    **ONLY** serves data specific to that release.

    To access all files, you should preferrably use the simple API, or otherwise
    use the non versioned json api at ``/pypi/<project_name>/json``.


.. http:get:: /pypi/<project_name>/<version>/json

    Returns metadata about an individual release at a specific version,
    otherwise identical to ``/pypi/<project_name>/json`` minus the
    ``releases`` key.

    **Example Request**:

    .. code:: http

        GET /pypi/sampleproject/1.2.0/json HTTP/1.1
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
                "version": "1.2.0",
                "yanked": false,
                "yanked_reason": null
            },
            "last_serial": 1591652,
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
            ],
            "vulnerabilities": []
        }

    :statuscode 200: no error

Known vulnerabilities
~~~~~~~~~~~~~~~~~~~~~

In the example above, the combination of the requested project and version
had no `known vulnerabilities <https://github.com/pypa/advisory-db>`_.
An example of a response for a project with known vulnerabilities is
provided below, with unrelated fields collapsed for readability.

.. code:: http

    GET /pypi/Django/3.0.2/json HTTP/1.1
    Host: pypi.org
    Accept: application/json

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
                "fixed_in": [
                    "2.2.18",
                    "3.0.12",
                    "3.1.6"
                ],
                "id": "PYSEC-2021-9",
                "link": "https://osv.dev/vulnerability/PYSEC-2021-9",
                "source": "osv"
            },
        ]
    }
