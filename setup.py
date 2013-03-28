#!/usr/bin/env python
import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand

__about__ = {}

with open("warehouse/__about__.py") as fp:
    exec(fp.read(), None, __about__)


class PyTest(TestCommand):

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # Import here, cause outside the eggs aren't loaded
        import pytest
        sys.exit(pytest.main(self.test_args))


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
    tests_requires=["pytest"],
    extras_require={
        "tests": ["pytest"],
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

    cmdclass={"test": PyTest},
)
