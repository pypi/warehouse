---
title: Introduction
---

# Introduction

When you add a package to your Python project, you are choosing to execute code written by someone else on your machine. This is the foundation of modern software development, but it also carries inherent risks. A malicious or compromised package could steal data, damage your system, or create a backdoor into your application.

Deciding which packages are safe to use involves navigating a complex security landscape. While this guide won't cover every possible risk, it provides a practical mental model for evaluating packages and explains the specific security features supported by PyPI.

## Topics covered by this guide

* [Assessing source code security](source-code-security.md)<br />
How can I assess a package's source code? What signals can I use to tell if a project is "healthy"?
* [Checking provenance (where a package came from)](provenance.md)<br />
How can I know where a package came from? How can I verify that a package was built or published by a legitimate workflow, by an identity known to PyPI, and not by an attacker?
* [Verifying package integrity](package-integrity.md)<br />
How can I be sure the package I'm installing is the same as the one hosted on PyPI? How can I know it hasn't been tampered with in-transit?
* [Protecting yourself from common security attacks](common-attacks.md)<br />
What are the different types of security attacks and how can I protect myself from them? What does PyPI do to protect me?
* [Reporting security issues](reporting-issues.md)<br />
How should I report a security issue to PyPI?
