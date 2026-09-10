# SPDX-License-Identifier: Apache-2.0

"""
Automated review checks for organization applications.

Every check is advisory: nothing here approves or declines an application. A check
returns None when it does not apply, and CheckStatus.Unknown when it applies but
cannot reach an answer.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import re

from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from tldextract import TLDExtract
from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

from warehouse.accounts.models import OAuthAccountAssociation
from warehouse.organizations.constants import (
    MIN_SUBSTRING_LENGTH,
    NAME_SIMILARITY_THRESHOLD,
    OPEN_APPLICATION_STATUSES,
)

if TYPE_CHECKING:
    from warehouse.accounts.models import User
    from warehouse.organizations.models import OrganizationApplication

_extractor = TLDExtract(suffix_list_urls=())

# Hosts that are public suffixes, so domain matching can't be used to affiliate
# to an org.
UNVERIFIABLE_URL_HOSTS = {
    "bitbucket.org",
    "codeberg.org",
    "gitee.com",
    "github.com",
    "github.io",
    "gitlab.com",
    "gitlab.io",
    "pypi.org",
    "readthedocs.io",
    "readthedocs.org",
    "sourceforge.net",
}

GITHUB_HOSTS = {"github.com", "github.io"}


class CheckStatus(enum.StrEnum):
    Ok = "ok"
    Fail = "fail"
    Warn = "warn"
    Unknown = "unknown"


@dataclasses.dataclass(frozen=True)
class Check:
    key: str
    label: str
    status: CheckStatus
    detail: str


_STATUS_ORDER = {
    CheckStatus.Fail: 0,
    CheckStatus.Warn: 1,
    CheckStatus.Unknown: 2,
    CheckStatus.Ok: 3,
}


def _host(value: str) -> str | None:
    r"""Resolve and punycode a host.

    `https://acme.example\@safe.example` therefore reads as `acme.example`.
    """
    try:
        host = parse_url(value).host
    except LocationParseError:
        return None
    return host.lower() if host else None


class _Link:
    """Every view of an application's URL the checks need, parsed once."""

    def __init__(self, raw: str) -> None:
        self.host = _host(raw)
        extracted = _extractor(self.host or "")
        self.registered_domain = extracted.top_domain_under_public_suffix or None
        self.domain_label = extracted.domain
        # `github.io` and `readthedocs.io` are themselves public suffixes, so a match
        # can land on either component depending on the host.
        parts = {extracted.top_domain_under_public_suffix, extracted.suffix}
        self.unverifiable = bool(parts & UNVERIFIABLE_URL_HOSTS)
        self.github = bool(parts & GITHUB_HOSTS)


# urllib3 reads these as authority terminators, so `acme.com\evil.org` would
# normalize to `acme.com`. An address holding one is not a domain to match on.
_URL_DELIMITERS = "\\/?#@:[]"


def _email_domain(email: str) -> str | None:
    _, _, domain = email.rpartition("@")
    if not domain or any(char in domain for char in _URL_DELIMITERS):
        return None
    return _extractor(_host(f"//{domain}") or "").top_domain_under_public_suffix or None


def _comparable(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _resembles(candidate: str, target: str) -> bool:
    if min(len(candidate), len(target)) >= MIN_SUBSTRING_LENGTH and (
        candidate in target or target in candidate
    ):
        return True
    return SequenceMatcher(None, candidate, target).ratio() >= NAME_SIMILARITY_THRESHOLD


def _domain_match_check(link: _Link, user: User) -> Check:
    check = functools.partial(
        Check, "domain_match", "Verified email matches organization domain"
    )

    if link.registered_domain is None:
        return check(
            CheckStatus.Unknown, "No domain could be read from the application URL."
        )

    if link.unverifiable:
        return check(
            CheckStatus.Unknown,
            f"{link.registered_domain} is a shared host, so an address there does "
            "not show affiliation. Verify another way.",
        )

    verified = sorted(email.email for email in user.emails if email.verified)
    if any(_email_domain(email) == link.registered_domain for email in verified):
        return check(
            CheckStatus.Ok, f"Verified @{link.registered_domain} address on file."
        )

    if not verified:
        return check(
            CheckStatus.Unknown,
            f"No verified address to compare against {link.registered_domain}.",
        )

    if any(
        _email_domain(email.email) == link.registered_domain
        for email in user.emails
        if not email.verified
    ):
        return check(
            CheckStatus.Fail,
            f"Has an @{link.registered_domain} address, but it is not verified.",
        )

    return check(
        CheckStatus.Fail,
        f"No verified @{link.registered_domain} address. "
        f"Verified addresses: {', '.join(verified)}.",
    )


def _url_shape_check(link: _Link) -> Check | None:
    # Two keys: the template routes each to a different saved reply.
    if not link.unverifiable:
        return None

    label = "Application URL is an organization homepage"
    if link.github:
        return Check(
            "url_shape_github",
            label,
            CheckStatus.Warn,
            f"URL is on {link.host}, not the organization's own domain. Ask for "
            "public GitHub membership and an account association.",
        )
    return Check(
        "url_shape_codehost",
        label,
        CheckStatus.Warn,
        f"URL is on {link.host}, a code or package host, not the organization's "
        "own domain.",
    )


def _name_domain_check(
    application: OrganizationApplication, link: _Link
) -> Check | None:
    """Catch the `acme` application pointing at `globex.com`."""
    check = functools.partial(
        Check, "name_domain_match", "Organization name matches the domain"
    )

    if link.unverifiable or link.registered_domain is None:
        return None

    target = _comparable(link.domain_label)
    candidates = {
        _comparable(application.name),
        _comparable(application.display_name or ""),
    } - {""}
    if any(_resembles(candidate, target) for candidate in candidates):
        return check(CheckStatus.Ok, f"Name lines up with {link.domain_label}.")
    return check(
        CheckStatus.Warn,
        f"Name looks unrelated to {link.domain_label}. Confirm they are the same "
        "organization.",
    )


def _email_verified_check(user: User) -> Check:
    check = functools.partial(Check, "email_verified", "Applicant has a verified email")

    if any(email.verified for email in user.emails):
        return check(CheckStatus.Ok, "Verified address on file.")
    return check(CheckStatus.Fail, "No verified email address on this account.")


def _github_association_check(link: _Link, user: User) -> Check | None:
    check = functools.partial(Check, "github_association", "GitHub account association")

    association = next(
        (
            a
            for a in user.account_associations
            if isinstance(a, OAuthAccountAssociation) and a.service == "github"
        ),
        None,
    )
    if association is not None:
        return check(CheckStatus.Ok, f"Linked to {association.external_username}.")

    if not link.github:
        return None
    return check(CheckStatus.Warn, "No GitHub account linked.")


def _projects_check(user: User) -> Check:
    check = functools.partial(Check, "has_projects", "Applicant has projects")

    count = len(user.projects)
    if count:
        return check(
            CheckStatus.Ok,
            f"{count} project{'' if count == 1 else 's'} on this account.",
        )
    return check(CheckStatus.Warn, "No projects on this account.")


def _name_conflict_check(
    application: OrganizationApplication,
    related_applications: Sequence[OrganizationApplication],
) -> Check | None:
    count = sum(
        1
        for other in related_applications
        if other.normalized_name == application.normalized_name
        and other.status in OPEN_APPLICATION_STATUSES
    )
    if not count:
        return None

    return Check(
        "name_conflict",
        "No competing applications",
        CheckStatus.Warn,
        f"{count} other open application{'' if count == 1 else 's'} "
        f"for {application.normalized_name}.",
    )


def application_domain(application: OrganizationApplication) -> str | None:
    """The domain the checks matched against, for the saved replies to quote."""
    return _Link(application.link_url).registered_domain


def review_checks(
    application: OrganizationApplication,
    user: User,
    related_applications: Sequence[OrganizationApplication] = (),
) -> list[Check]:
    """
    Build the reviewer-facing checks, most actionable first.
    """
    link = _Link(application.link_url)
    candidates = [
        _domain_match_check(link, user),
        _url_shape_check(link),
        _name_domain_check(application, link),
        _email_verified_check(user),
        _github_association_check(link, user),
        _projects_check(user),
        _name_conflict_check(application, related_applications),
    ]
    return sorted(
        (check for check in candidates if check is not None),
        key=lambda check: _STATUS_ORDER[check.status],
    )
