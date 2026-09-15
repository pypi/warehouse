---
title: Troubleshooting
---

# Troubleshooting Common Errors

## Why am I getting "No matching distribution found" or "Could not fetch URL" errors during pip install?

Transport Layer Security, or TLS, is part of how we make sure connections between your computer and PyPI are private and secure. It's a cryptographic protocol that's had several versions over time. PyPI [turned off support for TLS versions 1.0 and 1.1](https://mail.python.org/pipermail/python-announce-list/2018-April/011885.html) in April 2018. [Learn why on the PSF blog](https://pyfound.blogspot.com/2017/01/time-to-upgrade-your-python-tls-v12.html).

If you are having trouble with pip install and get a "No matching distribution found" or "Could not fetch URL" error, try adding `-v` to the command to get more information:

```console
pip install --upgrade -v pip
```

If you see an error like "There was a problem confirming the ssl certificate" or "tlsv1 alert protocol version" or `TLSV1_ALERT_PROTOCOL_VERSION`, you need to be connecting to PyPI with a newer TLS support library.

The specific steps you need to take will depend on your operating system version, where your installation of Python originated (python.org, your OS vendor, or an intermediate distributor), and the installed versions of Python, setuptools, and pip.

For help, go to [the #pypa IRC channel on Libera](https://web.libera.chat/#pypa), file an issue at [pypa/packaging-problems/issues](https://github.com/pypa/packaging-problems/issues), or [discuss on the Discourse](https://discuss.python.org/c/packaging/14), including your OS and installation details and the output of `pip install --upgrade -vvv pip`.

!!! note

    All users submitting feedback, reporting issues or contributing to Warehouse are expected to follow the [PSF Code of Conduct](https://github.com/pypa/.github/blob/main/CODE_OF_CONDUCT.md).
