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

        GET /pypi/visidata/json HTTP/1.1
        Host: pypi.org
        Accept: application/json

    **Example response**:

    .. code:: http

        HTTP/1.1 200 OK
        Content-Type: application/json; charset="UTF-8"

        {
            'info': {
                'author': 'Saul Pwanson',
                'author_email': 'visidata@saul.pw',
                'bugtrack_url': None,
                'classifiers': [
                        'Development Status :: 5 - Production/Stable',
                        'Environment :: Console',
                        'Environment :: Console :: Curses',
                        'Intended Audience :: Developers',
                        'Intended Audience :: Science/Research',
                        'Intended Audience :: System Administrators',
                        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
                        'Operating System :: OS Independent',
                        'Programming Language :: Python :: 3',
                        'Topic :: Database :: Front-Ends',
                        'Topic :: Office/Business :: Financial :: Spreadsheet',
                        'Topic :: Scientific/Engineering',
                        'Topic :: Scientific/Engineering :: Visualization',
                        'Topic :: Utilities'
                ],
                'description': '...',
                'description_content_type': '',
                'docs_url': None,
                'download_url': 'https://github.com/saulpw/visidata/tarball/1.2',
                'downloads': {'last_day': -1, 'last_month': -1, 'last_week': -1},
                'home_page': 'http://visidata.org',
                'keywords': 'console tabular data spreadsheet terminal viewer textpunkcurses csv hdf5 h5 xlsx excel tsv',
                'license': 'GPLv3',
                'maintainer': '',
                'maintainer_email': '',
                'name': 'visidata',
                'package_url': 'https://pypi.org/project/visidata/',
                'platform': '',
                'project_url': 'https://pypi.org/project/visidata/',
                'release_url': 'https://pypi.org/project/visidata/1.2/',
                'requires_dist': None,
                'requires_python': '>=3.4',
                'summary': 'curses interface for exploring and arranging tabular data',
                'version': '1.2'
            },
            'last_serial': 3829208,
            'releases': {
                ...,
                '1.2': [
                    {
                        'comment_text': '',
                        'digests': {
                            'md5': '2f6622b458e6be388e941067984add54',
                            'sha256': '042efc2c43edaf3c3f8bd1bbf3c5d515663db66c41e81eea5f8b09200c2744e1'
                        },
                        'downloads': -1,
                        'filename': 'visidata-1.2.tar.gz',
                        'has_sig': False,
                        'md5_digest': '2f6622b458e6be388e941067984add54',
                        'packagetype': 'sdist',
                        'python_version': 'source',
                        'size': 89712,
                        'upload_time': '2018-05-03T01:28:21',
                        'url': 'https://files.pythonhosted.org/packages/4f/f6/01acfae53ae901756bc7778fc8c6f1ee70d442b5190f8bfe7d54dd35bb19/visidata-1.2.tar.gz'
                    }
                ]
            },
            'urls': [
                {
                    'comment_text': '',
                    'digests': {
                        'md5': '2f6622b458e6be388e941067984add54',
                        'sha256': '042efc2c43edaf3c3f8bd1bbf3c5d515663db66c41e81eea5f8b09200c2744e1'
                    },
                    'downloads': -1,
                    'filename': 'visidata-1.2.tar.gz',
                    'has_sig': False,
                    'md5_digest': '2f6622b458e6be388e941067984add54',
                    'packagetype': 'sdist',
                    'python_version': 'source',
                    'size': 89712,
                    'upload_time': '2018-05-03T01:28:21',
                    'url': 'https://files.pythonhosted.org/packages/4f/f6/01acfae53ae901756bc7778fc8c6f1ee70d442b5190f8bfe7d54dd35bb19/visidata-1.2.tar.gz'
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

        GET /pypi/visidata/0.9/json HTTP/1.1
        Host: pypi.org
        Accept: application/json

    **Example response**:

    .. code:: http

        HTTP/1.1 200 OK
        Content-Type: application/json; charset="UTF-8"

        {
            'info': {
                'author': 'Saul Pwanson',
                'author_email': 'vd@saul.pw',
                'bugtrack_url': None,
                'classifiers': [
                    'Development Status :: 3 - Alpha',
                    'Environment :: Console',
                    'Environment :: Console :: Curses',
                    'Intended Audience :: Developers',
                    'Intended Audience :: Science/Research',
                    'Intended Audience :: System Administrators',
                    'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
                    'Operating System :: OS Independent',
                    'Programming Language :: Python :: 3',
                    'Topic :: Database :: Front-Ends',
                    'Topic :: Office/Business :: Financial :: Spreadsheet',
                    'Topic :: Scientific/Engineering',
                    'Topic :: Scientific/Engineering :: Visualization',
                    'Topic :: Utilities'
                ],
                'description': '...',
                'description_content_type': None,
                'docs_url': None,
                'download_url': 'https://github.com/saulpw/visidata/tarball/0.9',
                'downloads': {'last_day': -1, 'last_month': -1, 'last_week': -1},
                'home_page': 'http://github.com/saulpw/visidata',
                'keywords': 'console tabular data spreadsheet viewer textpunkcurses csv hdf5 h5 xlsx',
                'license': 'GPLv3',
                'maintainer': None,
                'maintainer_email': None,
                'name': 'visidata',
                'package_url': 'https://pypi.org/project/visidata/',
                'platform': 'UNKNOWN',
                'project_url': 'https://pypi.org/project/visidata/',
                'release_url': 'https://pypi.org/project/visidata/0.9/',
                'requires_dist': None,
                'requires_python': None,
                'summary': 'curses interface for exploring and arranging tabular data',
                'version': '0.9'
            },
            'last_serial': 3829208,
            'releases': {
                ...,
                '0.9': [
                    {
                        'comment_text': '',
                        'digests': {
                            'md5': '245dce35444551badceca00952ed3a93',
                            'sha256': '0d867db6ce49235f2e7a4529baac091819a97e263f1829a80c87642c12de051d'
                        },
                        'downloads': -1,
                        'filename': 'visidata-0.9.tar.gz',
                        'has_sig': False,
                        'md5_digest': '245dce35444551badceca00952ed3a93',
                        'packagetype': 'sdist',
                        'python_version': 'source',
                        'size': 38553,
                        'upload_time': '2017-06-29T02:09:14',
                        'url': 'https://files.pythonhosted.org/packages/68/10/713cd5b49453c091c6bdb9dc457b6ef2ed48712ddd1b7da2dbdae7dfc959/visidata-0.9.tar.gz'
                    }
                ],
                ..., # 'releases' will also show versions that were released after the one that you requested.
                '1.2': [
                    {
                        'comment_text': '',
                        'digests': {
                            'md5': '2f6622b458e6be388e941067984add54',
                            'sha256': '042efc2c43edaf3c3f8bd1bbf3c5d515663db66c41e81eea5f8b09200c2744e1'
                        },
                        'downloads': -1,
                        'filename': 'visidata-1.2.tar.gz',
                        'has_sig': False,
                        'md5_digest': '2f6622b458e6be388e941067984add54',
                        'packagetype': 'sdist',
                        'python_version': 'source',
                        'size': 89712,
                        'upload_time': '2018-05-03T01:28:21',
                        'url': 'https://files.pythonhosted.org/packages/4f/f6/01acfae53ae901756bc7778fc8c6f1ee70d442b5190f8bfe7d54dd35bb19/visidata-1.2.tar.gz'
                    }
                ]
            },
            'urls': [
                {
                    'comment_text': '',
                    'digests': {
                        'md5': '245dce35444551badceca00952ed3a93',
                        'sha256': '0d867db6ce49235f2e7a4529baac091819a97e263f1829a80c87642c12de051d'
                    },
                    'downloads': -1,
                    'filename': 'visidata-0.9.tar.gz',
                    'has_sig': False,
                    'md5_digest': '245dce35444551badceca00952ed3a93',
                    'packagetype': 'sdist',
                    'python_version': 'source',
                    'size': 38553,
                    'upload_time': '2017-06-29T02:09:14',
                    'url': 'https://files.pythonhosted.org/packages/68/10/713cd5b49453c091c6bdb9dc457b6ef2ed48712ddd1b7da2dbdae7dfc959/visidata-0.9.tar.gz'
                }
            ]
        }

    :statuscode 200: no error
