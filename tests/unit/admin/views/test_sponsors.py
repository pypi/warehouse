# SPDX-License-Identifier: Apache-2.0

import io
import secrets
import uuid

from cgi import FieldStorage
from unittest import TestCase

import pretend
import pytest

from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.exc import NoResultFound
from webob.multidict import MultiDict

from warehouse.admin.interfaces import ISponsorLogoStorage
from warehouse.admin.views import sponsors as views
from warehouse.sponsors.models import Sponsor

from ....common.db.sponsors import SponsorFactory

COLOR_LOGO_FILE = FieldStorage()
COLOR_LOGO_FILE.filename = "colorlogo.png"
COLOR_LOGO_FILE.file = io.BytesIO(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac\xfc\xcf\xc0P\x0f\x00"
    b"\x04\x85\x01\x80\x84\xa9\x8c!\x00\x00\x00\x00IEND\xaeB`\x82"
)
COLOR_LOGO_FILE.type = "image/png"

WHITE_LOGO_FILE = FieldStorage()
WHITE_LOGO_FILE.filename = "whitelogo.png"
WHITE_LOGO_FILE.file = io.BytesIO(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\xdac\xfc\xcf\xc0P\x0f\x00"
    b"\x04\x85\x01\x80\x84\xa9\x8c!\x00\x00\x00\x00IEND\xaeB`\x82"
)
WHITE_LOGO_FILE.type = "image/png"


class TestSponsorForm(TestCase):
    def setUp(self):
        self.data = {
            "name": "Sponsor",
            "link_url": "https://newsponsor.com",
            "color_logo_url": "http://domain.com/image.jpg",
        }

    def test_validate(self):
        form = views.SponsorForm(formdata=MultiDict(self.data))
        assert form.validate(), str(form.errors)

    def test_required_fields(self):
        required_fields = ["name", "link_url", "color_logo_url"]

        form = views.SponsorForm(formdata=MultiDict({"color_logo_url": ""}))

        assert form.validate() is False
        assert len(form.errors) == len(required_fields)
        for field in required_fields:
            assert field in form.errors

    def test_white_logo_is_required_for_footer_display(self):
        self.data["footer"] = True

        # don't validate without logo
        form = views.SponsorForm(formdata=MultiDict(self.data))
        assert form.validate() is False
        assert "white_logo" in form.errors

        self.data["white_logo_url"] = "http://domain.com/white-logo.jpg"
        form = views.SponsorForm(formdata=MultiDict(self.data))
        assert form.validate() is True

    def test_white_logo_is_required_for_infra_display(self):
        self.data["infra_sponsor"] = True

        # don't validate without logo
        form = views.SponsorForm(formdata=MultiDict(self.data))
        assert form.validate() is False
        assert "white_logo" in form.errors

        self.data["white_logo_url"] = "http://domain.com/white-logo.jpg"
        form = views.SponsorForm(formdata=MultiDict(self.data))
        assert form.validate() is True


class TestSponsorList:
    def test_list_all_sponsors(self, db_request):
        SponsorFactory.create_batch(5)
        sponsors = db_request.db.query(Sponsor).order_by(Sponsor.name).all()

        result = views.sponsor_list(db_request)

        assert result == {"sponsors": sponsors}


class TestCreateSponsor:
    def test_serialize_form_to_create_sponsor(self, db_request):
        result = views.create_sponsor(db_request)

        assert len(result) == 1
        assert isinstance(result["form"], views.SponsorForm)

    def test_serialize_form_errors_if_invalid_post(self, db_request):
        db_request.method = "POST"
        db_request.POST["name"] = ""
        db_request.POST["link_url"] = ""
        db_request.POST = MultiDict(db_request.POST)

        result = views.create_sponsor(db_request)

        assert len(result) == 1
        assert isinstance(result["form"], views.SponsorForm)
        assert result["form"].errors

    def test_create_sponsor(self, db_request):
        db_request.method = "POST"
        db_request.POST["name"] = "Sponsor"
        db_request.POST["link_url"] = "https://newsponsor.com"
        db_request.POST["color_logo"] = COLOR_LOGO_FILE
        db_request.POST = MultiDict(db_request.POST)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_url = pretend.call_recorder(lambda r: "/admin/sponsors/")
        storage_service = pretend.stub(
            store=pretend.call_recorder(
                lambda path, file_path, ct: f"http://files/sponsorlogos/{path}"
            )
        )
        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                ISponsorLogoStorage: storage_service,
            }.get(svc)
        )

        resp = views.create_sponsor(db_request)

        assert resp.status_code == 303
        assert resp.location == "/admin/sponsors/"
        assert db_request.session.flash.calls == [
            pretend.call("Added new sponsor 'Sponsor'", queue="success")
        ]
        assert db_request.route_url.calls == [pretend.call("admin.sponsor.list")]


class TestEditSponsor:
    def test_serialize_form_and_sponsor(self, db_request):
        sponsor = SponsorFactory.create()
        db_request.matchdict["sponsor_id"] = sponsor.id

        result = views.edit_sponsor(db_request)

        assert len(result) == 2
        assert isinstance(result["form"], views.SponsorForm)
        assert result["form"].data["name"] == sponsor.name
        assert result["sponsor"] == sponsor

    def test_404_if_sponsor_does_not_exist(self, db_request):
        db_request.matchdict["sponsor_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.edit_sponsor(db_request)

    def test_update_sponsor(self, monkeypatch, db_request):
        sponsor = SponsorFactory.create()
        form = views.SponsorForm(MultiDict({}), sponsor)
        data = form.data.copy()
        data["name"] = "New Name"
        data["white_logo"] = WHITE_LOGO_FILE
        data["color_logo"] = COLOR_LOGO_FILE
        db_request.matchdict["sponsor_id"] = sponsor.id
        db_request.method = "POST"
        db_request.POST = MultiDict(data)
        db_request.current_route_path = pretend.call_recorder(
            lambda: f"/admin/sponsors/{sponsor.id}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        storage_service = pretend.stub(
            store=pretend.call_recorder(
                lambda path, file_path, ct: f"http://files/sponsorlogos/{path}"
            )
        )
        db_request.find_service = pretend.call_recorder(
            lambda svc, name=None, context=None: {
                ISponsorLogoStorage: storage_service,
            }.get(svc)
        )

        monkeypatch.setattr(secrets, "token_urlsafe", lambda x: "deadbeef")

        resp = views.edit_sponsor(db_request)

        db_sponsor = db_request.db.query(Sponsor).filter(Sponsor.id == sponsor.id).one()

        assert resp.status_code == 303
        assert resp.location == f"/admin/sponsors/{sponsor.id}/"
        assert db_sponsor.name == "New Name"
        assert (
            db_sponsor.white_logo_url
            == "http://files/sponsorlogos/new-name-white-logo-deadbeef.png"
        )
        assert (
            db_sponsor.color_logo_url
            == "http://files/sponsorlogos/new-name-color-logo-deadbeef.png"
        )
        assert db_request.session.flash.calls == [
            pretend.call("Sponsor updated", queue="success")
        ]

    def test_form_errors_if_invalid_post_data(self, db_request):
        sponsor = SponsorFactory.create()
        form = views.SponsorForm(MultiDict({}), sponsor)
        data = form.data.copy()
        data["name"] = ""  # name is required
        db_request.matchdict["sponsor_id"] = sponsor.id
        db_request.method = "POST"
        db_request.POST = MultiDict(data)

        result = views.edit_sponsor(db_request)

        assert "name" in result["form"].errors


class TestDeleteSponsor:
    def test_404_if_sponsor_does_not_exist(self, db_request):
        db_request.matchdict["sponsor_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.delete_sponsor(db_request)

    def test_delete_sponsor(self, db_request):
        sponsor = SponsorFactory.create()
        db_request.matchdict["sponsor_id"] = sponsor.id
        db_request.params = {"sponsor": sponsor.name}
        db_request.method = "POST"
        db_request.route_url = pretend.call_recorder(lambda s: "/admin/sponsors/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.delete_sponsor(db_request)
        with pytest.raises(NoResultFound):
            db_request.db.query(Sponsor).filter(Sponsor.id == sponsor.id).one()

        assert resp.status_code == 303
        assert resp.location == "/admin/sponsors/"
        assert db_request.session.flash.calls == [
            pretend.call(f"Deleted sponsor {sponsor.name}", queue="success")
        ]
        assert db_request.route_url.calls == [pretend.call("admin.sponsor.list")]

    def test_do_not_delete_sponsor_if_invalid_confirmation_param(self, db_request):
        sponsor = SponsorFactory.create()
        db_request.matchdict["sponsor_id"] = sponsor.id
        db_request.params = {"sponsor": "not the sponsor name"}
        db_request.method = "POST"
        db_request.route_url = pretend.call_recorder(
            lambda s, sponsor_id: f"/admin/sponsors/{sponsor_id}"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.delete_sponsor(db_request)
        sponsor = db_request.db.query(Sponsor).filter(Sponsor.id == sponsor.id).one()

        assert resp.status_code == 303
        assert resp.location == f"/admin/sponsors/{sponsor.id}"
        assert db_request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error")
        ]
        assert db_request.route_url.calls == [
            pretend.call("admin.sponsor.edit", sponsor_id=sponsor.id)
        ]
