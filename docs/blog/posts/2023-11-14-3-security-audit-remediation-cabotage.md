---
title: "Security Audit Remediation: cabotage"
description: A deeper dive into the remediation of the security audit findings for the cabotage project.
authors:
  - ewdurbin
date: 2023-11-14T00:00:02
tags:
  - security
  - transparency
  - infrastructure
links:
  - posts/2023-11-14-1-pypi-completes-first-security-audit.md
  - posts/2023-11-14-2-security-audit-remediation-warehouse.md
---

_This is part three in a three-part series.
See [part one here](2023-11-14-1-pypi-completes-first-security-audit.md),
and [part two here](2023-11-14-2-security-audit-remediation-warehouse.md)_.

This post is a deeper dive into the remediation of the security audit findings
for cabotage - the [codebase](https://github.com/cabotage/cabotage-app) that
deploys [PyPI](https://pypi.org) and its supporting services such as
[conveyor](https://github.com/pypi/conveyor),
[camo](https://github.com/pypi/camo),
and [inspector](https://github.com/pypi/inspector).

<!-- more -->

Relative to the [warehouse codebase](https://github.com/pypi/warehouse) that
*is* [PyPI](https://pypi.org), cabotage is not as widely known.
The goals of cabotage are to provide a seamless and secure way of deploying
arbitrary services into a [Kubernetes](https://kubernetes.io) cluster
in a "[Twelve-Factor](https://12factor.net)" style.
There are also a number of firm opinions baked into cabotage that provide
end-to-end TLS, protection against recovering secrets through the web UI,
and isolation between tenants inside the cluster.

cabotage was initially developed in 2018 as part of the
[Mozilla Open Source Support Award](https://pyfound.blogspot.com/2017/11/the-psf-awarded-moss-grant-pypi.html)
that enabled the [Python Software Foundation](https://python.org/psf/) (PSF)
to fund a team of contracted developers and a project manager to
complete the development and deployment of warehouse and sunset the
[original PyPI codebase](https://github.com/pypi/legacy).

A primary goal of cabotage is to reduce the PSF Infrastructure's
dependence on a specific provider for running PyPI,
while providing self-service of configuration for project administrators
and fully automated deployments.
It is in-effect a "Platform as a Service" that deploys applications
into bog-standard Kubernetes clusters, no YAML required.

To date, cabotage has deployed 3,901 releases to PyPI since 2018,
and 7,377 releases in total across its current services "fleet".

The audit report can be found [here](2023-11-14-1-pypi-completes-first-security-audit.md).
Reading that _before_ you dive in will provide the fullest context.

## Findings

Eleven findings resulted from the audit along with twelve code quality
suggestions.
This post will focus on the findings and their remediation.
Some of the code quality suggestions were implemented, others deferred.

Here's a table of the items that are relevant to cabotage, and their status:

| ID          | Title                                                             | Severity      | Difficulty   | Status                                                                                                                                             |
|-------------|-------------------------------------------------------------------|---------------|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| TOB-PYPI-3  | Vulnerable dependencies in cabotage                               | Undetermined  | Low          | [Remediated](https://github.com/cabotage/cabotage-app/compare/ad532ea0dcb7c3dd5228ee8b1312ddad9c70c6af...3e045eea677dd4af71239aad682c4b8ab3a39d3a) |
| TOB-PYPI-17 | Use of shell=True in subprocesses                                 | Medium        | Medium       | [Remediated](https://github.com/cabotage/cabotage-app/pull/36)                                                                                     |
| TOB-PYPI-18 | Use of HMAC with SHA1 for GitHub webhook payload validation       | Low           | High         | [Remediated](https://github.com/cabotage/cabotage-app/pull/37)                                                                                     |
| TOB-PYPI-19 | Potential container image manipulation through malicious Procfile | Medium        | High         | [Remediated](https://github.com/cabotage/cabotage-app/pull/39)                                                                                     |
| TOB-PYPI-20 | Repository confusion during image building                        | Medium        | Medium       | [Remediated](https://github.com/cabotage/cabotage-app/pull/46)                                                                                     |
| TOB-PYPI-21 | Brittle X.509 certificate rewriting                               | Informational | Undetermined | [Accepted](https://github.com/cabotage/cabotage-app/pull/38)                                                                                       |
| TOB-PYPI-22 | Unused dependencies in cabotage                                   | Informational | Undetermined | [Remediated](https://github.com/cabotage/cabotage-app/pull/35)                                                                                     |
| TOB-PYPI-24 | Missing resource integrity check of third-party resources         | Informational | High         | [Remediated](https://github.com/cabotage/cabotage-app/pull/40)                                                                                     |
| TOB-PYPI-25 | Brittle secret filtering in logs                                  | Medium        | Low          | [Remediated](https://github.com/cabotage/cabotage-app/pull/47)                                                                                     |
| TOB-PYPI-26 | Routes missing access controls                                    | Low           | High         | [Remediated](https://github.com/cabotage/cabotage-app/pull/41)                                                                                     |
| TOB-PYPI-28 | Deployment hook susceptible to race condition due to temp files   | Informational | High         | Remediated [1](https://github.com/cabotage/cabotage-app/pull/45), [2](https://github.com/cabotage/cabotage-app/pull/42)                            |

_IDs are non-consecutive, as the audit report included findings for Warehouse as well._

## Details

### TOB-PYPI-3:  Vulnerable dependencies in cabotage

The maintenance of cabotage has been primarily driven by the need for new
features or to mitigate issues raised. As a result dependency management and
upgrades have often been done as a byproduct of other changes.

During review, there were a number of dependencies with known vulnerabilities
found. Of the nine vulnerabilities noted, only
[GHSA-cg8c-gc2j-2wf7](https://github.com/advisories/GHSA-cg8c-gc2j-2wf7)
was determined impact cabotage and was remediated by migrating to the latest
release of the maintained fork of flask-security, flask-security-too
([diff](https://github.com/cabotage/cabotage-app/compare/3f3e2ba7753f8e4434b562d226118a0dfe873498...3e045eea677dd4af71239aad682c4b8ab3a39d3a)).

In order to avoid falling behind in this kind of maintenance, automated
dependency management was added along with updates to all of known vulnerable
dependencies
([diff](https://github.com/cabotage/cabotage-app/compare/ad532ea0dcb7c3dd5228ee8b1312ddad9c70c6af...3f3e2ba7753f8e4434b562d226118a0dfe873498)).

### TOB-PYPI-17:  Use of `shell=True` in subprocesses

An attack vector was identified in the way that cabotage calls out to
[`buildctl`](https://github.com/moby/buildkit/tree/master/cmd/buildctl) when
running container builds in development mode. A specifically crafted user-input
has the ability to run arbitrary shell commands on the application host.

Ultimately this was not determined to be exploitable in the production instance
of cabotage, since the shell commands were only used when building containers
in local development mode. The use of `shell=True` was removed none-the-less as
a matter of hygiene
([diff](https://github.com/cabotage/cabotage-app/pull/36/files)).

### TOB-PYPI-18:  Use of HMAC with SHA1 for GitHub webhook payload validation

Similar to the SNS verification finding in TOB-PYPI-2 for warehouse,
the endpoint that received webhook payloads from GitHub for automated
deployments was using SHA1 HMAC signatures to validate authenticity when SHA256
HMAC signatures were available.

The remediation of this finding was much more direct than the SNS finding, as
GitHub began sending the SHA256 signature in the header, does not require
any changes to the configuration of the webhook, and uses standard HMAC signing
supported by the Python standard library
([diff](https://github.com/cabotage/cabotage-app/pull/37/files)).

### TOB-PYPI-19:  Potential container image manipulation through malicious Procfile

Along the same lines as TOB-PYPI-17, some user-supplied values had the ability
to alter the cabotage controlled Dockerfile that specifies how release
containers are built, which should not be modifiable.
Through specifically crafted process names in the Procfile,
a user could alter the resulting Dockerfile by injecting newlines.

Remediation was straightforward by adding additional validation of user
supplied process names
([diff](https://github.com/cabotage/cabotage-app/pull/39/files)).

### TOB-PYPI-20:  Repository confusion during image building

Due to a quirk in GitHub's API for fetching references, a given reference may
return a concrete SHA/commit that belongs to a repository other than the one
specified in the API call. In this case by providing a reference that resolves
to a commit on a fork of the configured repository, a user of cabotage had the
ability to intentionally (or mistakenly) configure cabotage to deploy code
from a repository other than the one defined.

By adding additional validation inspired by [Chainguard](https://www.chainguard.dev)'s
[clank](https://github.com/chainguard-dev/clank/blob/a5c8412f4e8fb128d2c0919ec02d89f086afdd24/main.go#L242-L272)
tool, cabotage now verifies that the resulting SHA for a given reference
belongs to the configured repository
([diff](https://github.com/cabotage/cabotage-app/pull/46/files)).

### TOB-PYPI-21:  Brittle X.509 certificate rewriting

All containers built and deployed by cabotage are done so using short-lived
authentication tokens for an internally deployed Docker [registry](https://hub.docker.com/_/registry)
instance. The cabotage application itself provides this authentication and must
publish a public key that the registry can use to validate tokens.

In order to avoid handling private-key material in the application, cabotage
relies heavily on [Hashicorp Vault](https://www.vaultproject.io). The transit
backend for vault
[did not support publishing the required x509 certificate](https://github.com/hashicorp/vault/issues/3845)
that Docker registry required when cabotage was originally developed in 2018,
so some clever use of the cryptography library was employed to create the
necessary file [ref](https://github.com/cabotage/cabotage-app/blob/f01b75222280699dcaa99aff3ec60e1d1d1830fc/cabotage/utils/cert_hacks.py).

In the audit it was determined that this work around was brittle in the event
that an attacker had the ability to alter the length of the signature,
resulting in an invalid x509 certificate and broken authentication for
registry clients.

In practice, this has not been observed in the five and a half years that
it has been in production and the result of a successful attack would only lead
to deployments being halted. As such, we have accepted this finding for the
time being and will investigate the newly released x509 support in vault 1.15
and adopt it if able ([issue](https://github.com/cabotage/cabotage-app/issues/43)).

### TOB-PYPI-22:  Unused dependencies in cabotage

Similar to TOB-PYPI-3, dependency management for cabotage was lacking. This
led to a handful of dependencies being installed that could be additional
exposure to vulnerabilities or attacks.

By adopting [`pip-tools`](https://pypi.org/project/pip-tools/) to compile and pin dependencies, only the projects
necessary are installed
([diff](https://github.com/cabotage/cabotage-app/pull/35/files)).

### TOB-PYPI-24:  Missing resource integrity check of third-party resources

When adding support for a new feature, third party JavaScript was added
without subresource integrity information being added.
This addition guards against malicious replacement of JavaScript an is good
practice when loading any third party code.

Remediation was simple, by ensuring that all CDN loaded JavaScript had the
correct value set
([diff](https://github.com/cabotage/cabotage-app/pull/40/files)).

### TOB-PYPI-25:  Brittle secret filtering in logs

There was a brief period where cabotage supported building from private GitHub
repositories, which necessitated filtering build logs and removing the
plaintext authentication tokens.

This filtering was naive, but also no longer required. Remediation was removal
of the filtering code, and a comment directing a future developer to the
correct way of providing such authentication for builds in the future, should
building from private GitHub repositories be supported
([diff](https://github.com/cabotage/cabotage-app/pull/47/files)).

### TOB-PYPI-26:  Routes missing access controls

Another vestigial piece of code that allowed for the build context necessary
for container builds was identified as allowing for potentially non-public
information to be leaked if a release id (UUIDv4) was guessed or surmised.

This route was unauthenticated as a shortcut rather than adding a new
authentication method to cabotage itself.

This code was made defunct when cabotage began building from contexts pulled
directly from GitHub and supplied via Kubernetes secrets. Remediation was
again, a simple removal of the code
([diff](https://github.com/cabotage/cabotage-app/pull/41/files)).

### TOB-PYPI-28:  Deployment hook susceptible to race condition due to temp files

A final vestigial piece of code was also flagged as part of the audit which
was created to fetch and re-package source code from GitHub for deployments.
This had the very outside potential of being exploitable if an attacker
gained access to the filesystem that the cabotage app uses for temporary
files.

This was similarly made defunct when cabotage began building from contexts pulled
directly from GitHub. Remediation was a final simple removal of code
([diff-0](https://github.com/cabotage/cabotage-app/pull/45/files)),
and a refactor of how temporary files are created and opened
([diff-1](https://github.com/cabotage/cabotage-app/pull/42/files)).

## Summary

In addition to the specific findings, the Trail of Bits team also made a number
of "Code Quality Recommendations" and analyzed the overall maturity of the
codebase. Those sections of the report highlight one of the two themes I see
in the report regarding cabotage:

1. Overall the development experience and continuous integration environment for
cabotage is lacking.

2. There are countless minutiae that one must consider when writing code with
security in mind.

In the end, no show stopping or easily exploitable security issues were found,
which is a relief! Many of the most interesting security findings were only
exploitable by a malicious internal actor who
already had configuration permissions in cabotage,
was deploying their app there in the first place,
or had access to the underlying systems.

The takeaway I have as the sole author and maintainer of cabotage is pretty
resounding, and addresses both themes from the report:

> Projects with solo maintainers do not benefit from the accountability
> that comes with collaborative development, are prone to deprioritizing
> critical improvements to developer experience and testing, and don't
> have the extra sets of eyes that often assist in spotting small bugs or
> improper handling of security sensitive software.

So if you're interested in infrastructure and projects that make deploying
software securely and reliably more straightforward, I'd love to talk more.
Swing by the [cabotage repo](https://github.com/cabotage/cabotage-app)
and consider helping build the software that deploys PyPI,
and will soon be deploying more and more of the
[Python Software Foundation](https://python.org/psf/)'s infrastructure
as we migrate from previously gratis PaaS hosting providers.
