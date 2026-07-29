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
from urllib3.util import parse_url

from warehouse.accounts.models import OAuthAccountAssociation
from warehouse.organizations.models import OrganizationApplicationStatus

if TYPE_CHECKING:
    from warehouse.accounts.models import User
    from warehouse.organizations.models import OrganizationApplication

_extractor = TLDExtract(suffix_list_urls=())

# Hosts that are public suffixes so domain matching cant be used to affiliate
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

EMBARGOED_TLDS = {"cu", "ir", "kp", "sy"}
SECTORAL_TLDS = {"by", "ru"}

# Only reached for names the substring test misses, i.e. edits in the middle of a word.
# A single dropped or transposed letter scores 0.75+, while unrelated names score under
# 0.5 (`acme` against `globex` is 0.20), so any value in that gap behaves the same.
NAME_SIMILARITY_THRESHOLD = 0.6

_MIN_SUBSTRING_LENGTH = 3


class CheckStatus(enum.StrEnum):
    Ok = "ok"
    Fail = "fail"
    Warn = "warn"
    Unknown = "unknown"


class Verdict(enum.StrEnum):
    Ready = "ready"
    Review = "review"
    NeedsInfo = "needsinfo"


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


class _Link:
    """Every view of an application's URL the checks need, parsed once."""

    def __init__(self, raw: str) -> None:
        extracted = _extractor(raw)
        self.host = parse_url(raw).host or raw
        self.registered_domain = extracted.top_domain_under_public_suffix or None
        self.domain_label = extracted.domain
        # The country-code label of a suffix, so `co.ir` reads as `ir`.
        self.terminal_tld = extracted.suffix.rpartition(".")[2]
        # `github.io` and `readthedocs.io` are themselves public suffixes, so a match
        # can land on either component depending on the host.
        parts = {extracted.top_domain_under_public_suffix, extracted.suffix}
        self.unverifiable = bool(parts & UNVERIFIABLE_URL_HOSTS)
        self.github = bool(parts & GITHUB_HOSTS)


def _email_domain(email: str) -> str | None:
    _, _, domain = email.rpartition("@")
    return _extractor(domain).top_domain_under_public_suffix or None if domain else None


def _comparable(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _resembles(candidate: str, target: str) -> bool:
    if min(len(candidate), len(target)) >= _MIN_SUBSTRING_LENGTH and (
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
            f"{link.registered_domain} hosts many unrelated organizations, so an "
            "address there would identify nobody. Establish affiliation another way.",
        )

    verified = [email.email for email in user.emails if email.verified]
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
        f"No verified @{link.registered_domain} address — "
        f"holds {', '.join(sorted(verified))}.",
    )


def _url_shape_check(link: _Link) -> Check | None:
    # Two keys: the template routes each to a different saved reply.
    if not link.unverifiable:
        return None

    label = "Application URL is an organization homepage"
    if link.github:  # TODO: may want to also check for other code forgers
        return Check(
            "url_shape_github",
            label,
            CheckStatus.Warn,
            f"Points at {link.host} rather than the organization's own site. Ask for "
            "public GitHub membership and an account association.",
        )
    return Check(
        "url_shape_codehost",
        label,
        CheckStatus.Warn,
        f"Points at {link.host}, a code or package host, rather than the "
        "organization's own site.",
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
    if not target or not candidates:
        return None

    if any(_resembles(candidate, target) for candidate in candidates):
        return check(
            CheckStatus.Ok, f"“{application.name}” lines up with {link.domain_label}."
        )
    return check(
        CheckStatus.Warn,
        f"“{application.name}” looks unrelated to {link.domain_label} — "
        "confirm they are the same organization.",
    )


def _email_verified_check(user: User) -> Check:
    check = functools.partial(Check, "email_verified", "Applicant has a verified email")

    if any(email.verified for email in user.emails):
        return check(CheckStatus.Ok, "Verified address on file.")
    return check(CheckStatus.Fail, "No verified email address on this account.")


def _github_association_check(link: _Link, user: User) -> Check | None:
    """A link corroborates identity anywhere; absence only matters on GitHub URLs."""
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
    return check(
        CheckStatus.Warn, "No GitHub account linked, so membership cannot be verified."
    )


def _projects_check(user: User) -> Check:
    check = functools.partial(Check, "has_projects", "Applicant has published projects")

    count = len(user.projects)
    if count:
        return check(
            CheckStatus.Ok, f"{count} project{'' if count == 1 else 's'} on PyPI."
        )
    return check(
        CheckStatus.Warn, "No projects on PyPI — ask why an organization is needed."
    )


def _restricted_tld_check(link: _Link) -> Check | None:
    if link.terminal_tld in EMBARGOED_TLDS:
        reason = "a comprehensively embargoed jurisdiction"
    elif link.terminal_tld in SECTORAL_TLDS:
        reason = "a jurisdiction under targeted sectoral sanctions"
    else:
        return None

    return Check(
        "restricted_tld",
        "Jurisdiction review",
        CheckStatus.Warn,
        f".{link.terminal_tld} maps to {reason} — confirm before approving.",
    )


def _name_conflict_check(
    application: OrganizationApplication,
    related_applications: Sequence[OrganizationApplication],
) -> Check | None:
    count = sum(
        1
        for other in related_applications
        if other.normalized_name == application.normalized_name
        and other.status != OrganizationApplicationStatus.Declined
    )
    if not count:
        return None

    return Check(
        "name_conflict",
        "Organization name is unclaimed",
        CheckStatus.Warn,
        f"{count} other open application{'' if count == 1 else 's'} "
        f"for “{application.normalized_name}”.",
    )


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
        _restricted_tld_check(link),
        _name_conflict_check(application, related_applications),
    ]
    return sorted(
        (check for check in candidates if check is not None),
        key=lambda check: _STATUS_ORDER[check.status],
    )


def verdict(checks: list[Check]) -> Verdict:
    statuses = {check.status for check in checks}
    if CheckStatus.Fail in statuses:
        return Verdict.NeedsInfo
    if CheckStatus.Warn in statuses or CheckStatus.Unknown in statuses:
        return Verdict.Review
    return Verdict.Ready
