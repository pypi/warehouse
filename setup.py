#!/usr/bin/env python
from setuptools import setup

__about__ = {}

with open("warehouse/__about__.py") as fp:
    exec(fp.read(), None, __about__)


setup(
    name=__about__["__title__"],
    version=__about__["__version__"],

    description=__about__["__summary__"],
    long_description=open("README.rst").read(),
    url=__about__["__uri__"],
    license=__about__["__license__"],

    author=__about__["__author__"],
    author_email=__about__["__email__"],

    install_requires=[
        "Django>=1.6",
    ],
    extras_require={
        "tests": [
            "pytest",
            "pytest-django",
        ],
    },

    packages=[
        "warehouse",
    ],

    entry_points={
        "console_scripts": [
            "warehouse = warehouse.__main__:main",
        ],
    },

    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 2.7",
    ],
)
