---
title: Security Alerts
---

# Security Alerts and Suspicious Activity

All PyPI user events are stored under security history in account settings. If there are any events that seem suspicious, take the following steps:

* [Reset your password](https://pypi.org/account/request-password-reset/)  
* Contact the PyPI admins about the event at [admin@pypi.org](mailto:admin@pypi.org)

## Security alerts

PyPI will notify you if a password or API token you are using has been compromised (e.g. by appearing in a public data breach):

### Compromised passwords

If PyPI informs you that your password is compromised, it is a protective measure and **does not mean PyPI itself has suffered a breach.** This check helps reduce the risk of credential stuffing attacks, where attackers use passwords leaked from other websites to try and access PyPI accounts.

Each time you use a password on PyPI (for registration, login, or password changes), it is checked against a database of passwords that have appeared in public data breaches. This is done securely:

* PyPI generates a SHA-1 hash of your password  
* The first five characters of that hash are sent to the [Have I Been Pwned](https://haveibeenpwned.com/) API to see if there is a match  
* Your plaintext password is **never** stored by PyPI or sent to any external service

If you see an error that "This password appears in a breach or has been compromised and cannot be used," you will be blocked from using it on PyPI. You should also change this password on any other service where you might be using it.

If this error occurs during login, your password has been automatically reset, and you must complete the password reset process to regain access to your account.

### Compromised API tokens

If you receive a notification that your API token has been compromised, it means a token associated with your account was found on a public website. For your protection, **the exposed token was automatically revoked by PyPI.**

Before generating a new token, you should:

* Review the notification email and investigate how the token may have been exposed  
* Review your account's security history for any unauthorized actions   
* Contact the PyPI admins at [admin@pypi.org](mailto:admin@pypi.org) if any unauthorized actions have occurred  
* Reset your password
