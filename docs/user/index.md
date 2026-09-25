# Welcome to PyPI User Documentation

The Python Package Index (PyPI), pronounced "pie-pea-eye"[^1], is the official package repository for Python. PyPI hosts packages created and shared by the global Python community.

As a Python user, you can use PyPI to find the code you need for your projects.

As a developer, you can use PyPI to publish and share your Python code with the world.

This documentation site (docs.pypi.org) covers how to use the PyPI website and [API](api/index.md). To learn about the codebase that powers PyPI itself, visit the [Warehouse documentation](https://warehouse.pypa.io).

## Contents

### Using PyPI

* [PyPI Basics](using-pypi/pypi-basics.md) - What PyPI is, and how projects, releases, and files relate to each other
* [Finding and Installing Packages](using-pypi/finding-and-installing.md) - Searching for packages and installing them with a package installer
* [Package Security](using-pypi/package-security/introduction.md) - A guide to assessing package security and avoiding common attacks
* [Troubleshooting](using-pypi/troubleshooting.md) - Solutions to common issues when using PyPI

### Configuring and Managing PyPI Projects

* [Choosing a Project Name](project-management/choosing-a-name.md) - Choosing a name, and why one might not be available
* [Name Retention](project-management/name-retention.md) - PyPI's policy (PEP 541) for reclaiming abandoned or unused project names
* [Project Descriptions](project-management/project-descriptions.md) - Writing short and long descriptions for your PyPI page
* [Project Metadata](project_metadata.md) - How PyPI displays and verifies project metadata, including project URLs
* [Archive Formats](archives.md) - Archive format restrictions PyPI enforces on wheels and source distributions
* [Storage Limits](project-management/storage-limits.md) - File and project size limits, and how to request an increase
* [Managing Project Collaborators](project-management/managing-collaborators.md) - Adding, removing, and transferring project collaborators
* [Yanking](project-management/yanking.md) - Marking a broken or vulnerable release as yanked, without deleting it
* [Archiving Projects](project-management/archiving-projects.md) - Marking a project as no longer maintained
* [Troubleshooting](project-management/troubleshooting.md) - Answers to common project management questions

### Publishing Projects to PyPI

* [Publishing to PyPI](publishing/publishing-to-pypi.md) - How to package and upload a new project or release
* [Trusted Publishing](trusted-publishers/index.md) - Publishing via OIDC, without long-lived API tokens
* [Attestations](attestations/index.md) - Cryptographically signing and verifying packages with PEP 740 attestations
* [Troubleshooting](publishing/troubleshooting.md) - Answers to common errors encountered when uploading a package

### Your PyPI Account

* [Managing Your Account](your-account/managing-your-account.md) - Account settings and profile configuration
* [Two-Factor Authentication](your-account/two-factor-authentication.md) - Setting up and using 2FA on your account
* [Account Recovery](your-account/account-recovery.md) - Recovering access to your PyPI account
* [Security Alerts](your-account/security-alerts.md) - Responding to security alerts and suspicious account activity

### Organization Accounts

* [Overview](organization-accounts/index.md) - What organization accounts are and who they're for
* [FAQs](organization-accounts/org-acc-faq.md) - Common questions about organization accounts
* [Roles and Entities](organization-accounts/roles-entities.md) - Organization roles, teams, and project-level permissions
* [Pricing and Payments](organization-accounts/pricing-and-payments.md) - Costs and billing for organization accounts
* [Support](organization-accounts/support.md) - Getting help with an organization account

### APIs & Data Integration

* [PyPI APIs](api/index.md) - Overview of the available APIs, caching, and rate limits
* [Index API](api/index-api.md) - The simple repository API used by installers
* [JSON API](api/json.md) - Structured project and release data
* [Upload API](api/upload.md) - Uploading packages programmatically
* [Integrity API](api/integrity.md) - Retrieving PEP 740 attestations and provenance for uploaded files
* [Stats API](api/stats.md) - Total and per-package size statistics
* [BigQuery Datasets](api/bigquery.md) - Public datasets for download statistics and project metadata
* [RSS Feeds](api/feeds.md) - Feeds for new and updated packages
* [Secret Reporting API](api/secrets.md) - Reporting exposed PyPI API tokens found in public places

### About PyPI

* [Who Maintains PyPI](about/who-maintains-pypi.md) - The PyPI maintainers and governance structure
* [Contributing](about/contributing.md) - How to contribute to PyPI and report issues or bugs
* [PyPI Roadmap](about/pypi-roadmap.md) - Upcoming features and improvements
* [Service Availability](about/service-availability.md) - Current status and service availability information
* [PyPI Statistics](about/pypi-statistics.md) - Usage and project statistics
* [Security and Internals](about/security-and-internals.md) - Technical security details and internal information
* [Getting Help](about/getting-help.md) - Resources and support for getting help with PyPI

## Help

* For general questions or support using PyPI, please see our [help page](about/getting-help.md)
* To report a bug or suggest a PyPI feature, submit an issue on the [Warehouse GitHub repository](https://github.com/pypi/warehouse)

## Contributing to the docs

We welcome contributions to this documentation! If you've noticed an error or would like to suggest an improvement, please open an issue on the [pypi/warehouse](https://github.com/pypi/warehouse) repository and add the [documentation](https://github.com/pypi/warehouse/issues?q=is%3Aopen+is%3Aissue+label%3Adocumentation) label.

[^1]: "PyPI" should be pronounced like "pie pea eye", specifically with the "PI" pronounced as individual letters, rather than a single sound. This minimizes confusion with the PyPy project, which is a popular alternative implementation of the Python language.
