# SPDX-License-Identifier: Apache-2.0

"""
A gated release is not installable.

These go through the real read paths an installer uses, the Simple index and
the JSON API, rather than asserting on the gate rows.
"""

import pretend
import pytest

from pyramid.httpexceptions import HTTPNotFound

from warehouse.legacy.api import json as json_api
from warehouse.packaging import views as packaging_views
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.tasks import (
    check_file_cache_tasks_outstanding,
    reconcile_file_storages,
    sync_file_to_cache,
)
from warehouse.packaging.utils import _simple_detail

from ...common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


def _register_storages(pyramid_services):
    """`reconcile_file_storages` resolves both named file storages up front."""
    for name in ("cache", "archive"):
        pyramid_services.register_service(pretend.stub(), IFileStorage, None, name=name)


@pytest.fixture
def routed_request(db_request):
    """`_simple_detail` and `_json_data` build file URLs via `route_url`."""
    db_request.route_url = lambda *a, **kw: "the-url"
    return db_request


class TestSimpleIndex:
    def test_ungated_release_is_listed(self, routed_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, gated=False)
        file_ = FileFactory.create(release=release)

        context = _simple_detail(project, routed_request)

        assert context["versions"] == [release.version]
        assert [f["filename"] for f in context["files"]] == [file_.filename]

    def test_gated_release_is_absent(self, routed_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, gated=True)
        FileFactory.create(release=release)

        context = _simple_detail(project, routed_request)

        assert context["versions"] == []
        assert context["files"] == []

    def test_gating_one_release_leaves_the_others(self, routed_request):
        project = ProjectFactory.create()
        published = ReleaseFactory.create(project=project, version="1.0", gated=False)
        FileFactory.create(release=published)
        withheld = ReleaseFactory.create(project=project, version="2.0", gated=True)
        FileFactory.create(release=withheld)

        context = _simple_detail(project, routed_request)

        assert context["versions"] == ["1.0"]


class TestJSONAPI:
    def test_gated_release_is_absent_from_the_project_payload(self, routed_request):
        project = ProjectFactory.create()
        published = ReleaseFactory.create(project=project, version="1.0", gated=False)
        FileFactory.create(release=published)
        withheld = ReleaseFactory.create(project=project, version="2.0", gated=True)
        FileFactory.create(release=withheld)

        data = json_api._json_data(
            routed_request, project, published, all_releases=True
        )

        assert "2.0" not in data["releases"]
        assert "1.0" in data["releases"]

    def test_gated_release_cannot_become_latest(self, db_request):
        project = ProjectFactory.create()
        published = ReleaseFactory.create(project=project, version="1.0", gated=False)
        FileFactory.create(release=published)
        newer = ReleaseFactory.create(project=project, version="2.0", gated=True)
        FileFactory.create(release=newer)

        db_request.matchdict = {"name": project.normalized_name}

        latest = json_api.latest_release_factory(db_request)

        assert latest.version == "1.0"

    def test_project_with_only_a_gated_release_is_not_found(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, gated=True)
        FileFactory.create(release=release)

        db_request.matchdict = {"name": project.normalized_name}

        assert isinstance(json_api.latest_release_factory(db_request), HTTPNotFound)


class TestArtifactAvailability:
    """
    Gating withholds a release from the Simple index and the JSON API, but its
    files are still synced to the cache bucket so the artifact stays fetchable
    by its URL (for example, for an authorized security scanner).
    """

    def test_sync_copies_a_gated_file(self, db_request, monkeypatch):
        release = ReleaseFactory.create(gated=True)
        file_ = FileFactory.create(
            release=release, cached=False, metadata_file_sha256_digest=None
        )

        copy = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr("warehouse.packaging.tasks._copy_file_to_cache", copy)
        monkeypatch.setattr(db_request, "find_service", lambda *a, **kw: pretend.stub())

        sync_file_to_cache(db_request, file_.id)

        assert len(copy.calls) == 1
        assert file_.cached is True

    def test_sync_copies_an_ungated_file(self, db_request, monkeypatch):
        release = ReleaseFactory.create(gated=False)
        file_ = FileFactory.create(
            release=release, cached=False, metadata_file_sha256_digest=None
        )

        copy = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr("warehouse.packaging.tasks._copy_file_to_cache", copy)
        monkeypatch.setattr(db_request, "find_service", lambda *a, **kw: pretend.stub())

        sync_file_to_cache(db_request, file_.id)

        assert len(copy.calls) == 1
        assert file_.cached is True

    def test_reconcile_checks_gated_files(
        self, db_request, pyramid_services, monkeypatch
    ):
        """A gated file is cached like any other, so the sweep still checks it."""
        release = ReleaseFactory.create(gated=True)
        file_ = FileFactory.create(
            release=release, cached=False, metadata_file_sha256_digest=None
        )

        _register_storages(pyramid_services)
        db_request.registry.settings = {"reconcile_file_storages.batch_size": 100}
        checked = pretend.call_recorder(
            lambda storage, f: pretend.stub(file=f.size, metadata_file=None)
        )
        monkeypatch.setattr("warehouse.packaging.tasks.fetch_sizes", checked)

        reconcile_file_storages(db_request)

        assert [c.args[1] for c in checked.calls] == [file_, file_]

    def test_reconcile_still_checks_ungated_files(
        self, db_request, pyramid_services, monkeypatch
    ):
        release = ReleaseFactory.create(gated=False)
        file_ = FileFactory.create(
            release=release, cached=False, metadata_file_sha256_digest=None
        )

        _register_storages(pyramid_services)
        db_request.registry.settings = {"reconcile_file_storages.batch_size": 100}
        checked = pretend.call_recorder(
            lambda storage, f: pretend.stub(file=f.size, metadata_file=None)
        )
        monkeypatch.setattr("warehouse.packaging.tasks.fetch_sizes", checked)

        reconcile_file_storages(db_request)

        assert [c.args[1] for c in checked.calls] == [file_, file_]

    def test_cache_gauge_counts_gated_files(self, db_request, metrics):
        """Gated files are expected to be cached, so the gauge counts them too."""
        gated = ReleaseFactory.create(gated=True)
        FileFactory.create(release=gated, cached=False)
        ungated = ReleaseFactory.create(gated=False)
        FileFactory.create(release=ungated, cached=False)

        check_file_cache_tasks_outstanding(db_request)

        assert (
            pretend.call("warehouse.packaging.files.not_cached", 2)
            in metrics.gauge.calls
        )


class TestWebUI:
    """A gated release is hidden from the project page and its version page."""

    def test_project_detail_skips_a_gated_release(self, db_request, mocker):
        project = ProjectFactory.create()
        published = ReleaseFactory.create(project=project, version="1.0", gated=False)
        ReleaseFactory.create(project=project, version="2.0", gated=True)
        inner = mocker.patch.object(
            packaging_views,
            "release_detail",
            autospec=True,
            return_value=mocker.sentinel.response,
        )

        resp = packaging_views.project_detail(project, db_request)

        assert resp is mocker.sentinel.response
        inner.assert_called_once_with(published, db_request)

    def test_project_detail_with_only_a_gated_release_is_not_found(self, db_request):
        project = ProjectFactory.create()
        ReleaseFactory.create(project=project, gated=True)

        with pytest.raises(HTTPNotFound):
            packaging_views.project_detail(project, db_request)

    def test_release_detail_404s_a_gated_release(self, db_request):
        release = ReleaseFactory.create(gated=True)

        with pytest.raises(HTTPNotFound):
            packaging_views.release_detail(release, db_request)

    def test_all_versions_excludes_gated(self, db_request):
        project = ProjectFactory.create()
        ReleaseFactory.create(project=project, version="1.0", gated=False)
        ReleaseFactory.create(project=project, version="2.0", gated=True)

        assert [row.version for row in project.all_versions] == ["1.0"]

    def test_latest_version_excludes_gated(self, db_request):
        project = ProjectFactory.create()
        ReleaseFactory.create(project=project, version="1.0", gated=False)
        ReleaseFactory.create(project=project, version="2.0", gated=True)

        assert project.latest_version.version == "1.0"
