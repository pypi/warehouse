# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pretend
import pytest

from pyramid.httpexceptions import HTTPTemporaryRedirect, HTTPNotFound

from warehouse.legacy.views import file_redirect

from ...common.db.packaging import ProjectFactory, ReleaseFactory, FileFactory


class TestFileRedirect:

    def test_404_if_letter_and_name_not_match(self):
        request = pretend.stub(matchdict={"path": "source/a/foo/foo-1.0.zip"})
        resp = file_redirect(request)

        assert isinstance(resp, HTTPNotFound)

    @pytest.mark.parametrize(
        "path",
        [
            "source/f/foo/foo-1.0.tar.gz",
            "source/f/foo/foo-1.0.tar.gz.asc",
        ],
    )
    def test_doesnt_find_nonexistent_file(self, db_request, path):
        db_request.matchdict["path"] = path
        resp = file_redirect(db_request)

        assert isinstance(resp, HTTPNotFound)

    @pytest.mark.parametrize("with_signature", [True, False])
    def test_redirects_to_real_file_url(self, db_request, with_signature):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
            size=27,
            has_signature=with_signature,
        )

        expected_filename = (
            file_.filename if not with_signature else file_.filename + ".asc"
        )
        db_request.matchdict["path"] = "source/{}/{}/{}".format(
            project.name[0],
            project.name,
            expected_filename,
        )

        @pretend.call_recorder
        def route_path(name, path):
            path = "/packages/ab/ab/thisisahash/" + file_.filename
            if with_signature:
                path += ".asc"
            return path

        db_request.route_path = route_path

        resp = file_redirect(db_request)

        assert isinstance(resp, HTTPTemporaryRedirect)
        assert resp.headers["Location"] == \
            "/packages/ab/ab/thisisahash/" + expected_filename
        assert route_path.calls == [
            pretend.call(
                "packaging.file",
                path=(file_.path if not with_signature else file_.pgp_path),
            ),
        ]

    def test_404_with_existing_file_no_signature(self, db_request):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project)
        file_ = FileFactory.create(
            release=release,
            filename="{}-{}.tar.gz".format(project.name, release.version),
            python_version="source",
            size=27,
            has_signature=False,
        )

        db_request.matchdict["path"] = "source/{}/{}/{}".format(
            project.name[0],
            project.name,
            file_.filename + ".asc"
        )

        @pretend.call_recorder
        def route_path(name, path):
            return "/packages/ab/ab/thisisahash/" + file_.filename + ".asc"

        db_request.route_path = route_path

        resp = file_redirect(db_request)

        assert isinstance(resp, HTTPNotFound)
