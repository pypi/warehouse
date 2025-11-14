---
title: New Login Verification for TOTP-based Logins
description: PyPI has added email verification for TOTP-based logins
date: 2025-11-14
authors:
  - di
tags:
  - security
  - 2fa
---

We've implemented a new security feature designed to protect PyPI users from phishing attacks: **email verification for TOTP-based logins from new devices.**

<!-- more -->

### What's Changing?

Previously, when logging in with a Time-based One-Time Password (TOTP) authenticator, a successful TOTP code was sufficient. Now, if you log in from a device or browser that PyPI doesn't recognize, we will send a verification email to the email address associated with your PyPI account with the subject "Unrecognized login to your PyPI account". You will need to click a link in this email to confirm the login attempt before you can proceed, after which the current device will be trusted for future logins.

**Users who have enabled WebAuthn (security keys) or passkeys for 2FA will not see any changes**, as these methods are inherently phishing-resistant. They cryptographically bind the authentication to the specific website (origin), meaning an attacker cannot trick you into authenticating on a fake site, unlike TOTP codes which can be phished.

### Why This Change?

This extra step significantly enhances PyPI user account security by mitigating the risk of phishing. As we've discussed in previous posts, such as ["Phishing attacks with new domains likely to continue"](https://blog.pypi.org/posts/2025-09-23-plenty-of-phish-in-the-sea/), recent phishing campaigns have targeted PyPI users. This new feature is a direct response to these ongoing threats. Even if an attacker manages to steal your username, password, and a TOTP code, they won't be able to access your account from a new device without also gaining access to your email. This makes it much harder for malicious actors to compromise your account.

### What You Need To Do

Most users will only encounter this verification when using TOTP-based 2FA when logging in from a new device. If you receive a verification email and you *did not* attempt to log in to PyPI, please do not click the link. Instead, change your password immediately and review your account for any suspicious activity.

While this new feature improves the security of TOTP, we continue to recommend migrating to stronger second-factor authentication methods such as **passkeys** or **WebAuthn (security keys)**. These methods offer superior protection against phishing and other sophisticated attacks. If you haven't already, please consider upgrading your 2FA method for the best possible account security on PyPI.

We believe this change will make PyPI an even safer place for the Python community. Thank you for your continued trust and support!
