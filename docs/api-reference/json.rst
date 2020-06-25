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

{   'info': {   'author': 'A. Random Developer',
                'author_email': 'author@example.com',
                'bugtrack_url': None,
                'classifiers': [   'Development Status :: 3 - Alpha',
                                   'Intended Audience :: Developers',
                                   'License :: OSI Approved :: MIT License',
                                   'Programming Language :: Python :: 3',
                                   'Programming Language :: Python :: 3.5',
                                   'Programming Language :: Python :: 3.6',
                                   'Programming Language :: Python :: 3.7',
                                   'Programming Language :: Python :: 3.8',
                                   'Programming Language :: Python :: 3 :: '
                                   'Only',
                                   'Topic :: Software Development :: Build '
                                   'Tools'],
                'description': '# A sample Python project\n'
                               '\n'
                               '![Python '
                               'Logo](https://www.python.org/static/community_logos/python-logo.png '
                               '"Sample inline image")\n'
                               '\n'
                               'A sample project that exists as an aid to the '
                               '[Python Packaging User\n'
                               "Guide][packaging guide]'s [Tutorial on "
                               'Packaging and Distributing\n'
                               'Projects][distribution tutorial].\n'
                               '\n'
                               'This project does not aim to cover best '
                               'practices for Python project\n'
                               'development as a whole. For example, it does '
                               'not provide guidance or tool\n'
                               'recommendations for version control, '
                               'documentation, or testing.\n'
                               '\n'
                               '[The source for this project is available '
                               'here][src].\n'
                               '\n'
                               'Most of the configuration for a Python project '
                               'is done in the `setup.py` file,\n'
                               'an example of which is included in this '
                               'project. You should edit this file\n'
                               'accordingly to adapt this sample project to '
                               'your needs.\n'
                               '\n'
                               '----\n'
                               '\n'
                               'This is the README file for the project.\n'
                               '\n'
                               'The file should use UTF-8 encoding and can be '
                               'written using\n'
                               '[reStructuredText][rst] or [markdown][md use] '
                               'with the appropriate [key set][md\n'
                               'use]. It will be used to generate the project '
                               'webpage on PyPI and will be\n'
                               'displayed as the project homepage on common '
                               'code-hosting services, and should be\n'
                               'written for that purpose.\n'
                               '\n'
                               'Typical contents for this file would include '
                               'an overview of the project, basic\n'
                               'usage examples, etc. Generally, including the '
                               'project changelog in here is not a\n'
                               "good idea, although a simple “What's New” "
                               'section for the most recent version\n'
                               'may be appropriate.\n'
                               '\n'
                               '[packaging guide]: '
                               'https://packaging.python.org\n'
                               '[distribution tutorial]: '
                               'https://packaging.python.org/tutorials/packaging-projects/\n'
                               '[src]: https://github.com/pypa/sampleproject\n'
                               '[rst]: '
                               'http://docutils.sourceforge.net/rst.html\n'
                               '[md]: '
                               'https://tools.ietf.org/html/rfc7764#section-3.5 '
                               '"CommonMark variant"\n'
                               '[md use]: '
                               'https://packaging.python.org/specifications/core-metadata/#description-content-type-optional\n'
                               '\n'
                               '\n',
                'description_content_type': 'text/markdown',
                'docs_url': None,
                'download_url': '',
                'downloads': {   'last_day': -1,
                                 'last_month': -1,
                                 'last_week': -1},
                'home_page': 'https://github.com/pypa/sampleproject',
                'keywords': 'sample setuptools development',
                'license': '',
                'maintainer': '',
                'maintainer_email': '',
                'name': 'sampleproject',
                'package_url': 'https://pypi.org/project/sampleproject/',
                'platform': '',
                'project_url': 'https://pypi.org/project/sampleproject/',
                'project_urls': {   'Bug Reports': 'https://github.com/pypa/sampleproject/issues',
                                    'Funding': 'https://donate.pypi.org',
                                    'Homepage': 'https://github.com/pypa/sampleproject',
                                    'Say Thanks!': 'http://saythanks.io/to/example',
                                    'Source': 'https://github.com/pypa/sampleproject/'},
                'release_url': 'https://pypi.org/project/sampleproject/2.0.0/',
                'requires_dist': [   'peppercorn',
                                     "check-manifest ; extra == 'dev'",
                                     "coverage ; extra == 'test'"],
                'requires_python': '>=3.5, <4',
                'summary': 'A sample Python project',
                'version': '2.0.0',
                'yanked': False,
                'yanked_reason': None},
    'last_serial': 7562906,
    'releases': {   '1.0': [],
                    '1.2.0': [   {   'comment_text': '',
                                     'digests': {   'md5': 'bab8eb22e6710eddae3c6c7ac3453bd9',
                                                    'sha256': '7a7a8b91086deccc54cac8d631e33f6a0e232ce5775c6be3dc44f86c2154019d'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.2.0-py2.py3-none-any.whl',
                                     'has_sig': False,
                                     'md5_digest': 'bab8eb22e6710eddae3c6c7ac3453bd9',
                                     'packagetype': 'bdist_wheel',
                                     'python_version': '2.7',
                                     'requires_python': None,
                                     'size': 3795,
                                     'upload_time': '2015-06-14T14:38:05',
                                     'upload_time_iso_8601': '2015-06-14T14:38:05.875222Z',
                                     'url': 'https://files.pythonhosted.org/packages/30/52/547eb3719d0e872bdd6fe3ab60cef92596f95262
e925e1943f68f840df88/sampleproject-1.2.0-py2.py3-none-any.whl',
                                     'yanked': False,
                                     'yanked_reason': None},
                                 {   'comment_text': '',
                                     'digests': {   'md5': 'd3bd605f932b3fb6e91f49be2d6f9479',
                                                    'sha256': '3427a8a5dd0c1e176da48a44efb410875b3973bd9843403a0997e4187c408dc1'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.2.0.tar.gz',
                                     'has_sig': False,
                                     'md5_digest': 'd3bd605f932b3fb6e91f49be2d6f9479',
                                     'packagetype': 'sdist',
                                     'python_version': 'source',
                                     'requires_python': None,
                                     'size': 3148,
                                     'upload_time': '2015-06-14T14:37:56',
                                     'upload_time_iso_8601': '2015-06-14T14:37:56.383366Z',
                                     'url': 'https://files.pythonhosted.org/packages/eb/45/79be82bdeafcecb9dca474cad4003e32ef8e4a0d
ec6abbd4145ccb02abe1/sampleproject-1.2.0.tar.gz',
                                     'yanked': False,
                                     'yanked_reason': None}],
                    '1.3.0': [   {   'comment_text': '',
                                     'digests': {   'md5': 'de98c6cdd6962d67e7368d2f9d9fa934',
                                                    'sha256': 'ab855ea282734dd216e8be4a42899a6fa8d2ce8f65b41c6379b69c1f804d6b1c'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.3.0-py2.py3-none-any.whl',
                                     'has_sig': False,
                                     'md5_digest': 'de98c6cdd6962d67e7368d2f9d9fa934',
                                     'packagetype': 'bdist_wheel',
                                     'python_version': 'py2.py3',
                                     'requires_python': '>=2.7, !=3.0.*, '
                                                        '!=3.1.*, !=3.2.*, '
                                                        '!=3.3.*, <4',
                                     'size': 3988,
                                     'upload_time': '2019-05-28T20:23:12',
                                     'upload_time_iso_8601': '2019-05-28T20:23:12.721927Z',
                                     'url': 'https://files.pythonhosted.org/packages/a1/fd/3564a5176430eac106c27eff4de50b58fc916f50
83782062cea3141acfaa/sampleproject-1.3.0-py2.py3-none-any.whl',
                                     'yanked': False,
                                     'yanked_reason': None},
                                 {   'comment_text': '',
                                     'digests': {   'md5': '3dd8fce5e4e2726f343de4385ec8d479',
                                                    'sha256': 'ee67ab9c8b445767203e7d9523d029287f737c60524a3c0e0c36cc504e0f24d7'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.3.0.tar.gz',
                                     'has_sig': False,
                                     'md5_digest': '3dd8fce5e4e2726f343de4385ec8d479',
                                     'packagetype': 'sdist',
                                     'python_version': 'source',
                                     'requires_python': '>=2.7, !=3.0.*, '
                                                        '!=3.1.*, !=3.2.*, '
                                                        '!=3.3.*, <4',
                                     'size': 5913,
                                     'upload_time': '2019-05-28T20:23:13',
                                     'upload_time_iso_8601': '2019-05-28T20:23:13.940627Z',
                                     'url': 'https://files.pythonhosted.org/packages/a6/aa/0090d487d204f5de30035c00f6c71b53ec7f6131
38d8653eebac50f47f45/sampleproject-1.3.0.tar.gz',
                                     'yanked': False,
                                     'yanked_reason': None}],
                    '1.3.1': [   {   'comment_text': '',
                                     'digests': {   'md5': '0cf94b45deeeb876f1619d9c27cff120',
                                                    'sha256': '26c9172e08244873b0e09c574a229bf2c251c67723a05e08fd3ec0c5ee423796'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.3.1-py2.py3-none-any.whl',
                                     'has_sig': False,
                                     'md5_digest': '0cf94b45deeeb876f1619d9c27cff120',
                                     'packagetype': 'bdist_wheel',
                                     'python_version': 'py2.py3',
                                     'requires_python': '>=2.7, !=3.0.*, '
                                                        '!=3.1.*, !=3.2.*, '
                                                        '!=3.3.*, !=3.4.*, <4',
                                     'size': 3991,
                                     'upload_time': '2019-11-04T20:36:25',
                                     'upload_time_iso_8601': '2019-11-04T20:36:25.256613Z',
                                     'url': 'https://files.pythonhosted.org/packages/a4/95/7398f8a08a0e83dc39dd4cbada9d22c65bcbb41c
36626b2c54a1db83c710/sampleproject-1.3.1-py2.py3-none-any.whl',
                                     'yanked': False,
                                     'yanked_reason': None},
                                 {   'comment_text': '',
                                     'digests': {   'md5': '65aafafd304b27436fe7e5a53993471e',
                                                    'sha256': '75bb5bb4e74a1b77dc0cff25ebbacb54fe1318aaf99a86a036cefc86ed885ced'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.3.1-py3-none-any.whl',
                                     'has_sig': False,
                                     'md5_digest': '65aafafd304b27436fe7e5a53993471e',
                                     'packagetype': 'bdist_wheel',
                                     'python_version': 'py3',
                                     'requires_python': '>=2.7, !=3.0.*, '
                                                        '!=3.1.*, !=3.2.*, '
                                                        '!=3.3.*, !=3.4.*, <4',
                                     'size': 4208,
                                     'upload_time': '2020-06-25T19:00:04',
                                     'upload_time_iso_8601': '2020-06-25T19:00:04.654819Z',
                                     'url': 'https://files.pythonhosted.org/packages/17/b4/8aac28f6f9d5c97c74f077567e9d418adab96fb3
1aa9a0f398145635f8d0/sampleproject-1.3.1-py3-none-any.whl',
                                     'yanked': False,
                                     'yanked_reason': None},
                                 {   'comment_text': '',
                                     'digests': {   'md5': '76ddb449e0e9ef3f55b880f566fcb700',
                                                    'sha256': '3593ca2f1e057279d70d6144b14472fb28035b1da213dde60906b703d6f82c55'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-1.3.1.tar.gz',
                                     'has_sig': False,
                                     'md5_digest': '76ddb449e0e9ef3f55b880f566fcb700',
                                     'packagetype': 'sdist',
                                     'python_version': 'source',
                                     'requires_python': '>=2.7, !=3.0.*, '
                                                        '!=3.1.*, !=3.2.*, '
                                                        '!=3.3.*, !=3.4.*, <4',
                                     'size': 5920,
                                     'upload_time': '2019-11-04T20:36:26',
                                     'upload_time_iso_8601': '2019-11-04T20:36:26.798325Z',
                                     'url': 'https://files.pythonhosted.org/packages/6f/5b/2f3fe94e1c02816fe23c7ceee5292fb186912929
e1972eee7fb729fa27af/sampleproject-1.3.1.tar.gz',
                                     'yanked': False,
                                     'yanked_reason': None}],
                    '2.0.0': [   {   'comment_text': '',
                                     'digests': {   'md5': '34b3750e8a39e7c2930cac64cd44ca0a',
                                                    'sha256': '2b0c55537193b792098977fdb62f0acbaeb2c3cfc56d0e24ccab775201462e04'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-2.0.0-py3-none-any.whl',
                                     'has_sig': False,
                                     'md5_digest': '34b3750e8a39e7c2930cac64cd44ca0a',
                                     'packagetype': 'bdist_wheel',
                                     'python_version': 'py3',
                                     'requires_python': '>=3.5, <4',
                                     'size': 4209,
                                     'upload_time': '2020-06-25T19:09:43',
                                     'upload_time_iso_8601': '2020-06-25T19:09:43.103653Z',
                                     'url': 'https://files.pythonhosted.org/packages/b8/f7/dd9223b39f683690c30f759c876df0944815e47b
588cb517e4b9e652bcf7/sampleproject-2.0.0-py3-none-any.whl',
                                     'yanked': False,
                                     'yanked_reason': None},
                                 {   'comment_text': '',
                                     'digests': {   'md5': '7414660845e963b2a0e4d52c6d4a111f',
                                                    'sha256': 'd99de34ffae5515db43916ec47380d3c603e9dead526f96581b48c070cc816d3'},
                                     'downloads': -1,
                                     'filename': 'sampleproject-2.0.0.tar.gz',
                                     'has_sig': False,
                                     'md5_digest': '7414660845e963b2a0e4d52c6d4a111f',
                                     'packagetype': 'sdist',
                                     'python_version': 'source',
                                     'requires_python': '>=3.5, <4',
                                     'size': 7298,
                                     'upload_time': '2020-06-25T19:09:43',
                                     'upload_time_iso_8601': '2020-06-25T19:09:43.925879Z',
                                     'url': 'https://files.pythonhosted.org/packages/8d/c7/bf2d01f14bc647c4ef2299dec830560a9b55a582
ecf9e0e43af740c79ccd/sampleproject-2.0.0.tar.gz',
                                     'yanked': False,
                                     'yanked_reason': None}]},
    'urls': [   {   'comment_text': '',
                    'digests': {   'md5': '34b3750e8a39e7c2930cac64cd44ca0a',
                                   'sha256': '2b0c55537193b792098977fdb62f0acbaeb2c3cfc56d0e24ccab775201462e04'},
                    'downloads': -1,
                    'filename': 'sampleproject-2.0.0-py3-none-any.whl',
                    'has_sig': False,
                    'md5_digest': '34b3750e8a39e7c2930cac64cd44ca0a',
                    'packagetype': 'bdist_wheel',
                    'python_version': 'py3',
                    'requires_python': '>=3.5, <4',
                    'size': 4209,
                    'upload_time': '2020-06-25T19:09:43',
                    'upload_time_iso_8601': '2020-06-25T19:09:43.103653Z',
                    'url': 'https://files.pythonhosted.org/packages/b8/f7/dd9223b39f683690c30f759c876df0944815e47b588cb517e4b9e652b
cf7/sampleproject-2.0.0-py3-none-any.whl',
                    'yanked': False,
                    'yanked_reason': None},
                {   'comment_text': '',
                    'digests': {   'md5': '7414660845e963b2a0e4d52c6d4a111f',
                                   'sha256': 'd99de34ffae5515db43916ec47380d3c603e9dead526f96581b48c070cc816d3'},
                    'downloads': -1,
                    'filename': 'sampleproject-2.0.0.tar.gz',
                    'has_sig': False,
                    'md5_digest': '7414660845e963b2a0e4d52c6d4a111f',
                    'packagetype': 'sdist',
                    'python_version': 'source',
                    'requires_python': '>=3.5, <4',
                    'size': 7298,
                    'upload_time': '2020-06-25T19:09:43',
                    'upload_time_iso_8601': '2020-06-25T19:09:43.925879Z',
                    'url': 'https://files.pythonhosted.org/packages/8d/c7/bf2d01f14bc647c4ef2299dec830560a9b55a582ecf9e0e43af740c79
ccd/sampleproject-2.0.0.tar.gz',
                    'yanked': False,
                    'yanked_reason': None}
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
