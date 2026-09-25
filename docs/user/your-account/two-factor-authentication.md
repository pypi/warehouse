---
title: Two-Factor Authentication
---

# Two-Factor Authentication

To enhance the security of the Python ecosystem, PyPI has implemented [mandatory two-factor authentication (2FA) for all accounts](https://blog.pypi.org/posts/2024-01-01-2fa-enforced/) since 2024. This measure is a crucial step in safeguarding accounts from unauthorized access and protecting PyPI users from malicious attacks.

## What is two-factor authentication?

Two-factor authentication makes your account more secure by requiring two things in order to log in: *something you know* and *something you own*.

In PyPI's case, "something you know" is your username and password. "Something you own" can be an application to generate a temporary code, or a security device (most commonly a USB key).

## Recovery codes

Recovery codes are a set of single-use codes that can be used to log in to your account in an emergency. They should be stored in a secure location, such as a password manager or a physical safe.

**Before you can enable 2FA, you must generate and verify your recovery codes.** This ensures you have a working backup before you lock yourself into requiring 2FA to log in.

**How to get them:**

1. From your account settings, choose "Generate recovery codes." This is required before you can add a TOTP application or security device.
2. Securely store the displayed codes.
3. To verify that you've safely stored them, you'll be asked to submit ("burn") one of the codes. Only after this is verified can you set up your first 2FA method.
4. You can also generate new codes at any time from your account settings. Generating new codes will invalidate any previous sets.

**How to use them:**

1. On the login page, select the option to use a recovery code
2. Enter one of your unused codes to gain access to your account
3. As each code can be used only once, you might want to mark the code as used (or generate a new set, as described above)

## Setting up two-factor authentication

You can enable 2FA on your PyPI account using one of the following methods. **It is highly recommended to set up at least two methods to avoid losing access to your account.**

Before you can add either method, PyPI requires you to generate and verify a set of [recovery codes](#recovery-codes).

!!! warning "Prefer a security device when possible"
    Where you have the choice, a WebAuthn security device is preferred over a TOTP application. Security devices are resistant to phishing, since they verify the identity of the site you're logging into, whereas a TOTP code can be copied and reused by an attacker if you're tricked into entering it on a fake site.

### Security device (WebAuthn)

A security device is a physical key (often a USB key or mobile phone) that communicates with your browser to authenticate you. PyPI supports any [FIDO compliant device](https://fidoalliance.org/certification/fido-certified-products/), including USB keys.

**How it works:**

PyPI utilizes the [WebAuthn standard](https://www.w3.org/TR/webauthn/), which allows browsers to use a registered security device to verify your identity.

**Requirements:**

* Use a browser:  
    * [That supports WebAuthn and PublicKeyCredential](https://developer.mozilla.org/en-US/docs/Web/API/PublicKeyCredential#Browser_compatibility)  
    * That is running JavaScript  
* If using a USB key, ensure that it adheres to the [FIDO U2F specification](https://fidoalliance.org/specifications/download/):  
    * Popular keys include [Yubikey](https://www.yubico.com/), [Google Titan](https://cloud.google.com/titan-security-key/) and [Thetis](https://thetis.io/)  
    * Note that some older Yubico USB keys **do not follow the FIDO specification**, and will therefore not work with PyPI

**Setup instructions:**

1. Log in to your PyPI account, go to your account settings, and choose "Add 2FA with security device (e.g. USB key)"  
2. Give your key a name. This is necessary because it's possible to add more than one security device to your account.  
3. Click on the "Set up security device" button  
4. Follow instructions from your browser to complete the configuration (e.g. insert and touch your USB key)

### Authentication application (TOTP)

A Time-based One-Time Password (TOTP) application generates a new, temporary verification code on a regular basis.

**How it works:**

TOTP applications work by sharing a secret key with PyPI. This key is used to generate the same six-digit code on both your device and the PyPI server at the same time.

**Compatible applications:**

Because TOTP is an open standard, a wide variety of applications are compatible with your PyPI account. Popular choices include:

* Google Authenticator for [Android](https://play.google.com/store/apps/details?id=com.google.android.apps.authenticator2) or [iOS](https://itunes.apple.com/app/google-authenticator/id388497605) (proprietary)  
* [Microsoft Authenticator](https://www.microsoft.com/en-us/account/authenticator) (proprietary)  
* Duo Mobile for [Android](https://play.google.com/store/apps/details?id=com.duosecurity.duomobile) or [iOS](https://itunes.apple.com/app/duo-mobile/id422663827) (proprietary)  
* [Authy](https://authy.com/) (proprietary)  
* [FreeOTP+](https://play.google.com/store/apps/details?id=org.liberty.android.freeotpplus) (open source)  
* [FreeOTP](https://freeotp.github.io/) (open source)

Some password managers (e.g. [1Password](https://1password.com/)) can also generate authentication codes. 

For security reasons, PyPI only allows you to link one authentication application to your account at a time.

**Setup instructions:**

1. Log in to your PyPI account and navigate to your account settings.  
2. Select the option to "Add 2FA with authentication application"  
3. PyPI will display a QR code and a textual representation of your secret key  
4. Open your chosen authenticator app and either scan the QR code or manually enter the key  
5. Your app will start generating six-digit codes. Enter the current code into the verification field on PyPI to complete the setup.

!!! tip "Having trouble setting up your authentication application?"
    If you're having issues while setting up a TOTP device, it may be because your device's time is out of sync. TOTP codes are time-based, so PyPI and your device need to agree on the current time. Check that the time on your device is set automatically, and try setting up the device again.

## Account recovery

If you have lost access to all of your 2FA devices and do not have your recovery codes, you may still be able to recover your account by following the [account recovery](account-recovery.md) process. 

However, to avoid this scenario, **it is strongly recommended that you provision and securely store your recovery codes.**
