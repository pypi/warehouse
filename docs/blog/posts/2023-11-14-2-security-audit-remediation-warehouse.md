---
title: "Security Audit Remediation: Warehouse"
description: A deeper dive into the remediation of the security audit findings for the Warehouse project.
authors:
  - miketheman
date: 2023-11-14T00:00:01
tags:
  - security
  - transparency
links:
  - posts/2023-11-14-1-pypi-completes-first-security-audit.md
  - posts/2023-11-14-3-security-audit-remediation-cabotage.md
---

_This is part two in a three-part series. See [part one here](2023-11-14-1-pypi-completes-first-security-audit.md), and [part three here](2023-11-14-3-security-audit-remediation-cabotage.md)_.

This post is a deeper dive into the remediation of the security audit findings
for the Warehouse - the main codebase for [PyPI.org](https://pypi.org).

The audit report can be found [here](2023-11-14-1-pypi-completes-first-security-audit.md).
I highly recommend reading that for the fullest context first.

<!-- more -->

## Findings

The audit report identified 18 findings for Warehouse,
along with some code quality suggestions.
This post will focus on the findings and their remediation.
Some of the code quality suggestions were implemented, others deferred.

Here's a table of the items that are relevant to warehouse, and their status:

| ID          | Title                                                            | Severity      | Difficulty   | Status                                                     |
|-------------|------------------------------------------------------------------|---------------|--------------|------------------------------------------------------------|
| TOB-PYPI-1  | Unsafe input handling in "Combine PRs" workflow                  | Informational | High         | [Remediated](https://github.com/pypi/warehouse/pull/14528) |
| TOB-PYPI-2  | Weak signatures used in AWS SNS verification                     | Medium        | Undetermined | [Remediated](https://github.com/pypi/warehouse/pull/14387) |
| TOB-PYPI-4  | Lack of rate limiting on endpoints that send email               | Low           | High         | Accepted                                                   |
| TOB-PYPI-5  | Account status information leak for frozen and disabled accounts | Medium        | Low          | [Remediated](https://github.com/pypi/warehouse/pull/14449) |
| TOB-PYPI-6  | Potential race conditions in search locking                      | Low           | High         | [Remediated](https://github.com/pypi/warehouse/pull/14640) |
| TOB-PYPI-7  | Use of multiple distinct URL parsers                             | Informational | Undetermined | [Remediated](https://github.com/pypi/warehouse/pull/14497) |
| TOB-PYPI-8  | Overly permissive CSP headers on XML views                       | Informational | High         | [Remediated](https://github.com/pypi/warehouse/pull/14452) |
| TOB-PYPI-9  | Missing Permissions-Policy                                       | Medium        | High         | [Remediated](https://github.com/pypi/infra/pull/160)       |
| TOB-PYPI-10 | Domain separation in file digests                                | Low           | Low          | [Remediated](https://github.com/pypi/warehouse/pull/14492) |
| TOB-PYPI-11 | Object storage susceptible to TOC/TOU due to temporary files     | Informational | High         | Accepted                                                   |
| TOB-PYPI-12 | HTTP header is silently trusted if token mismatches              | Informational | High         | [Remediated](https://github.com/pypi/warehouse/pull/14499) |
| TOB-PYPI-13 | Bleach library is deprecated                                     | Informational | Undetermined | [Remediated](https://github.com/pypi/warehouse/pull/14526) |
| TOB-PYPI-14 | Weak hashing in storage backends                                 | Medium        | High         | Accepted                                                   |
| TOB-PYPI-15 | Uncaught exception with crafted README                           | Informational | Medium       | Accepted                                                   |
| TOB-PYPI-16 | ReDoS via zxcvbn-python dependency                               | Informational | High         | Accepted                                                   |
| TOB-PYPI-23 | Insecure XML processing in XMLRPC server                         | Low           | Low          | [Remediated](https://github.com/pypi/warehouse/pull/14491) |
| TOB-PYPI-27 | Denial-of-service risk on tar.gz uploads                         | Informational | Medium       | Accepted                                                   |
| TOB-PYPI-29 | Unescaped values in LIKE SQL queries                             | Informational | Low          | Accepted                                                   |

_IDs are non-consecutive, as the audit report included findings for cabotage as well._

For some of the Remediated entries and all the Accepted ones, I'll go into more detail below.

## Details

Now that you've had a chance to read the original audit report,
and can see that we've remediated most of the findings,
I wanted to take some time to dig into some specifics of particular findings.

### TOB-PYPI-2: Weak signatures used in AWS SNS verification

PyPI uses AWS SES to send emails to users.
The SES configuration is set to use a
[Message Delivery Status](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#mailing-list-notification)
topic, which sends a notification to an AWS SNS topic,
which then sends a notification to our application.

This is useful for things like "Accepted/Delivered",
but more importantly "Bounced" and "Complaint" notifications,
which change the status of user accounts.
We don't want to send more emails to a known bad address,
and we don't want to send emails to users who have marked us as spam.

Since PyPI receives a webhook from AWS SNS,
it needs to verify the signature of the message.

Verifying inbound SNS messages has generally been left up to the user.
[The AWS SNS docs](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
are clear about that.

We had previously implemented signature verification for version 1,
which uses the SHA1 hash algorithm,
as that is what existed when we implemented it.

As time evolved, and AWS SNS added support for SHA256,
the path to upgrade was still left in the hands of the user.
SNS still defaults to SHA1 (`SignatureVersion: '1'`),
and there's no Python SDK function to call to validate the signature for you.

This is [also an outstanding request from boto3 users](https://github.com/boto/boto3/issues/2508).

In September 2022, AWS SNS added support for SHA256 signatures,
and shared the details in [this blog post](https://aws.amazon.com/blogs/security/sign-amazon-sns-messages-with-sha256-hashing-for-http-subscriptions/).
They also added support for verification in some of the client-side SDKs,
but sadly Python is not one of them yet.

While we were already validating SignatureVersion 1,
we took this opportunity to add support for SignatureVersion 2,
update our settings, and now only accept SHA256 signatures.

As an [AWS Hero](https://aws.amazon.com/developer/community/heroes/),
I reached out to Farrah Campbell who heads up Modern Compute Community at AWS,
and she quickly connected me with the AWS SNS service team for a chat.
We discussed some of the challenges, as well as some ideas for the path forward.

I'm hopeful that sometime in the future we will see two big things:

- message validation in `boto3` for both signature versions
  This would enable us to remove [`MessageVerifier` we added to warehouse](https://github.com/pypi/warehouse/blob/256d3e374ff8c2c3b29ac1b3040c88ddfb7e1d76/warehouse/utils/sns.py), and benefit from any future enhancements to the validation process.
- update AWS SNS to default to `SignatureVersion: 2` (SHA256).
  This could be a breaking change for users who have not updated their settings,
  but would be a good step forward for security.
  This make take some time, as the new signature version was only added a year ago.
  I'll leave that up to the SNS service team.

### TOB-PYPI-4: Lack of rate limiting on endpoints that send email

We accepted this finding, as we need to send emails to unverified users
as part of the account creation process, and we don't want to block that.

The finding details that PyPI doesn't apply blanket rate limiting, which is correct.
The endpoints that send emails to **unverified** addresses are protected via rate limiting.

PyPI has compensating controls in place to prevent abuse,
such as preventing too many password reset emails from being sent to a single user.

Since the risk here was to the cost and reputation of the email service,
we decided to accept this finding.
At some future point we may revisit the rate limiting strategy for sending email.

### TOB-PYPI-6: Potential race conditions in search locking

This is another case of "we implemented something that was good at the time,
and as time went on a better solution became available".

We had written a context manager to handle locking the search index
when performing updates, to prevent multiple processes from trying to update
the search index at the same time.
The implementation wasn't tied to the underlying Redis lock expiration,
so could lead to the Redis-lock expiring, but Python believing it was still locked.

Here we updated our implementation to use a context manager that `redis-py`
now provides, instead of crafting our own.

A solid reminder to check back on your libraries and services now and then,
to see if there's new features that can help you out.

### TOB-PYPI-11: Object storage susceptible to TOC/TOU due to temporary files

This is a complex timing attack, which requires a level of access to the system
that would allow for a more direct attack.
The finding itself details that if an attacker could execute this,
they are more likely to do other kinds of damage.

The complexity of navigating between our various storage backends/client APIs
does not appear to be worth the resulting defense in depth,
given the required access level to exploit.

We have a [draft PR](https://github.com/pypi/warehouse/pull/14568)
with a start of implementation should we decide to pursue this.

### TOB-PYPI-14: Weak hashing in storage backends

This is specifically about the Backblaze B2 storage backend,
one of PyPI's current object storage providers,
which does not currently support SHA-256 checksums.
They do support SHA-1 which is useful for detecting data corruption in transit,
but is insufficient for non-colliding checksums - we have to use MD5 for that.

During the audit, we reached out to the Backblaze team to discuss and determined it's on their roadmap, and when they implement it, we'll update our usage accordingly.

### TOB-PYPI-15: Uncaught exception with crafted README

This finding discovered a bug in `docutils`, which PyPI uses via the `readme_renderer` library to render project descriptions from reStructuredText and Markdown to HTML.

The bug is [tracked here](https://sourceforge.net/p/docutils/bugs/474/),
and has yet to see a response from the maintainers.

It only applies to client-side behavior when using reStructuredText for a README,
so we've accepted this finding.
Additionally, any user performing `twine check` prior to upload
will surface this issue.

Once the bug is fixed, we'll update!

### TOB-PYPI-16: ReDoS via `zxcvbn-python` dependency

Direct from the audit:

> This finding is purely informational.
> We believe that it has virtually no impact, like many ReDoS vulnerabilities,
> due to Warehouse’s deployment architecture.

Enough said.

### TOB-PYPI-23: Insecure XML processing in XMLRPC server

The audit began when the Warehouse deployment was on Debian 11 `bullseye`,
and as part of normal maintenance we upgraded to
[Debian 12 `bookworm`](https://github.com/pypi/warehouse/pull/14491)
while the audit was in progress.

Python XMLRPC uses [`expat`](https://libexpat.github.io/) for XML parsing.
The version of `expat` in Debian `bullseye` was `2.2.10`, which was vulnerable
to the specific attack detailed in the audit report.

With `bookworm`, the version of [`expat` is `2.5.0`](https://packages.debian.org/bookworm/libexpat1),
which is not vulnerable. (Generally considered [fixed as of 2.4.1.](https://github.com/python/cpython/pull/26945))

This was a tricky one to track down, as once the report came in
I was unable to reproduce the issue locally, as I had already upgraded.

Using some `git bisect` magic, I was able to track down the exact commit
that fixed the issue (the `bookworm` upgrade),
and then it was a matter of figuring out which library had changed.

After figuring it out, I worked with the auditors to update their
recommendations to reflect the upgrade.
Until now, the general recommendation was to adopt `defusedxml`,
which might have proven harder as we delegate the majority of our XML parsing
to `pyramid-rpc`, which uses `xmlrpc.client` from the standard library.

If you want to check your own installation, you can run the following:

```bash
python -c "import pyexpat; print(pyexpat.EXPAT_VERSION)"
```

On `bookworm`, we get `expat_2.5.0`, which is not affected by the vulnerability.

This was remediated by underlying OS update to `bookworm`.
Debian distributions pin to a specific version of libraries
for the duration of that distribution version.

### TOB-PYPI-27: Denial-of-service risk on tar.gz uploads

This is a tricky one, as it's a tradeoff between usability and security.

The audit report details a specific attack vector,
where a malicious user could upload a tarball with a highly-compressed file,
which would cause the server to spend a lot of time decompressing it.

Since we accept uploads from the general public,
we have to take precautions whenever possible to prevent abuse.
When it comes to ZIP files (which all `.whl` or "wheel" files are), we already have a mechanism to detect
decompression bombs, and reject them.

However, since `.tar.gz` files do not advertise file sizes as metadata,
in order to detect a decompression bomb we would have to decompress the entire file anyhow.

As the report notes, our deployment architecture compensates for this behavior,
where we have a dedicated worker pool for handling uploads.

We may apply additional restrictions at the system level in the future,
but for now we've accepted this finding.

### TOB-PYPI-29: Unescaped values in `LIKE SQL` queries

The risk here is that a query could "walk the table"
and not take advantage of any indexes, leading to higher resource usage.

The majority of the places where we use unescaped `LIKE` queries
is in PyPI admin-only interface, where want to allow admins to search for users, packages, etc.

For the one place where we allow public-facing `LIKE` queries,
there are already rate limits in place to prevent abuse.
The table in question is also smaller than 1M rows, so walking an un-indexed column
would not be a significant resource usage, and takes a handful of extra milliseconds.

The potential higher resource usage would be limited to malicious internal actors,
and if we can't trust each other, we've got bigger problems to deal with.

We've accepted this finding, and will continue to monitor all of relevant resources.

## Summary

Working with the folks at [Trail of Bits](https://www.trailofbits.com/) was a pleasure,
and I'm thankful for their thoroughness and professionalism.

While the audit was funded through the [Open Technology Fund](https://opentech.fund/),
my work on remediation would not have been as timely
if not funded by [Amazon Web Services](https://aws.amazon.com/)
to work as the [PyPI Safety and Security Engineer](./2023-05-09-announcing-pypi-safety-and-security-engr-role.md).
I am grateful for the continued support of both organizations
in making PyPI a safer place for all Python users.

_Mike Fiedler is the inaugural PyPI Safety & Security Engineer._
