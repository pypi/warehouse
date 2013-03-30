#!/usr/bin/env python
from setuptools import setup, find_packages

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
        # We depend on Django>=1.6 but until it's released we can't depend on it
        #   here.
        "Django",
        "PyYAML",
    ],
    extras_require={
        "tests": [
            "pytest",
            "pytest-cov",
            "pytest-django",
        ],
    },

    packages=find_packages(exclude=["tests"]),

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

    zip_safe=False,
)
