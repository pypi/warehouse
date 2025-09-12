# SPDX-License-Identifier: Apache-2.0

from warehouse.banners import views

from ...common.db.banners import BannerFactory


def test_list_active_banners(db_request):
    active_banner = BannerFactory.create()
    assert active_banner.is_live
    inactive_banner = BannerFactory.create(active=False)
    assert inactive_banner.is_live is False

    result = views.list_banner_messages(db_request)

    assert result["banners"] == [active_banner]


def test_list_specific_banner_for_preview(db_request):
    active_banner = BannerFactory.create()
    assert active_banner.is_live
    inactive_banner = BannerFactory.create(active=False)
    assert inactive_banner.is_live is False

    db_request.params = {"single_banner": str(inactive_banner.id)}
    result = views.list_banner_messages(db_request)

    assert result["banners"] == [inactive_banner]
