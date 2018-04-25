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

        GET /pypi/pip/json HTTP/1.1
        Host: pypi.org
        Accept: application/json

    **Example response**:

    .. code:: http

        HTTP/1.1 200 OK
        Content-Type: application/json; charset="UTF-8"

        {
            "info": {
                "author": "The pip developers",
                "author_email": "python-virtualenv@groups.google.com",
                "bugtrack_url": "",
                "classifiers": [
                    "Development Status :: 5 - Production/Stable",
                    "Intended Audience :: Developers",
                    "License :: OSI Approved :: MIT License",
                    "Programming Language :: Python :: 2",
                    "Programming Language :: Python :: 2.6",
                    "Programming Language :: Python :: 2.7",
                    "Programming Language :: Python :: 3",
                    "Programming Language :: Python :: 3.3",
                    "Programming Language :: Python :: 3.4",
                    "Programming Language :: Python :: 3.5",
                    "Programming Language :: Python :: Implementation :: PyPy",
                    "Topic :: Software Development :: Build Tools"
                ],
                "description": "...",
                "description_content_type": null,
                "docs_url": null,
                "download_url": "",
                "downloads": {
                    "last_day": 0,
                    "last_month": 0,
                    "last_week": 0
                },
                "home_page": "https://pip.pypa.io/",
                "keywords": "easy_install distutils setuptools egg virtualenv",
                "license": "MIT",
                "maintainer": "",
                "maintainer_email": "",
                "name": "pip",
                "platform": "",
                "project_url": "https://pypi.org/project/pip/",
                "release_url": "https://pypi.org/project/pip/9.0.1/",
                "requires_dist": [
                    "mock; extra == 'testing'",
                    "pretend; extra == 'testing'",
                    "pytest; extra == 'testing'",
                    "scripttest (>=1.3); extra == 'testing'",
                    "virtualenv (>=1.10); extra == 'testing'"
                ],
                "requires_python": ">=2.6,!=3.0.*,!=3.1.*,!=3.2.*",
                "summary": "The PyPA recommended tool for installing Python packages.",
                "version": "9.0.1"
            },
            "releases": {
                ...,
                "9.0.1": [
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "297dbd16ef53bcef0447d245815f5144",
                            "sha256": "690b762c0a8460c303c089d5d0be034fb15a5ea2b75bdf565f40421f542fefb0"
                        },
                        "downloads": -1,
                        "filename": "pip-9.0.1-py2.py3-none-any.whl",
                        "has_sig": true,
                        "md5_digest": "297dbd16ef53bcef0447d245815f5144",
                        "packagetype": "bdist_wheel",
                        "python_version": "py2.py3",
                        "size": 1254803,
                        "upload_time": "2016-11-06T18:51:46",
                        "url": "https://files.pythonhosted.org/packages/b6/ac/7015eb97dc749283ffdec1c3a88ddb8ae03b8fad0f0e611408f196358da3/pip-9.0.1-py2.py3-none-any.whl"
                    },
                    {
                        "comment_text": "",
                        "digests": {
                            "md5": "35f01da33009719497f01a4ba69d63c9",
                            "sha256": "09f243e1a7b461f654c26a725fa373211bb7ff17a9300058b205c61658ca940d"
                        },
                        "downloads": -1,
                        "filename": "pip-9.0.1.tar.gz",
                        "has_sig": true,
                        "md5_digest": "35f01da33009719497f01a4ba69d63c9",
                        "packagetype": "sdist",
                        "python_version": "source",
                        "size": 1197370,
                        "upload_time": "2016-11-06T18:51:51",
                        "url": "https://files.pythonhosted.org/packages/11/b6/abcb525026a4be042b486df43905d6893fb04f05aac21c32c638e939e447/pip-9.0.1.tar.gz"
                    }
                ]
            },
            "urls": {
                ...
            }
        }

    :statuscode 200: no error

Release
-------

.. http:get:: /pypi/<project_name>/<version>/json

    Returns metadata about an individual release at a specific version,
    otherwise identical to ``/pypi/<project_name>/json``.
