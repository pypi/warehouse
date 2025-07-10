---
title: "Supply-chain attack analysis: Ultralytics"
description: Analysis of a package targeted by a supply-chain attack to the build and release process
authors:
  - sethmlarson
date: 2024-12-11
tags:
  - security
---

Last week, the Python project “[ultralytics](https://pypi.org/project/ultralytics/)” suffered a supply-chain attack through a compromise of the projects’ GitHub Actions workflows and subsequently its PyPI API token. No security flaw in PyPI was used to execute this attack. Versions 8.3.41, 8.3.42, 8.3.45, and 8.3.46 were affected and have been removed from PyPI.

<!-- more -->

The attack highlights the importance of securing software forges and the build and publish workflows for open source projects. A [complete set of details is available](https://blog.yossarian.net/2024/12/06/zizmor-ultralytics-injection) thanks to the analysis of William Woodruff from Trail of Bits.

## Visibility from Attestations and Trusted Publishers

Despite the success of the attack, many things went right from PyPI’s perspective, especially the ability to audit the attack while it was occurring and after the fact. Because the Ultralytics project was using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) and the [PyPA’s publishing GitHub Action](https://github.com/pypa/gh-action-pypi-publish): PyPI staff, volunteers, and security researchers were able to dig into how maliciously injected software was able to make its way into the package.

From looking at the [Sigstore transparency logs](https://search.sigstore.dev/?logIndex=153589716) and the PyPI provenance attestations, it was clear that the first set of injected packages were published through the existing GitHub Actions workflow, not by an API token. This considerably reduced the scope of the attack: either the malicious code was inside the source repository or was injected during the build phase. Later investigation showed that the [attack targeted the GitHub Actions cache](https://blog.yossarian.net/2024/12/06/zizmor-ultralytics-injection#conclusions) which was used during the build phase.

The second round of malicious releases came from the attacker using an unrevoked PyPI API token that was still available to the GitHub Actions workflow, potentially a hold-over from before the project adopted Trusted Publishing. This was detectable because there were no corresponding source repository activity or PyPI publish attestations for the second round of releases.

Once tools begin utilizing these publish attestations to record the “expected” provenance of software, this type of attack will be less effective as the lack of provenance information will be more apparent and verifiable at install time.

## How can PyPI improve the security of the ecosystem?

From this story, we can see a few places where PyPI can help developers towards a secure configuration without infringing on existing use-cases:

* **API tokens are allowed to go unused alongside Trusted Publishers.** It’s valid for a project to use a mix of API tokens and Trusted Publishers because Trusted Publishers aren’t universally supported by all platforms. However, API tokens that are being unused over a period of time despite releases continuing to be published via Trusted Publishing is a strong indicator that the API token is no longer needed and can be revoked.

* **GitHub Environments are optional, but recommended, when using a GitHub Trusted Publisher.** However, PyPI doesn’t fail or warn users that are using a GitHub Environment that the corresponding Trusted Publisher isn’t configured to require the GitHub Environment. This fact didn’t end up mattering for this specific attack, but during the investigation it was noticed as something easy for project maintainers to miss.

We’ve created tracking issues for both of the above changes.


## What is PyPI doing about malware?

Not every package and release on PyPI should be treated as trusted, it is up to you the user to review your usage of software from PyPI before choosing to install packages.

PyPI staff and volunteers do their best to remove malware, but because the service is open to anyone looking to publish software there is an unfortunately high amount of abuse. Thankfully most of this abuse does not have the same widespread impact as a targeted attack on an already widely-used project.

Mike Fiedler, the PyPI Safety and Security Engineer is working on new systems for reducing the time that malware is available to be installed on PyPI, through [APIs that security researchers can automatically send reports](./2023-09-18-inbound-malware-reporting.md) to and new [“quarantine” release status](./2024-08-16-safety-and-security-engineer-year-in-review.md#project-lifecycle-status-quarantine) to prevent harm while a human investigates the situation. Expect more in this space in 2025!

## What can you do as a publisher to the Python Package Index?

If you are publishing software to PyPI then you can harden your build and publish workflow to avoid supply-chain attacks. Following a handful of security best-practices is enough to avoid becoming a target as the difficulty increases drastically for each added mitigation.

* **Audit the existing workflow definitions for insecure configurations.** Avoid the use of commonly insecure patterns, such as GitHub Action’s “pull_request_target” or shared caches during the build and release process. Tools like [zizmor](https://woodruffw.github.io/zizmor/) can provide a list of potential places to start improving your workflow’s security.
* **Lock or pin dependencies to explicit versions with checksums** (such as SHA256 or git commits), especially for build and release processes. Minimize the total number of dependencies where possible. This protects against an external dependency compromise affecting your own project.
* **Use Trusted Publishers if available for your platform**, such as GitHub Actions, GitLab CI/CD, Google Cloud Build, and ActiveState. Trusted Publishers means credentials are short-lived so don’t need to be rotated in the case of a compromise and have limited time-bounded value if exfiltrated.
* **Don’t allow contributors to commit binary or opaque files.** Examples of this include compiled binaries and libraries, but also archives and certificates. This prevents attacks similar to xz-utils backdoor, where the malicious code was hidden in a binary archive file and therefore not easily reviewable by humans or tooling.

In addition to the specific recommendations above, we strongly recommend general account security best practices such as:

* **Use 2FA / MFA, preferably using a hardware key or authenticator app for all accounts associated with open source contributions.** This includes your email address and accounts for source forge(s) like GitHub or GitLab. Avoid SMS and text-message-based 2FA schemes if possible, as they are susceptible to SIM-swapping. PyPI already requires the use of 2FA to publish packages.
* **Don’t reuse passwords, use a password manager.** Re-using passwords for services means that a compromise to one service will compromise your account(s) elsewhere.

Prevention is important, but just as important is preparedness. Here’s what to do if your own project is compromised:

* **Delete known-bad releases from PyPI** and notify [security@pypi.org](mailto:security@pypi.org) for malware.
* **Rotate ALL long-lived secrets.** Chances are that if you are using long-lived secrets like API tokens for authentication that the attacker has exfiltrated these secrets and can use them later if not rotated.
* **Keep investigators in the loop, if possible.** Publish what actions you have taken or what you have learned to public places like an issue tracker so others can follow along. You aren’t alone, there are many contributors (like me) that are monitoring and trying to help protect Python users from supply-chain attacks.

## Thanks to sponsors for a secure Python ecosystem

Massive thank-you to sponsors who make security work for Python and PyPI possible such as [Alpha-Omega](https://alpha-omega.dev/) sponsoring Seth Larson as the Security Developer-in-Residence, [Amazon Web Services](https://aws.amazon.com/opensource/) sponsoring Mike Fiedler as the PyPI Safety and Security Engineer, and the [Sovereign Tech Fund](https://www.sovereigntechfund.de/tech/python-package-index) and the Google Open Source Security Team for sponsoring [Trail of Bits](https://www.trailofbits.com/) to work on PyPI Attestations.
