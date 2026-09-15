---
title: Security and Internals
---

# Security and Internals

## Reporting security vulnerabilities

**Do not report security issues in public forums or issue trackers.**

To read the most up-to-date version of PyPI’s security policy, including directions for reporting security issues, please visit [https://pypi.org/security](https://pypi.org/security/).

## PyPI as a target

Unfortunately, PyPI’s open and accessible nature, combined with its widespread use, makes it a high-profile target for hackers, spammers, and other malicious actors. They attempt to compromise PyPI and our users in several ways:

* **Software supply chain attacks:** By injecting malicious code into popular packages, attackers can compromise the software supply chain. This allows them to distribute malware to a vast number of developers and end-users who unwittingly install the compromised packages. These attacks can lead to data theft, system compromise, and the installation of malware like remote access trojans (RATs) and information stealers.  
* **Phishing campaigns:** Attackers may impersonate PyPI or its maintainers in emails or on other platforms to trick users into revealing their login credentials. For example, a recent [phishing campaign](https://blog.pypi.org/posts/2025-07-31-incident-report-phishing-attack/) lured PyPI users to a fake site at pipj.org, using a 'j' to impersonate the 'i' in pypi.org, in order to steal their credentials.  
* **Account takeover via expired domains:** Attackers may attempt to take over accounts by exploiting expired email domains. By registering a domain that was previously associated with a user's PyPI account, an attacker can reactivate the email address to initiate a password reset. Attackers identify potential targets by scanning the email metadata of published packages. See our [blog post on Domain Resurrection Attacks](https://blog.pypi.org/posts/2025-08-18-preventing-domain-resurrections/) for more information.  
* **Typosquatting:** Attackers upload packages with names that are common misspellings of popular libraries. They rely on developers making a typo to accidentally install the malicious version. In March 2024, [a large-scale typosquatting campaign](https://thehackernews.com/2024/03/pypi-halts-sign-ups-amid-surge-of.html) led to PyPI temporarily halting new user and project registrations to mitigate the threat.  
* **Spam:** Spammers return to PyPI with some regularity hoping to place their search engine optimized (SEO) phishing, scam, and click-farming content on the site. Since PyPI allows search engines to index a project’s long description and other metadata, and has a strong search reputation, it is a prime target.

The PyPI team uses the [PyPI blog](https://blog.pypi.org/) to publicly report on security compromises and remediations.

## PyPI security features

PyPI provides a range of security features to defend our users and the Python ecosystem from bad actors:

### Account security

* **Mandatory [two-factor authentication (2FA)](../your-account/two-factor-authentication.md):** To enhance account security, PyPI [mandates 2FA for all users](https://blog.pypi.org/posts/2024-01-01-2fa-enforced/). This requires all users to authenticate with a second form of verification (in addition to an account password) such as a code from an authenticator app or a physical security key.  
* [**Verified email address**](../your-account/managing-your-account.md#email-address-verification)**:** To perform certain actions, such as registering a new project, users must have a verified email address (proving that they own the email address). PyPI also:  
    * Maintains a blocklist of email domains that are frequently used for spam or other abuse, helping to mitigate automated attacks. See our [blog post on prohibiting outlook domains](https://blog.pypi.org/posts/2024-06-16-prohibiting-msn-emails/) for more information.   
    * Checks the reputation of an email address at registration time, and rejects addresses identified as disposable or temporary — even on domains that aren't otherwise blocklisted. See [account registration limits](../your-account/managing-your-account.md#account-registration-limits) for more information.  
    * Checks that email domains are valid on account registration, or when a user adds or changes the email addresses associated with their account.
    * Periodically scans for accounts with expired email domains or MX records, disabling those vulnerable to attack. See our [blog post on preventing domain resurrection attacks](https://blog.pypi.org/posts/2025-08-18-preventing-domain-resurrections/) for more information.
* **Phishing awareness:** PyPI implements email authentication standards (SPF, DKIM, and DMARC) to help prevent phishing by allowing mail servers to verify the authenticity of emails sent from PyPI.org. However, because the enforcement of these standards is the responsibility of the receiving mail server, fraudulent emails may still reach a user's inbox. Users should remain cautious of suspicious links and always verify they are on the official pypi.org domain before entering credentials. See [this incident report](http://link) for more information.

### Publishing security

* [**Trusted Publishing**](https://docs.pypi.org/trusted-publishers/)**:** This is the most secure and recommended method for publishing packages. It uses the OpenID Connect (OIDC) standard to allow a CI/CD provider (like GitHub Actions) to securely obtain short-lived API tokens and publish a package to PyPI. This approach:  
    * Removes the need for project maintainers to manually manage or store secrets, eliminating the risk of a long-lived API token being leaked  
    * Is more secure because build workflows can be protected by repository-level controls like branch protection and required reviews  
    * Provides a visible audit trail if there is any attempt to maliciously alter the build workflow (as this typically requires a public commit)  
    * Generates an [attestation](../attestations/index.md) so package consumers can verify the origin of a package  
* [**API tokens**](../publishing/publishing-to-pypi.md#using-an-api-token)**:** For manual uploads or for services that do not yet support Trusted Publishing, API tokens serve as an alternative to using an account password for authentication. PyPI API tokens can be scoped to specific projects, limiting the potential damage if a token is ever compromised.

### Threat response and automated protections

* [**Malware reporting**](https://blog.pypi.org/posts/2024-03-06-malware-reporting-evolved/)**:** PyPI relies on its users and the wider security community to help identify and report malicious packages. Users can report malware:  
    * **Via PyPI.org:** Suspicious packages should be reported using the "Report project as malware" link on a project's security tab  
    * **Via API (Beta):** PyPI provides a malware reporting API. This API is currently in beta, and users can apply to participate by completing [this Google Form](https://forms.gle/67dcguKijSsfJfxR7).  
* [**Project quarantine**](https://blog.pypi.org/posts/2024-12-30-quarantine/)**:** Projects that are flagged as malicious are placed in "quarantine." A quarantined project cannot be downloaded, and its owners cannot modify it. This immediately neutralizes the threat while the report is reviewed.   
* **Disabling new registrations or uploads:** During a large-scale spam or malware attack, PyPI administrators can temporarily disable new user or new project registrations (see [account registration limits](../your-account/managing-your-account.md#account-registration-limits)), or, in severe cases, disable new package uploads entirely or enter a full read-only mode (see [troubleshooting](../project-management/troubleshooting.md#why-am-i-getting-a-new-uploads-are-temporarily-disabled-or-read-only-mode-error)). The PyPI [status page](https://status.python.org/) provides updates during either kind of event.  
* **Typosquatting protection:** To combat [typosquatting](https://en.wikipedia.org/wiki/Typosquatting), PyPI prevents the registration of new projects with names that are confusingly similar to existing projects or that match the names of standard library modules. See [Choosing a project name](http://link) for more information.  
* **Preventing [ZIP confusion attacks](https://www.crowdstrike.com/en-us/blog/how-to-prevent-zip-file-exploitation/):** Python package "wheels" (or "binary distributions") are actually a ZIP archive in disguise. PyPI rejects ZIPs constructed to exploit ZIP confusion attacks. See [this blog post](https://blog.pypi.org/posts/2025-08-07-wheel-archive-confusion-attacks/) for more information.

## Internals

### What powers PyPI?

PyPI is powered by [Warehouse](https://warehouse.pypa.io/) and by a variety of tools and services provided by our [generous sponsors](https://pypi.org/sponsors/). For more information, see the:

* [Warehouse documentation](https://warehouse.pypa.io/)  
* [Warehouse codebase and issue tracker](https://github.com/pypi/warehouse)

### How can I get a list of PyPI's IP addresses?

All traffic is routed through our global CDN, which lists their public IP addresses here: [https://api.fastly.com/public-ip-list](https://api.fastly.com/public-ip-list).

More information about this list can be found here: [https://docs.fastly.com/en/guides/accessing-fastlys-ip-ranges](https://docs.fastly.com/en/guides/accessing-fastlys-ip-ranges).
