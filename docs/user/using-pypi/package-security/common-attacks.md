---
title: Common Security Attacks
---

# Protecting Yourself From Common Security Attacks

Knowledge is power. Understanding common attacks and how you can protect yourself is key to using packages securely.

## Typosquatting

This attack preys on you making a simple typing mistake. An attacker publishes a malicious project with a name that is a common misspelling of a popular, legitimate project (e.g. `python-datutil` instead of `python-dateutil`). When you accidentally install the misspelled version, you unknowingly execute the attacker's code.

To combat this, PyPI automatically rejects a new project's name if it is too similar to any other project on PyPI.

Your best defense is to always double check the spelling of a package you are installing and install dependencies from a `requirements.txt` file, which formalizes the exact name and version you intend to use.

Always check package names from LLM output, as an attacker could register a malicious package that an LLM may hallucinate (this is known as [slopsquatting](https://en.wikipedia.org/wiki/Slopsquatting)).

## Dependency confusion

This attack targets you when you use a mix of package sources — i.e. private packages from an internal or company source, alongside public packages from PyPI.org.

An attacker discovers the name of a private package you want to install (e.g. `mycompany-internal-billing`) and publishes a malicious public package on PyPI with the exact same name.

When your machine or a build system installs dependencies, it can prioritize installing the malicious public package instead of the intended private package.

For more information on dependency confusion, see [this article](https://portswigger.net/daily-swig/researcher-hacks-apple-microsoft-and-other-major-tech-companies-in-novel-supply-chain-attack). You can also read a report about the [PyTorch incident](https://pytorch.org/blog/compromised-nightly-dependency/), where this attack was used to target Python users.

## Man-in-the-Middle (MitM) attacks

This attack occurs when an attacker secretly intercepts your internet connection, often on an insecure network like public Wi-Fi. They can then replace the legitimate package you intended to download with a malicious one.

To combat this, PyPI provides a unique checksum for every file uploaded. This checksum acts as a digital fingerprint for the original file (see [Verifying package integrity](package-integrity.md)).

To protect yourself, use pip with [hash checking mode](https://pip.pypa.io/en/stable/topics/secure-installs/#hash-checking-mode) and include hashes from PyPI in your `requirements.txt` file.

## Account takeover (ATO)

In this attack, an attacker gains access to a maintainer's PyPI account and pushes a new, malicious version of a popular, legitimate package. From your perspective, the malicious version appears to come from the original author, making it difficult to detect.

Since you can't know if a maintainer's account has been compromised, your best defense is to look for signals of good security practice. Prefer packages that use [Trusted Publishing](../../trusted-publishers/index.md), which you can identify by the presence of an [attestation](provenance.md) on the release's security page.

This indicates the package was uploaded via an automated process without the use of API tokens that can be stolen.

## Supply chain attacks

This attack happens when malicious code is inserted into a package before it is uploaded, for example by compromising a maintainer's source code repository or their automated build system. The compromised package, which looks legitimate, is then published to PyPI for users to download.

To protect yourself from code injected during this process, you should verify the package's origin. Look for packages on PyPI that include an [attestation](provenance.md). You can then inspect the information in the attestation to check where the package came from, including (where available) the source repository, source commit, build/publishing platform and build/publishing workflow.
