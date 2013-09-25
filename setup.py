#!/usr/bin/env python
# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function

from setuptools import setup, find_packages


about = {}
with open("warehouse/__about__.py") as fp:
    exec(fp.read(), about)


setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=open("README.rst").read(),
    license=about["__license__"],
    url=about["__uri__"],

    author=about["__author__"],
    author_email=about["__email__"],

    classifiers=[
        "License :: OSI Approved :: Apache Software License",

        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],

    packages=find_packages(),
    package_data={
        "warehouse": ["*.yml"],
        "warehouse.legacy": ["templates/*.html"],
        "warehouse.migrations": ["*.mako", "versions/*.py"],
    },

    install_requires=[
        "alembic",
        "Jinja2",
        "psycopg2cffi-compat",
        "PyYAML",
        "six",
        "SQLAlchemy",
        "sqlalchemy-citext>=1.1.0",
        "Werkzeug",
    ],

    entry_points={
        "console_scripts": [
            "warehouse = warehouse.__main__:main",
        ],
    },

    zip_safe=False,
)
