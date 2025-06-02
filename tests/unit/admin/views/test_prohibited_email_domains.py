# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther

from warehouse.admin.views import prohibited_email_domains as views

from ....common.db.accounts import ProhibitedEmailDomain, ProhibitedEmailDomainFactory


class TestProhibitedEmailDomainsList:
    def test_no_query(self, db_request):
        prohibited = sorted(
            ProhibitedEmailDomainFactory.create_batch(30),
            key=lambda b: b.created,
        )

        result = views.prohibited_email_domains(db_request)

        assert result == {"prohibited_email_domains": prohibited[:25], "query": None}

    def test_with_page(self, db_request):
        prohibited = sorted(
            ProhibitedEmailDomainFactory.create_batch(30),
            key=lambda b: b.created,
        )
        db_request.GET["page"] = "2"

        result = views.prohibited_email_domains(db_request)

        assert result == {"prohibited_email_domains": prohibited[25:], "query": None}

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.prohibited_email_domains(request)

    def test_basic_query(self, db_request):
        prohibited = sorted(
            ProhibitedEmailDomainFactory.create_batch(30),
            key=lambda b: b.created,
        )
        db_request.GET["q"] = prohibited[0].domain

        result = views.prohibited_email_domains(db_request)

        assert result == {
            "prohibited_email_domains": [prohibited[0]],
            "query": prohibited[0].domain,
        }

    def test_wildcard_query(self, db_request):
        prohibited = sorted(
            ProhibitedEmailDomainFactory.create_batch(30),
            key=lambda b: b.created,
        )
        db_request.GET["q"] = f"{prohibited[0].domain[:-1]}%"

        result = views.prohibited_email_domains(db_request)

        assert result == {
            "prohibited_email_domains": [prohibited[0]],
            "query": f"{prohibited[0].domain[:-1]}%",
        }


class TestProhibitedEmailDomainsAdd:
    def test_no_email_domain(self, db_request):
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/add/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {}

        with pytest.raises(HTTPSeeOther):
            views.add_prohibited_email_domain(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Email domain is required.", queue="error")
        ]

    def test_invalid_domain(self, db_request):
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/add/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"email_domain": "invalid"}

        with pytest.raises(HTTPSeeOther):
            views.add_prohibited_email_domain(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Invalid domain name 'invalid'", queue="error")
        ]

    def test_duplicate_domain(self, db_request):
        existing_domain = ProhibitedEmailDomainFactory.create()
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/add/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"email_domain": existing_domain.domain}

        with pytest.raises(HTTPSeeOther):
            views.add_prohibited_email_domain(db_request)

        assert db_request.session.flash.calls == [
            pretend.call(
                f"Email domain '{existing_domain.domain}' already exists.",
                queue="error",
            )
        ]

    @pytest.mark.parametrize(
        ("input_domain", "expected_domain"),
        [
            ("example.com", "example.com"),
            ("mail.example.co.uk", "example.co.uk"),
            ("https://example.com/", "example.com"),
        ],
    )
    def test_success(self, db_request, input_domain, expected_domain):
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/list/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {
            "email_domain": input_domain,
            "is_mx_record": "on",
            "comment": "testing",
        }

        response = views.add_prohibited_email_domain(db_request)

        assert response.status_code == 303
        assert response.headers["Location"] == "/admin/prohibited_email_domains/list/"
        assert db_request.session.flash.calls == [
            pretend.call("Prohibited email domain added.", queue="success")
        ]

        query = db_request.db.query(ProhibitedEmailDomain).filter(
            ProhibitedEmailDomain.domain == expected_domain
        )
        assert query.count() == 1
        assert query.one().is_mx_record
        assert query.one().comment == "testing"


class TestProhibitedEmailDomainsRemove:
    def test_no_domain_name(self, db_request):
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/remove/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {}

        with pytest.raises(HTTPSeeOther):
            views.remove_prohibited_email_domain(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Domain name is required.", queue="error")
        ]

    def test_domain_not_found(self, db_request):
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/remove/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"domain_name": "example.com"}

        with pytest.raises(HTTPSeeOther):
            views.remove_prohibited_email_domain(db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Domain not found.", queue="error")
        ]

    def test_success(self, db_request):
        domain = ProhibitedEmailDomainFactory.create()
        db_request.method = "POST"
        db_request.route_path = lambda a: "/admin/prohibited_email_domains/list/"
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.POST = {"domain_name": domain.domain}

        response = views.remove_prohibited_email_domain(db_request)

        assert response.status_code == 303
        assert response.headers["Location"] == "/admin/prohibited_email_domains/list/"
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Prohibited email domain '{domain.domain}' removed.", queue="success"
            )
        ]

        query = db_request.db.query(ProhibitedEmailDomain).filter(
            ProhibitedEmailDomain.domain == domain.domain
        )
        assert query.count() == 0
