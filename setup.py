#!/usr/bin/env python
# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from setuptools import setup, find_packages

import warehouse


setup(
    name=warehouse.__title__,
    version=warehouse.__version__,

    description=warehouse.__summary__,
    long_description=open("README.rst").read(),
    url=warehouse.__uri__,
    license=warehouse.__license__,

    author=warehouse.__author__,
    author_email=warehouse.__email__,

    install_requires=[
        "bcrypt",
        # We depend on Django>=1.6 but until it's released we can't depend on
        #   it here.
        "Django",
        "django-braces",
        "django-configurations>=0.2.1",
        "psycopg2",
        "South>=0.8",
    ],
    extras_require={
        "tests": [
            "django-webtest",
            "mock",
            "pretend>=1.0",
            "pyquery",
            "pytest",
            "pytest-cov",
            "pytest-django>=2.3.0",
            "webtest",
        ],
    },

    packages=find_packages(exclude=["tests"]),
    package_data={
        "warehouse": [
            "static/*/LICENSE",
            "static/*.*",
            "templates/*.html",
            "templates/*.txt",
        ],
    },
    include_package_data=True,

    entry_points={
        "console_scripts": [
            "warehouse = warehouse.__main__:main",
        ],
    },

    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3.3",
    ],

    zip_safe=False,
)
