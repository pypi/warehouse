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

import fnmatch
import os

from setuptools import setup, find_packages


def recursive_glob(path, pattern, cutdirs=0):
    matches = []
    for root, dirnames, filenames in os.walk(path):
        for filename in fnmatch.filter(filenames, pattern):
            filepath = os.path.join(root, filename)
            filepath = "/".join(filepath.split("/")[cutdirs:])
            matches.append(filepath)
    return matches


about = {}
with open("warehouse/__about__.py") as fp:
    exec(fp.read(), about)


with open("README.rst") as fp:
    long_description = fp.read()


setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=long_description,
    license=about["__license__"],
    url=about["__uri__"],

    author=about["__author__"],
    author_email=about["__email__"],

    classifiers=[
        "License :: OSI Approved :: Apache Software License",

        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
    ],

    packages=find_packages(),
    package_data={
        "warehouse": (
            ["*.yml"] + recursive_glob("warehouse/static", "*.*", 1) +
            recursive_glob("warehouse/templates", "*.*", 1)
        ),
        "warehouse.migrations": ["*.mako", "versions/*.py"],
    },

    install_requires=[
        "alembic",
        "arrow",
        "babel",
        "bcrypt",
        "elasticsearch",
        "guard",
        "html5lib",
        "Jinja2",
        "msgpack-python>=0.4.0",
        "passlib>=1.6.2",
        "psycopg2",
        "PyYAML",
        "raven",
        "readme>=0.2.0",
        "redis",
        "SQLAlchemy",
        "sqlalchemy-citext>=1.2.0",
        "Werkzeug",
        "whitenoise>=0.12",
        "WTForms>=1.0",
    ],

    entry_points={
        "console_scripts": [
            "warehouse = warehouse.__main__:main",
        ],
        "flake8.extension": [
            "E4 = warehouse.styleguide:FlaskSessionCheck",
        ],
    },

    zip_safe=False,
)
