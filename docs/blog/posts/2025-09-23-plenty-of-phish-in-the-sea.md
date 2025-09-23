---
title: Phishing attacks with new domains likely to continue
description: A new phishing campaign targeting PyPI users using similar tactics to previous campaigns.
authors:
  - sethmlarson
date: 2025-09-23
tags:
  - security
  - transparency
links:
  - posts/2025-07-28-pypi-phishing-attack.md
  - posts/2025-07-31-incident-report-phishing-attack.md

---

Unfortunately the string of phishing attacks using domain-confusion
and legitimate-looking emails continues. This is the [same attack PyPI saw a few months ago](2025-07-28-pypi-phishing-attack.md)
and targeting many other open source repositories
but with a different domain name. Judging from this, we believe this type of campaign will continue
with new domains in the future.

In short, there's a new phishing campaign
targeting PyPI users occurring right now. The email asks you to "verify their email address"
for "account maintenance and security procedures" with a note that your account may be suspended.
This email is fake, and the link goes to `pypi-mirror.org` which is a domain not owned by PyPI or the PSF.

If you have already clicked on the link and provided your credentials, we recommend changing your
password on PyPI immediately. Inspect your account's Security History for anything unexpected.
Report suspicious activity, such as potential phishing campaigns against PyPI, to [`security@pypi.org`](mailto:security@pypi.org).

## What is PyPI doing to protect users?

There's no quick-and-easy method for PyPI maintainers to completely
halt this sort of attack short of requiring phishing-resistant 2FA (such as hardware tokens).
Below are the following steps we're taking to keep users safe:

* Contacting the registrars and CDN of the malicious domains to have them taken down.
* Submitting phishing domains to lists of known-malicious URLs. This makes browsers show a warning
  before visiting the website, hopefully triggering alarm bells for users.
* Collaborating with other open source package managers to share strategies for quicker domain take-downs.
* [Requiring an email confirmation for TOTP-based logins](https://github.com/pypi/warehouse/pull/18689) when logging in from a new device.
  Phishing-resistant 2FA methods like hardware keys won't require this confirmation.

## What can you do as a maintainer?

If you are a maintainer of a package on PyPI, you can help protect your users by adopting the following practices:

* Don't trust or click on links in emails that you didn't trigger yourself.
* Use a password manager that auto-fills based on domain name and exclusively using this feature.
  If auto-fill isn't working when it usually does, that is a warning sign!
* Adopt a phishing-resistant 2FA method such as hardware keys.
* When in doubt, ask for help before taking action. There is no shame in being cautious, share fishy-looking emails with others.
* Share this warning within your own communities. PyPI is not the first or last open source service that will be targeted with phishing attacks.
