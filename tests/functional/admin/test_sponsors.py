# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.sponsors import SponsorFactory


class TestSponsorsList:
    def test_renders_tabulator_table(self, webtest, login_admin):
        login_admin()
        sponsor = SponsorFactory.create(name="Example Corp", level_order=1)

        page = webtest.get("/admin/sponsors/", status=HTTPStatus.OK)

        table = page.html.find(id="sponsors")
        assert table.has_attr("data-tabulator")
        assert table.has_attr("data-tabulator-column-menu")
        assert sponsor.name in table.get_text()

    def test_unleveled_sponsors_render_last(self, webtest, login_admin):
        login_admin()
        SponsorFactory.create(name="no-level", level_order=0)
        SponsorFactory.create(name="leveled", level_order=1)

        page = webtest.get("/admin/sponsors/", status=HTTPStatus.OK)

        names = [
            row.find_all("td")[1].get_text(strip=True)
            for row in page.html.find(id="sponsors").find("tbody").find_all("tr")
        ]
        assert names == ["leveled", "no-level"]
