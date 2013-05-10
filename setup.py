#!/usr/bin/env python
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
        # We depend on Django>=1.6 but until it's released we can't depend on
        #   it here.
        "Django",
        "django-braces",
        "django-configurations>=0.2.1",
    ],
    extras_require={
        "tests": [
            "django-webtest",
            "pretend",
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
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3.3",
    ],

    zip_safe=False,
)
