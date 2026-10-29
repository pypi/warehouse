# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.organizations.checks import (
    CheckStatus,
    _email_domain,
    _Link,
    can_email,
    review_checks,
)
from warehouse.organizations.models import OrganizationApplicationStatus

from ...common.db.accounts import (
    EmailFactory,
    OAuthAccountAssociationFactory,
    UserFactory,
)
from ...common.db.organizations import OrganizationApplicationFactory
from ...common.db.packaging import RoleFactory


def find(checks, key):
    return next((check for check in checks if check.key == key), None)


class TestLink:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://acme.com/about", "acme.com"),
            ("https://dept.acme.com", "acme.com"),
            ("https://acme.co.uk", "acme.co.uk"),
            ("https://acme.blogspot.com", "acme.blogspot.com"),
            ("https://acme.github.io", "acme.github.io"),
            ("https://localhost", None),
            ("https://ACME.com", "acme.com"),
            # A backslash ends the host, so the credential-looking tail is not it.
            (r"https://acme.com\@evil.example", "acme.com"),
            # Unparsable, rather than raising into the admin view.
            ("https://acme.com:99999", None),
            # Parses, but carries no host.
            ("https://", None),
        ],
    )
    def test_registered_domain(self, value, expected):
        assert _Link(value).registered_domain == expected

    @pytest.mark.parametrize(
        ("value", "unverifiable", "github", "gitlab"),
        [
            ("https://acme.com", False, False, False),
            ("https://github.com/acme", True, True, False),
            ("https://GITHUB.COM/acme", True, True, False),
            ("https://acme.github.io", True, True, False),
            ("https://gitlab.com/acme", True, False, True),
            ("https://acme.gitlab.io", True, False, True),
            ("https://codeberg.org/acme", True, False, False),
            ("https://acme.uk.com", False, False, False),
        ],
    )
    def test_host_classification(self, value, unverifiable, github, gitlab):
        link = _Link(value)
        assert (link.unverifiable, link.github, link.gitlab) == (
            unverifiable,
            github,
            gitlab,
        )

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("jdoe@acme.com", "acme.com"),
            ("jdoe@ACME.com", "acme.com"),
            ("jdoe@other.blogspot.com", "other.blogspot.com"),
            ("jdoe@bücher.de", "xn--bcher-kva.de"),
            # A backslash would otherwise truncate this to `acme.com`.
            ("jdoe@acme.com\\evil.org", None),
            ("jdoe@mail.acme.com", "acme.com"),
            ("jdoe@localhost", None),
            ("", None),
        ],
    )
    def test_email_domain(self, value, expected):
        assert _email_domain(value) == expected


class TestDomainMatch:
    def test_unreadable_url_is_unknown(self, db_request):
        # `link_url` is constrained to ^https?:// at the database level, but a bare
        # host still has no registrable domain to match an email against.
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://localhost", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Unknown
        assert "No domain could be read" in check.detail

    @pytest.mark.parametrize(
        ("url", "email"),
        [
            ("https://github.com/acme", "jdoe@acme.com"),
            # A free email address can't show affiliation, even with the provider
            ("https://yahoo.com", "jdoe@yahoo.com"),
        ],
    )
    def test_shared_host_is_unknown(self, db_request, url, email):
        user = UserFactory.create()
        EmailFactory.create(user=user, email=email, verified=True)
        application = OrganizationApplicationFactory.create(
            link_url=url, submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Unknown

    def test_verified_match_passes(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Ok

    @pytest.mark.parametrize(
        ("email_domain", "status"),
        [("acme.uk.com", CheckStatus.Ok), ("other.uk.com", CheckStatus.Fail)],
    )
    def test_private_registry_domain(self, db_request, email_domain, status):
        user = UserFactory.create()
        EmailFactory.create(user=user, email=f"jdoe@{email_domain}", verified=True)
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://acme.uk.com", submitted_by=user
        )

        checks = review_checks(application, user)
        assert find(checks, "domain_match").status == status
        assert find(checks, "url_shape_codehost") is None
        assert find(checks, "name_domain_match").status == CheckStatus.Ok

    def test_verified_match_handles_internationalized_domains(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@bücher.de", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://bücher.de", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Ok

    def test_no_verified_email_is_unknown(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Unknown
        assert "No verified address" in check.detail

    def test_matching_but_unverified_fails(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@gmail.com", verified=True)
        EmailFactory.create(
            user=user, email="jdoe@acme.com", verified=False, primary=False
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Fail
        assert "not verified" in check.detail

    def test_mismatch_fails(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@gmail.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Fail
        assert "jdoe@gmail.com" in check.detail


class TestURLShape:
    def test_own_domain_omits_check(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        checks = review_checks(application, user)
        assert find(checks, "url_shape_github") is None
        assert find(checks, "url_shape_gitlab") is None
        assert find(checks, "url_shape_codehost") is None

    @pytest.mark.parametrize(
        ("link_url", "key", "host"),
        [
            ("https://github.com/acme", "url_shape_github", "github.com"),
            ("https://gitlab.com/acme", "url_shape_gitlab", "gitlab.com"),
            ("https://codeberg.org/acme", "url_shape_codehost", "codeberg.org"),
        ],
    )
    def test_shared_host_routes_to_its_reply(self, db_request, link_url, key, host):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url=link_url, submitted_by=user
        )

        checks = review_checks(application, user)
        shape_checks = [check for check in checks if check.key.startswith("url_shape")]
        assert [check.key for check in shape_checks] == [key]
        assert shape_checks[0].status == CheckStatus.Warn
        assert host in shape_checks[0].detail


class TestNameDomainMatch:
    def test_omitted_for_shared_hosts(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://github.com/acme", submitted_by=user
        )

        assert find(review_checks(application, user), "name_domain_match") is None

    def test_omitted_without_a_domain_label(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://localhost", submitted_by=user
        )

        assert find(review_checks(application, user), "name_domain_match") is None

    @pytest.mark.parametrize(
        ("name", "link_url"),
        [
            ("acme", "https://acme.com"),
            ("acme", "https://acme-corp.com"),
            ("acme-corp", "https://acme.com"),
            ("Acme", "https://ACME.com"),
            ("acmee", "https://acme.com"),
        ],
    )
    def test_related_names_pass(self, db_request, name, link_url):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name=name, display_name=name, link_url=link_url, submitted_by=user
        )

        check = find(review_checks(application, user), "name_domain_match")
        assert check.status == CheckStatus.Ok

    @pytest.mark.parametrize(
        ("name", "link_url"),
        [
            ("acme", "https://globex.com"),
            ("initech", "https://umbrella.org"),
        ],
    )
    def test_unrelated_names_warn(self, db_request, name, link_url):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name=name, display_name=name, link_url=link_url, submitted_by=user
        )

        check = find(review_checks(application, user), "name_domain_match")
        assert check.status == CheckStatus.Warn
        assert "looks unrelated" in check.detail

    def test_display_name_can_carry_the_match(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="ac-2026",
            display_name="Acme Corporation",
            link_url="https://acme.com",
            submitted_by=user,
        )

        check = find(review_checks(application, user), "name_domain_match")
        assert check.status == CheckStatus.Ok

    def test_short_names_do_not_match_on_containment(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="ab",
            display_name="ab",
            link_url="https://cabbage.com",
            submitted_by=user,
        )

        check = find(review_checks(application, user), "name_domain_match")
        assert check.status == CheckStatus.Warn


class TestEmailVerified:
    def test_passes_with_verified_primary(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert can_email(user)
        assert (
            find(review_checks(application, user), "email_verified").status
            == CheckStatus.Ok
        )

    def test_fails_with_unverified_primary_and_verified_secondary(self, db_request):
        # Mail goes only to the primary, so a verified secondary doesn't help.
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=False)
        EmailFactory.create(
            user=user, email="jdoe@gmail.com", verified=True, primary=False
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert not can_email(user)
        check = find(review_checks(application, user), "email_verified")
        assert check.status == CheckStatus.Fail
        assert "jdoe@acme.com is unverified" in check.detail

    def test_fails_without_primary_email(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(
            user=user, email="jdoe@acme.com", verified=True, primary=False
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert not can_email(user)
        check = find(review_checks(application, user), "email_verified")
        assert check.status == CheckStatus.Fail
        assert "No primary email" in check.detail


@pytest.mark.parametrize(
    ("service", "name", "link_url"),
    [
        ("github", "GitHub", "https://github.com/acme"),
        ("gitlab", "GitLab", "https://gitlab.com/acme"),
    ],
)
class TestAccountAssociation:
    def test_omitted_for_own_domain_when_unlinked(
        self, db_request, service, name, link_url
    ):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert find(review_checks(application, user), f"{service}_association") is None

    def test_reported_for_own_domain_when_linked(
        self, db_request, service, name, link_url
    ):
        # A linked account corroborates identity whatever the application URL is.
        user = UserFactory.create()
        OAuthAccountAssociationFactory.create(
            user=user, service=service, external_username="jdoe"
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), f"{service}_association")
        assert check.status == CheckStatus.Ok
        assert check.label == f"{name} account association"
        assert check.detail == "Linked to jdoe."

    def test_warns_when_unlinked_on_its_host(self, db_request, service, name, link_url):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url=link_url, submitted_by=user
        )

        checks = review_checks(application, user)
        check = find(checks, f"{service}_association")
        assert check.status == CheckStatus.Warn
        assert check.detail == f"No {name} account linked."
        # Only the URL's own service asks for a link.
        other = "gitlab" if service == "github" else "github"
        assert find(checks, f"{other}_association") is None


class TestProjects:
    def test_warns_with_no_projects(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert (
            find(review_checks(application, user), "has_projects").status
            == CheckStatus.Warn
        )

    def test_passes_with_projects(self, db_request):
        user = UserFactory.create()
        RoleFactory.create(user=user)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "has_projects")
        assert check.status == CheckStatus.Ok
        assert "1 project" in check.detail


class TestNameConflict:
    def test_omitted_without_conflicts(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert find(review_checks(application, user, []), "name_conflict") is None

    def test_declined_conflicts_are_ignored(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://acme.com", submitted_by=user
        )
        other = OrganizationApplicationFactory.create(
            name="acme", status=OrganizationApplicationStatus.Declined
        )

        assert find(review_checks(application, user, [other]), "name_conflict") is None

    def test_approved_conflicts_are_ignored(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://acme.com", submitted_by=user
        )
        other = OrganizationApplicationFactory.create(
            name="acme", status=OrganizationApplicationStatus.Approved
        )

        assert find(review_checks(application, user, [other]), "name_conflict") is None

    def test_warns_on_open_conflict(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://acme.com", submitted_by=user
        )
        other = OrganizationApplicationFactory.create(name="acme")

        check = find(review_checks(application, user, [other]), "name_conflict")
        assert check.status == CheckStatus.Warn
        assert "1 other open application" in check.detail


class TestReviewChecks:
    def test_orders_failures_before_passes(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@gmail.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        order = [
            CheckStatus.Fail,
            CheckStatus.Warn,
            CheckStatus.Unknown,
            CheckStatus.Ok,
        ]
        ranks = [
            order.index(check.status) for check in review_checks(application, user)
        ]
        assert ranks == sorted(ranks)
