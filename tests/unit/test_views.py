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

import datetime

import pretend
import pytest

from warehouse import views
from warehouse.views import (
    forbidden, index, httpexception_view, robotstxt, current_user_indicator,
    search,
)

from ..common.db.packaging import (
    ProjectFactory, ReleaseFactory, FileFactory,
)
from ..common.db.accounts import UserFactory


def test_httpexception_view():
    response = context = pretend.stub()
    request = pretend.stub()
    assert httpexception_view(context, request) is response


class TestForbiddenView:

    def test_logged_in_returns_exception(self):
        exc, request = pretend.stub(), pretend.stub(authenticated_userid=1)
        resp = forbidden(exc, request)
        assert resp is exc

    def test_logged_out_redirects_login(self):
        exc = pretend.stub()
        request = pretend.stub(
            authenticated_userid=None,
            path_qs="/foo/bar/?b=s",
            route_url=pretend.call_recorder(
                lambda route, _query: "/accounts/login/?next=/foo/bar/%3Fb%3Ds"
            ),
        )

        resp = forbidden(exc, request)

        assert resp.status_code == 303
        assert resp.headers["Location"] == \
            "/accounts/login/?next=/foo/bar/%3Fb%3Ds"


def test_robotstxt(pyramid_request):
    assert robotstxt(pyramid_request) == {}
    assert pyramid_request.response.content_type == "text/plain"


class TestIndex:

    def test_index(self, db_request):

        project = ProjectFactory.create()
        release1 = ReleaseFactory.create(project=project)
        release1.created = datetime.date(2011, 1, 1)
        release2 = ReleaseFactory.create(project=project)
        release2.created = datetime.date(2012, 1, 1)
        FileFactory.create(
            release=release1,
            filename="{}-{}.tar.gz".format(project.name, release1.version),
            python_version="source",
        )
        UserFactory.create()

        assert index(db_request) == {
            # assert that ordering is correct
            'latest_releases': [release2, release1],
            'top_projects': [release2],
            'num_projects': 1,
            'num_users': 3,
            'num_releases': 2,
            'num_files': 1,
        }


def test_esi_current_user_indicator():
    assert current_user_indicator(pretend.stub()) == {}


class TestSearch:

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_with_a_query(self, monkeypatch, page):
        params = {"q": "foo bar"}
        if page is not None:
            params["page"] = page
        suggest = pretend.stub()
        query = pretend.stub(
            suggest=pretend.call_recorder(lambda *a, **kw: suggest),
        )
        request = pretend.stub(
            es=pretend.stub(
                query=pretend.call_recorder(lambda *a, **kw: query),
            ),
            params=params,
        )

        page_obj = pretend.stub()
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(request) == {"page": page_obj, "term": params.get("q")}
        assert page_cls.calls == [
            pretend.call(suggest, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(request)]
        assert request.es.query.calls == [
            pretend.call(
                "multi_match",
                query="foo bar",
                fields=[
                    "name", "version", "author", "author_email", "maintainer",
                    "maintainer_email", "home_page", "license", "summary",
                    "description", "keywords", "platform", "download_url",
                ],
            ),
        ]
        assert query.suggest.calls == [
            pretend.call(
                name="name_suggestion",
                term={"field": "name"},
                text="foo bar",
            ),
        ]

    @pytest.mark.parametrize("page", [None, 1, 5])
    def test_without_a_query(self, monkeypatch, page):
        params = {}
        if page is not None:
            params["page"] = page
        query = pretend.stub()
        request = pretend.stub(
            es=pretend.stub(query=lambda: query),
            params=params,
        )

        page_obj = pretend.stub()
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "ElasticsearchPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        assert search(request) == {"page": page_obj, "term": params.get("q")}
        assert page_cls.calls == [
            pretend.call(query, url_maker=url_maker, page=page or 1),
        ]
        assert url_maker_factory.calls == [pretend.call(request)]
