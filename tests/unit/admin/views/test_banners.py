# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pretend
import pytest

from pyramid.httpexceptions import HTTPNotFound
from sqlalchemy.exc import NoResultFound
from webob.multidict import MultiDict

from warehouse.admin.views import banners as views
from warehouse.banners.models import Banner

from ....common.db.banners import BannerFactory


@pytest.fixture
def banner_data():
    """Fixture with minimal required data to create a banner"""
    return {
        "name": "Sample Banner",
        "text": "This should be the correct text",
        "link_url": "https://samplebanner.com",
        "end": (datetime.date.today() + datetime.timedelta(days=2)).isoformat(),
    }


class TestBannerList:
    def test_list_all_banners(self, db_request):
        BannerFactory.create_batch(5)
        banners = db_request.db.query(Banner).all()

        result = views.banner_list(db_request)

        assert result == {"banners": banners}


class TestCreateBanner:
    def test_serialize_form_to_create_banner(self, db_request):
        result = views.create_banner(db_request)

        assert len(result) == 1
        assert isinstance(result["form"], views.BannerForm)

    def test_serialize_form_errors_if_invalid_post(self, db_request):
        db_request.method = "POST"
        db_request.POST["name"] = ""
        db_request.POST["link_url"] = ""
        db_request.POST = MultiDict(db_request.POST)

        result = views.create_banner(db_request)

        assert len(result) == 1
        assert isinstance(result["form"], views.BannerForm)
        assert result["form"].errors

    def test_create_banner(self, db_request, banner_data):
        db_request.method = "POST"
        db_request.POST = MultiDict(banner_data)
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_url = pretend.call_recorder(lambda r: "/admin/banners/")

        assert db_request.db.query(Banner).count() == 0
        resp = views.create_banner(db_request)
        assert db_request.db.query(Banner).count() == 1

        assert resp.status_code == 303
        assert resp.location == "/admin/banners/"
        assert db_request.session.flash.calls == [
            pretend.call("Added new banner 'Sample Banner'", queue="success")
        ]
        assert db_request.route_url.calls == [pretend.call("admin.banner.list")]


class TestEditBanner:
    def test_serialize_form_and_banner(self, db_request):
        banner = BannerFactory.create()
        db_request.matchdict["banner_id"] = banner.id

        result = views.edit_banner(db_request)

        assert len(result) == 2
        assert isinstance(result["form"], views.BannerForm)
        assert result["form"].data["name"] == banner.name
        assert result["banner"] == banner

    def test_404_if_banner_does_not_exist(self, db_request):
        db_request.matchdict["banner_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.edit_banner(db_request)

    def test_update_banner(self, db_request, banner_data):
        banner = BannerFactory.create(fa_icon="custom")
        assert banner.is_live
        form = views.BannerForm(MultiDict(), banner)
        data = form.data.copy()
        data["name"] = "New Name"
        data["end"] = str(data["end"])
        data.pop("fa_icon")  # do not send fa icon within post data
        db_request.matchdict["banner_id"] = banner.id
        db_request.method = "POST"
        db_request.POST = MultiDict(data)
        db_request.current_route_path = pretend.call_recorder(
            lambda: f"/admin/banners/{banner.id}/"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.edit_banner(db_request)
        db_banner = db_request.db.query(Banner).filter(Banner.id == banner.id).one()

        assert resp.status_code == 303
        assert resp.location == f"/admin/banners/{banner.id}/"
        assert db_banner.name == "New Name"
        assert db_banner.fa_icon == "custom"  # keep previous value
        assert db_request.session.flash.calls == [
            pretend.call("Banner updated", queue="success")
        ]

    def test_form_errors_if_invalid_post_data(self, db_request):
        banner = BannerFactory.create()
        form = views.BannerForm(MultiDict(), banner)
        data = form.data.copy()
        data["name"] = "New name"
        data["end"] = ""  # date is required
        db_request.matchdict["banner_id"] = banner.id
        db_request.method = "POST"
        db_request.POST = MultiDict(data)

        result = views.edit_banner(db_request)

        assert "end" in result["form"].errors
        assert "New name" == result["form"].data["name"]


class TestDeleteBanner:
    def test_404_if_banner_does_not_exist(self, db_request):
        db_request.matchdict["banner_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.delete_banner(db_request)

    def test_delete_banner(self, db_request):
        banner = BannerFactory.create()
        db_request.matchdict["banner_id"] = banner.id
        db_request.params = {"banner": banner.name}
        db_request.method = "POST"
        db_request.route_url = pretend.call_recorder(lambda s: "/admin/banners/")
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.delete_banner(db_request)
        with pytest.raises(NoResultFound):
            db_request.db.query(Banner).filter(Banner.id == banner.id).one()

        assert resp.status_code == 303
        assert resp.location == "/admin/banners/"
        assert db_request.session.flash.calls == [
            pretend.call(f"Deleted banner {banner.name}", queue="success")
        ]
        assert db_request.route_url.calls == [pretend.call("admin.banner.list")]

    def test_do_not_delete_banner_if_invalid_confirmation_param(self, db_request):
        banner = BannerFactory.create()
        db_request.matchdict["banner_id"] = banner.id
        db_request.params = {"banner": "not the banner name"}
        db_request.method = "POST"
        db_request.route_url = pretend.call_recorder(
            lambda s, banner_id: f"/admin/banners/{banner_id}"
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        resp = views.delete_banner(db_request)
        banner = db_request.db.query(Banner).filter(Banner.id == banner.id).one()

        assert resp.status_code == 303
        assert resp.location == f"/admin/banners/{banner.id}"
        assert db_request.session.flash.calls == [
            pretend.call("Wrong confirmation input", queue="error")
        ]
        assert db_request.route_url.calls == [
            pretend.call("admin.banner.edit", banner_id=banner.id)
        ]


class TestPreviewBanner:
    def test_404_if_banner_does_not_exist(self, db_request):
        db_request.matchdict["banner_id"] = str(uuid.uuid4())

        with pytest.raises(HTTPNotFound):
            views.preview_banner(db_request)

    def test_preview_banner(self, db_request):
        banner = BannerFactory.create()
        db_request.matchdict["banner_id"] = str(banner.id)

        resp = views.preview_banner(db_request)
        assert {"banner": banner} == resp


class TestBannerForm:
    def test_validate(self, banner_data):
        form = views.BannerForm(MultiDict(banner_data))
        assert form.validate(), str(form.errors)
        data = form.data
        defaults = {
            "fa_icon": Banner.DEFAULT_FA_ICON,
            "active": False,
            "dismissable": False,
            "link_label": Banner.DEFAULT_BTN_LABEL,
        }

        # Mash the `end` into a date object to match the form's coerced result.
        banner_data["end"] = datetime.date.fromisoformat(banner_data["end"])
        assert data == {**banner_data, **defaults}

    def test_required_fields(self, banner_data):
        form = views.BannerForm(MultiDict())

        assert form.validate() is False
        assert set(form.errors) == set(banner_data)
