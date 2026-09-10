# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.organizations.checks import (
    CheckStatus,
    _email_domain,
    _Link,
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
            ("https://localhost", None),
            ("https://ACME.com", "acme.com"),
            # A backslash ends the host, so the credential-looking tail is not it.
            (r"https://acme.com\@evil.example", "acme.com"),
            # Unparseable, rather than raising into the admin view.
            ("https://acme.com:99999", None),
            # Parses, but carries no host.
            ("https://", None),
        ],
    )
    def test_registered_domain(self, value, expected):
        assert _Link(value).registered_domain == expected

    @pytest.mark.parametrize(
        ("value", "unverifiable", "github"),
        [
            ("https://acme.com", False, False),
            ("https://github.com/acme", True, True),
            ("https://GITHUB.COM/acme", True, True),
            ("https://acme.github.io", True, True),
            ("https://gitlab.com/acme", True, False),
        ],
    )
    def test_host_classification(self, value, unverifiable, github):
        link = _Link(value)
        assert (link.unverifiable, link.github) == (unverifiable, github)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("jdoe@acme.com", "acme.com"),
            ("jdoe@ACME.com", "acme.com"),
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

    def test_shared_host_is_unknown(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://github.com/acme", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Unknown
        assert "hosts many unrelated organizations" in check.detail

    def test_verified_match_passes(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Ok

    def test_verified_match_handles_internationalized_domains(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@bücher.de", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://bücher.de", submitted_by=user
        )

        check = find(review_checks(application, user), "domain_match")
        assert check.status == CheckStatus.Ok

    def test_verified_match_ignores_case(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@ACME.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://ACME.com", submitted_by=user
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
        assert find(checks, "url_shape_codehost") is None

    def test_github_url(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://github.com/acme", submitted_by=user
        )

        check = find(review_checks(application, user), "url_shape_github")
        assert check.status == CheckStatus.Warn
        assert "github.com" in check.detail

    def test_other_code_host(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://gitlab.com/acme", submitted_by=user
        )

        check = find(review_checks(application, user), "url_shape_codehost")
        assert check.status == CheckStatus.Warn
        assert "gitlab.com" in check.detail


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
    def test_passes_with_verified_email(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(user=user, email="jdoe@acme.com", verified=True)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert (
            find(review_checks(application, user), "email_verified").status
            == CheckStatus.Ok
        )

    def test_fails_without_any_verified_email(self, db_request):
        user = UserFactory.create()
        EmailFactory.create(
            user=user, email="jdoe@acme.com", verified=False, primary=False
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert (
            find(review_checks(application, user), "email_verified").status
            == CheckStatus.Fail
        )


class TestGitHubAssociation:
    def test_omitted_for_non_github_urls_when_unlinked(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        assert find(review_checks(application, user), "github_association") is None

    def test_reported_for_non_github_urls_when_linked(self, db_request):
        # A linked account corroborates identity whatever the application URL is.
        user = UserFactory.create()
        OAuthAccountAssociationFactory.create(
            user=user, service="github", external_username="jdoe"
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "github_association")
        assert check.status == CheckStatus.Ok
        assert "jdoe" in check.detail

    def test_warns_when_unlinked(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            link_url="https://github.com/acme", submitted_by=user
        )

        check = find(review_checks(application, user), "github_association")
        assert check.status == CheckStatus.Warn

    def test_passes_when_linked(self, db_request):
        user = UserFactory.create()
        OAuthAccountAssociationFactory.create(
            user=user, service="github", external_username="jdoe"
        )
        application = OrganizationApplicationFactory.create(
            link_url="https://github.com/acme", submitted_by=user
        )

        check = find(review_checks(application, user), "github_association")
        assert check.status == CheckStatus.Ok
        assert "jdoe" in check.detail


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

    def test_singular_project(self, db_request):
        user = UserFactory.create()
        RoleFactory.create(user=user)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "has_projects")
        assert check.status == CheckStatus.Ok
        assert check.detail == "1 project on PyPI."

    def test_plural_projects(self, db_request):
        user = UserFactory.create()
        RoleFactory.create(user=user)
        RoleFactory.create(user=user)
        application = OrganizationApplicationFactory.create(
            link_url="https://acme.com", submitted_by=user
        )

        check = find(review_checks(application, user), "has_projects")
        assert check.detail == "2 projects on PyPI."


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

    def test_pluralizes_multiple_conflicts(self, db_request):
        user = UserFactory.create()
        application = OrganizationApplicationFactory.create(
            name="acme", link_url="https://acme.com", submitted_by=user
        )
        others = [
            OrganizationApplicationFactory.create(name="acme"),
            OrganizationApplicationFactory.create(name="acme"),
        ]

        check = find(review_checks(application, user, others), "name_conflict")
        assert "2 other open applications" in check.detail


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

