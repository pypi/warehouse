---
title: PyPI Basics
---

# PyPI Basics

## Who uses PyPI?

PyPI serves two main audiences:

* **Package consumers**: Users who want to download and install code to use in their own projects
* **Package publishers (or maintainers)**: Users who want to share their code with the Python community

This section of the documentation focuses on helping **package consumers**. Documentation for package publishers can be found under *Configuring and managing PyPI projects* and *Publishing projects to PyPI*.

## Using package managers with PyPI

While you can browse and search for projects on the PyPI website, the most common way to interact with PyPI is through a package manager. The standard package manager included with Python is [pip](https://pip.pypa.io/). Other popular package management tools like [PDM](https://pdm-project.org/latest/), [Poetry](https://python-poetry.org/), and [uv](https://docs.astral.sh/uv/) also use PyPI as their default source for packages.

For information on installing packages with package managers, see [finding and installing packages](finding-and-installing.md).

## Projects, releases and files (packages) on PyPI

All software on PyPI is organized into projects. A project is a collection of releases and files, and information about them. Projects on PyPI are made and shared by other members of the Python community so that you can use them.

A "release" on PyPI is a specific version of a project. For example, the [requests](https://pypi.org/project/requests/) project has many releases, like "requests 2.10" and "requests 1.2.1". A release consists of one or more "files".

A "file", also known as a "package", on PyPI is something that you can download and install. Because of different hardware, operating systems, and file formats, a release may have several files (packages), like an archive containing source code or a binary [wheel](https://pypi.org/project/wheel/#files).

When you search for software on the PyPI website, the page you see is for a specific **release** of a project. It shows you:

* The project name and a description of what it does  
* The "Release files" tab, which shows the individual files (packages) for the release
* The "Security" tab, which provides shows security information about the release
* The "Release history" tab, which lists all available releases
    
## Project and release status

Sometimes, the status of a project or release can change:

* **Pre-release**: A version of a package that is not yet considered stable for general use. Pre-releases are typically labelled with suffixes such as a (alpha), b (beta), or rc (release candidate) — for example, 1.0a1 or 2.3rc2. By default, installers such as pip will not install pre-release versions unless explicitly requested.
* **Yanked release**: A release that is always ignored by an installer, unless it is the only release that matches a version specifier (using either == or ===). A maintainer might yank a release if a critical bug is discovered.
* **Archived project**: A project that is no longer receiving any updates. A project maintainer can mark a project as archived to signal to users that future updates should not be expected. An archived project cannot make new releases and will not appear in PyPI's search results, but unlike a deleted or yanked release, it remains publicly visible and can still be installed as normal.
* **Quarantined project or release**: A project, or a single release within it, placed in quarantine for suspicion of malicious activity, spam, or other violations of the Terms of Service or Acceptable Use Policy. While in quarantine, the project or release cannot be installed by package installers, cannot be modified by its maintainers, and is excluded from PyPI's search results and index APIs. When a single release is quarantined, other releases of the same project are unaffected. PyPI Administrators must review it before it can be restored.

## Project data

PyPI is a public repository where anyone can upload projects of any quality. Because PyPI does not pre-screen or review projects before they are published, most of the information you see is provided by the project maintainers rather than PyPI itself.

When evaluating a project, it is important to distinguish between the three types of data on display:

* **PyPI data**: System metadata managed by PyPI (e.g., upload time, owners, maintainers).
* **Verified data**: Author-provided metadata that PyPI explicitly verified at the time of upload
* **Unverified data**: Author-provided metadata that PyPI did not check or validate

**Unless a piece of information is explicitly labeled as "PyPI data" or "Verified," assume it is unverified.**

For more information on metadata, please see our [project metadata](../project_metadata.md) documentation. For more information on security signals, see our [package security guide](package-security/introduction.md).

## A note on security

When you install a package from PyPI, you are choosing to execute code written by someone else on your machine. This is the foundation of modern software development, but it also carries inherent risks. A malicious or compromised package could steal data, damage your system, or create a backdoor into your application.

PyPI provides several security features to protect you, but the final decision to trust a package is yours. We strongly recommend reading our [package security guide](package-security/introduction.md) for guidance on how to assess package security and tips on how to protect yourself from common security attacks.
