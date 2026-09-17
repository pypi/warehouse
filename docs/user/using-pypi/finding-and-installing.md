---
title: Finding and Installing Packages
---

# Finding and Installing Packages

## Finding packages

You can search for packages directly on the PyPI website. The search results can be filtered by [Trove Classifiers](https://pypi.org/classifiers/) — standardized labels that package authors apply to their projects to categorize things like intended audience, license, and supported Python versions. You can also filter by License, or by Python version (listed under "Programming Language").

## Installing packages

!!! warning
    Installing packages from PyPI means running third-party code, which carries inherent security risks. Before installing any package, we strongly recommend reading our [package security guide](package-security/introduction.md).

The standard tool for installing Python packages is [pip](https://pip.pypa.io/en/stable/). It is included with modern versions of Python. The official Python Packaging User Guide provides a [comprehensive tutorial on installing packages with pip](https://packaging.python.org/en/latest/tutorials/installing-packages/). The guide includes:

* [Ensuring you have pip available](https://packaging.python.org/en/latest/tutorials/installing-packages/#ensure-you-can-run-pip-from-the-command-line)
* [Installing packages from PyPI](https://packaging.python.org/en/latest/tutorials/installing-packages/#installing-from-pypi)
* [Using virtual environments to isolate dependencies](https://packaging.python.org/en/latest/tutorials/installing-packages/#creating-virtual-environments)

## Other package managers

While pip is the standard installer, the Python ecosystem has other popular package management tools that also use PyPI as their default package source. These tools often provide additional features like automatic dependency locking and integrated project management workflows.

Here are the installation guides for some common alternatives:

* [PDM](https://pdm-project.org/latest/)
* [Poetry](https://python-poetry.org/)
* [uv](https://docs.astral.sh/uv/)
