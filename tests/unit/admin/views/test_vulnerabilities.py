# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther

from warehouse.admin.views import vulnerabilities as views
from warehouse.integrations.vulnerabilities.models import (
    ReleaseVulnerability,
    VulnerabilityRecord,
)

from ....common.db.integrations import VulnerabilityRecordFactory
from ....common.db.packaging import ProjectFactory, ReleaseFactory


@pytest.fixture
def stubbed_request(db_request, mocker):
    """db_request with route_path patched and session.flash spied."""
    mocker.patch.object(db_request, "route_path", return_value="/stub")
    mocker.spy(db_request.session, "flash")
    return db_request


class TestVulnerabilityList:
    def test_empty(self, db_request):
        db_request.db.query(VulnerabilityRecord).delete()
        result = views.vulnerability_list(db_request)

        assert list(result["vulnerabilities"]) == []
        assert result["release_counts"] == {}
        assert result["query"] is None

    def test_lists_and_counts(self, db_request):
        db_request.db.query(VulnerabilityRecord).delete()
        project = ProjectFactory.create()
        r1 = ReleaseFactory.create(project=project, version="1.0")
        r2 = ReleaseFactory.create(project=project, version="2.0")
        VulnerabilityRecordFactory.create(source="osv", id="PYSEC-1", releases=[r1, r2])
        VulnerabilityRecordFactory.create(source="osv", id="PYSEC-2", releases=[r1])

        result = views.vulnerability_list(db_request)

        assert [v.id for v in result["vulnerabilities"]] == ["PYSEC-1", "PYSEC-2"]
        assert result["release_counts"] == {
            ("osv", "PYSEC-1"): 2,
            ("osv", "PYSEC-2"): 1,
        }

    def test_invalid_page(self):
        with pytest.raises(HTTPBadRequest):
            views.vulnerability_list(SimpleNamespace(params={"page": "not-an-int"}))

    def test_pagination(self, db_request):
        db_request.db.query(VulnerabilityRecord).delete()
        for i in range(30):
            VulnerabilityRecordFactory.create(
                source="osv", id=f"PYSEC-{i:02d}", releases=[]
            )
        db_request.GET["page"] = "2"

        result = views.vulnerability_list(db_request)

        assert result["vulnerabilities"].item_count == 30
        assert len(list(result["vulnerabilities"])) == 5

    @pytest.mark.parametrize(
        ("records", "q", "expected_ids"),
        [
            pytest.param(
                [
                    {"source": "osv", "id": "ECHO-2024-001"},
                    {"source": "osv", "id": "PYSEC-2024-001"},
                ],
                "ECHO",
                ["ECHO-2024-001"],
                id="substring",
            ),
            pytest.param(
                [
                    {"source": "osv", "id": "ECHO-2024-001"},
                    {"source": "osv", "id": "PYSEC-2024-001"},
                ],
                "ECHO%",
                ["ECHO-2024-001"],
                id="explicit-wildcard",
            ),
            pytest.param(
                [
                    {"source": "osv", "id": "PYSEC-1", "aliases": ["CVE-2024-9999"]},
                    {"source": "osv", "id": "PYSEC-2", "aliases": ["CVE-2000-0001"]},
                ],
                "CVE-2024",
                ["PYSEC-1"],
                id="alias",
            ),
        ],
    )
    def test_search(self, db_request, records, q, expected_ids):
        db_request.db.query(VulnerabilityRecord).delete()
        for kwargs in records:
            VulnerabilityRecordFactory.create(releases=[], **kwargs)
        db_request.GET["q"] = q

        result = views.vulnerability_list(db_request)

        assert [v.id for v in result["vulnerabilities"]] == expected_ids


class TestVulnerabilityDetail:
    def test_not_found(self, db_request):
        db_request.matchdict = {"source": "osv", "id": "missing"}
        with pytest.raises(HTTPNotFound):
            views.vulnerability_detail(db_request)

    def test_returns_record_and_sorted_releases(self, db_request):
        project_b = ProjectFactory.create(name="bravo")
        project_a = ProjectFactory.create(name="Alpha")
        r_b1 = ReleaseFactory.create(project=project_b, version="1.0")
        r_a2 = ReleaseFactory.create(project=project_a, version="2.0")
        r_a1 = ReleaseFactory.create(project=project_a, version="1.0")
        vuln = VulnerabilityRecordFactory.create(
            source="osv", id="PYSEC-1", releases=[r_b1, r_a2, r_a1]
        )

        db_request.matchdict = {"source": vuln.source, "id": vuln.id}
        result = views.vulnerability_detail(db_request)

        assert result["vulnerability"] is vuln
        assert result["releases"] == [r_a1, r_a2, r_b1]


class TestVulnerabilityDelete:
    def test_not_found(self, db_request):
        db_request.matchdict = {"source": "osv", "id": "missing"}
        db_request.POST = {"confirm": "missing"}
        with pytest.raises(HTTPNotFound):
            views.vulnerability_delete(db_request)

    def test_requires_confirmation(self, stubbed_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        vuln = VulnerabilityRecordFactory.create(
            source="osv", id="PYSEC-1", releases=[release]
        )

        stubbed_request.matchdict = {"source": vuln.source, "id": vuln.id}
        stubbed_request.POST = {"confirm": "wrong"}

        result = views.vulnerability_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        stubbed_request.session.flash.assert_called_once_with(
            "Please confirm the vulnerability id 'PYSEC-1' to delete.",
            queue="error",
        )
        assert (
            stubbed_request.db.query(VulnerabilityRecord)
            .filter_by(source=vuln.source, id=vuln.id)
            .one_or_none()
            is not None
        )

    def test_deletes_record_and_associations(self, stubbed_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        vuln = VulnerabilityRecordFactory.create(
            source="osv", id="PYSEC-1", releases=[release]
        )

        stubbed_request.matchdict = {"source": vuln.source, "id": vuln.id}
        stubbed_request.POST = {"confirm": vuln.id}

        result = views.vulnerability_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        stubbed_request.db.flush()
        assert (
            stubbed_request.db.query(VulnerabilityRecord)
            .filter_by(source=vuln.source, id=vuln.id)
            .one_or_none()
            is None
        )
        assert (
            stubbed_request.db.query(ReleaseVulnerability)
            .filter_by(vulnerability_source=vuln.source, vulnerability_id=vuln.id)
            .count()
            == 0
        )


class TestVulnerabilityBulkDelete:
    def test_missing_filter(self, stubbed_request):
        stubbed_request.POST = {"q": "", "confirm": ""}

        result = views.vulnerability_bulk_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        stubbed_request.session.flash.assert_called_once_with(
            "Provide a filter to bulk delete vulnerabilities.",
            queue="error",
        )

    def test_confirmation_mismatch(self, stubbed_request):
        stubbed_request.db.query(VulnerabilityRecord).delete()
        VulnerabilityRecordFactory.create(source="osv", id="ECHO-1", releases=[])
        stubbed_request.POST = {"q": "ECHO%", "confirm": "echo%"}

        result = views.vulnerability_bulk_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        stubbed_request.session.flash.assert_called_once_with(
            "Confirmation did not match the filter. No vulnerabilities were deleted.",
            queue="error",
        )
        assert stubbed_request.db.query(VulnerabilityRecord).count() == 1

    def test_over_limit_refuses(self, stubbed_request, monkeypatch):
        stubbed_request.db.query(VulnerabilityRecord).delete()
        for i in range(3):
            VulnerabilityRecordFactory.create(source="osv", id=f"ECHO-{i}", releases=[])
        monkeypatch.setattr(views, "BULK_DELETE_LIMIT", 2)

        stubbed_request.POST = {"q": "ECHO%", "confirm": "ECHO%"}

        result = views.vulnerability_bulk_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        assert stubbed_request.db.query(VulnerabilityRecord).count() == 3
        stubbed_request.session.flash.assert_called_once_with(
            "Filter matches 3 records (limit 2). Refine the filter.",
            queue="error",
        )

    def test_deletes_matching(self, stubbed_request):
        stubbed_request.db.query(VulnerabilityRecord).delete()
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        VulnerabilityRecordFactory.create(source="osv", id="ECHO-1", releases=[release])
        VulnerabilityRecordFactory.create(source="osv", id="ECHO-2", releases=[])
        VulnerabilityRecordFactory.create(source="osv", id="PYSEC-1", releases=[])

        stubbed_request.POST = {"q": "ECHO%", "confirm": "ECHO%"}

        result = views.vulnerability_bulk_delete(stubbed_request)

        assert isinstance(result, HTTPSeeOther)
        stubbed_request.db.flush()
        assert [v.id for v in stubbed_request.db.query(VulnerabilityRecord).all()] == [
            "PYSEC-1"
        ]
        assert stubbed_request.db.query(ReleaseVulnerability).count() == 0
        stubbed_request.session.flash.assert_called_once_with(
            "Deleted 2 vulnerability record(s) matching 'ECHO%'.",
            queue="success",
        )
