---
title: "PyPI has completed its second audit"
description: We are proud to announce PyPI's second external security audit.
authors:
  - miketheman
date: 2026-04-16T14:00:00
tags:
  - security
  - transparency
links:
  - posts/2023-11-14-1-pypi-completes-first-security-audit.md
  - posts/2023-11-14-2-security-audit-remediation-warehouse.md
meta:
  - name: fediverse:creator
    content: "@miketheman@hachyderm.io"
---
In 2023 [PyPI completed its first security audit](./2023-11-14-1-pypi-completes-first-security-audit.md),
and I am proud to announce that we have now completed our second external security audit.

This work was funded by the [Sovereign Tech Agency](https://www.sovereign.tech/),
a supporter of Open Source security-related improvements,
partnering with [Trail of Bits](https://www.trailofbits.com/) to perform the audit.
Thanks to ongoing support from [Alpha-Omega](https://alpha-omega.dev/),
my role at the PSF enabled me to focus on rapid remediation of the findings.

This time around, there's no three-part series, as the scope was narrower,
focused only on PyPI's codebase and behaviors.
Read on for a summary of issues identified, their resolutions,
and more details about the audit process.

<!-- more -->

The full audit report can be found on the [Trail of Bits publication page](https://github.com/trailofbits/publications/blob/master/reviews/2026-04-pypi-warehouse-securityreview.pdf).
I highly recommend reading that for the fullest context first.

## Findings

Here's a table of the findings, status,
and links to the relevant pull requests where applicable:

| ID            | Title                                                                                         | Severity      | Difficulty | Status                                                     |
| :------------ | :-------------------------------------------------------------------------------------------- | :------------ | :--------- | :--------------------------------------------------------- |
| [TOB-PYPI26-1](#tob-pypi26-1-oidc-jti-anti-replay-lock-expires-before-jwt-leeway-window-closes)  | OIDC JTI anti-replay lock expires before JWT leeway window closes                             | Medium        | High       | [Remediated](https://github.com/pypi/warehouse/pull/19627) |
| TOB-PYPI26-2  | OIDC token minting is vulnerable to a TOCTOU race in JTI anti-replay                          | Low           | High       | [Remediated](https://github.com/pypi/warehouse/pull/19625) |
| TOB-PYPI26-3  | Verification badge bypass on the home page and download URLs                                  | Low           | Low        | [Remediated](https://github.com/pypi/warehouse/pull/19628) |
| TOB-PYPI26-4  | Project-level token deletion audit events silently dropped due to data structure mismatch     | Low           | Low        | [Remediated](https://github.com/pypi/warehouse/pull/19652) |
| TOB-PYPI26-5  | Password reset leaks privileged account status                                                | Low           | High       | [Remediated](https://github.com/pypi/warehouse/pull/19653) |
| [TOB-PYPI26-6](#tob-pypi26-6-ip-ban-bypass-via-macaroon-api-token-authentication)  | IP ban bypass via macaroon API token authentication                                           | Informational | High       | Accepted                                                   |
| TOB-PYPI26-7  | Moderators can modify organization applications due to a missing write permission check       | Low           | High       | [Remediated](https://github.com/pypi/warehouse/pull/19619) |
| [TOB-PYPI26-8](#tob-pypi26-8-organization-members-can-invite-new-owners-due-to-a-missing-manage-permission-check)  | Organization members can invite new owners due to a missing manage permission check           | High          | Medium     | [Remediated](https://github.com/pypi/warehouse/pull/19610) |
| TOB-PYPI26-9  | TOTP replay prevention bypass via space normalization mismatch between validation and storage | Informational | High       | [Remediated](https://github.com/pypi/warehouse/pull/19668) |
| [TOB-PYPI26-10](#tob-pypi26-10-wheel-metadata-is-served-to-installers-without-validation-against-upload-metadata) | Wheel METADATA is served to installers without validation against upload metadata             | Low           | Low        | Accepted                                                   |
| TOB-PYPI26-11 | IDOR in API Token Deletion Allows Any Authenticated User to Delete Other Users' Macaroons     | Low           | High       | [Remediated](https://github.com/pypi/warehouse/pull/19669) |
| TOB-PYPI26-12 | GitHub OIDC publisher lookup lacks issuer URL isolation for custom GHES issuers               | Informational | High       | [Remediated][1] [1], [2]                                        |
| [TOB-PYPI26-13](#tob-pypi26-13-organization-scoped-project-associations-persist-after-project-transfer-or-removal) | Organization-scoped project associations persist after project transfer or removal            | High          | High       | [Remediated](https://github.com/pypi/warehouse/pull/19749) |
| TOB-PYPI26-14 | Admin flag changes lack audit logging                                                         | Informational | High       | [Remediated](https://github.com/pypi/warehouse/pull/19751) |

[1]: https://github.com/pypi/warehouse/pull/19661
[2]: https://github.com/pypi/warehouse/pull/19718

Of the 14 findings, I used a combination of Severity and Difficulty
to determine which ones to work on first, and which ones to accept for now.

There were 2 High, 1 Medium, 7 Low, and 4 Informational severity findings.

All but 2 findings have been remediated, and the remaining 2 are accepted for now.
More details on the accepted findings below, but in general these were accepted
because they require significant effort to remediate, and the risk they pose is relatively low.

To reiterate, the [published report PDF](https://github.com/trailofbits/publications/blob/master/reviews/2026-04-pypi-warehouse-securityreview.pdf) goes into deeper detail about each finding,
so I recommend reading that for the fullest context first.

## Details

For some of the Remediated entries and all the Accepted ones, I'll go into more detail below.

### TOB-PYPI26-1: OIDC JTI anti-replay lock expires before JWT leeway window closes

PyPI's [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) flow
uses OIDC JWTs issued by CI providers to mint short-lived upload tokens.
Each JWT contains a `jti` (JWT Token Identifier) claim that should be single-use.
To enforce this, we store each `jti` in cache (Redis) with an expiration of `exp + 5` seconds,
and check whether it already exists before accepting a new token.

The problem: `PyJWT` is configured with `leeway=30`,
meaning it accepts tokens up to 30 seconds past their `exp` claim.
This created a 25-second window (from `exp + 5` to `exp + 30`)
where the cache key had already been evicted, but the JWT still passed signature verification.
During that window, a replayed token would pass both the signature check and the `jti` uniqueness check.

The fix was straightforward --
align the cache TTL to outlive the full leeway window
by [setting the expiration to `exp + leeway + margin`](https://github.com/pypi/warehouse/pull/19627/changes#diff-b6993869ec628f626827f05a87938a08f1ced03e52b68a49000100910d9d46f2R288).
I also took the opportunity to centralize these time-window constants
so they're derived from a shared configuration,
preventing future drift when one value is updated without the other.

### TOB-PYPI26-6: IP ban bypass via macaroon API token authentication

**Accepted for now.**

PyPI administrators can ban IP addresses through the admin dashboard.
The session authentication policy enforces this by checking the IP against the ban list
before returning an identity.
However, the macaroon (API token) authentication policy doesn't perform this same check.
This means a user with a valid API token could continue uploading packages
from a banned IP address.

I've accepted this finding for now. IP bans are a relatively blunt tool that we use sparingly,
[introduced late last year](https://github.com/pypi/warehouse/pull/19213)
to mitigate a specific wave of abuse.
The practical risk here is low - if we've identified a malicious actor,
we have other mechanisms to disable their account entirely.
That said, it's a gap worth closing, and we'll likely address it as part of broader work
on making security controls consistent across all authentication methods.

### TOB-PYPI26-8: Organization members can invite new owners due to a missing manage permission check

This was the highest-severity finding in the audit, and one I prioritized immediately.

The `manage_organization_roles` view handled both `GET` (viewing the people page)
and `POST` (sending invitations) under a single `@view_config` decorator
that only required `OrganizationsRead` permission.
This meant any organization member could send invitations with _any_ role -
including Owner - to any PyPI user.

The irony is that we already had the correct pattern elsewhere in the codebase.
Views like `resend_organization_invitation` and `change_organization_role`
correctly use separate `@view_config` decorators for `GET` and `POST`
with distinct permission requirements.
This one was simply missed.

The [fix was to split the view configuration](https://github.com/pypi/warehouse/pull/19610):
`GET` requires `OrganizationsRead`, `POST` requires `OrganizationsManage`.
As part of the audit, Trail of Bits also developed a custom CodeQL query
to detect this class of issue - views that handle state-changing `POST` requests
under a read-only permission check.
I'll integrate that into our CI to catch this pattern going forward.

### TOB-PYPI26-10: Wheel METADATA is served to installers without validation against upload metadata

**Accepted for now.**

This is a nuanced one. When a wheel is uploaded to PyPI,
we store two independent sources of metadata:
the form-declared metadata from the upload request (which populates the database and the JSON API),
and the embedded `.dist-info/METADATA` file extracted from the wheel itself
(which is served via [PEP 658](https://peps.python.org/pep-0658/) to `pip` for dependency resolution).

These two sources are never compared.
In theory, an attacker could embed hidden dependencies in the wheel's `METADATA`
that `pip` would install, but that security tools querying the JSON API would never see.

We've accepted this for now because the fix is non-trivial.
Properly validating embedded metadata against upload metadata
touches a core part of how we handle uploads,
and requires careful consideration of edge cases across the ecosystem.
This is something we want to get right rather than rush,
and [involves a fair amount of database changes, including data backfills](https://github.com/pypi/warehouse/issues/8090).

### TOB-PYPI26-13: Organization-scoped project associations persist after project transfer or removal

This was the other High-severity finding, and a subtle one.

When a project is transferred between organizations,
the `OrganizationProject` junction record is correctly deleted and recreated.
However, the `TeamProjectRole` records - which grant a team's members
access to specific projects - were _not_ cleaned up during the transfer.

This meant that if LexCorp Organization had a "release-engineers" team
with Owner-level access to a project,
and that project was transferred to Organization OsCorp,
the LexCorp team's members would silently retain full access to the project.
Worse, the receiving organization had no visibility into these stale associations -
team-granted permissions are resolved at ACL evaluation time
and don't appear as individual collaborator entries in the UI.

The fix in [pypi/warehouse#19749](https://github.com/pypi/warehouse/pull/19749)
ensures that `TeamProjectRole` records belonging to the departing organization
are cleaned up when a project is transferred.
Auditing database records proved that this has not happened in the past,
so I am confident there have been no such transfers with dangling permissions.
I also added defensive filters in the project's ACL computation
to verify that a team's organization matches the project's current organization
before granting permissions,
so stale records can't grant access regardless of how they're orphaned.

## Summary

Working with [Trail of Bits](https://www.trailofbits.com/) was again a pleasure.
The team were thorough, communicative, and clearly understood
the nuances of a system like PyPI - where the threat model spans everything
from CI/CD token replay to metadata integrity for millions of downstream users.

Beyond the 14 findings, the audit also produced proposal reviews
for features I'm considering (per-org Trusted Publishers, TOTP hardening, and more),
as well as custom CodeQL queries to integrate into our CI/CD pipeline.

This audit was funded in partnership with
the [Sovereign Tech Agency](https://www.sovereign.tech/),
which continues to support security improvements across the Open Source ecosystem.

My work at the Python Software Foundation is supported by [Alpha-Omega](https://alpha-omega.dev/).
