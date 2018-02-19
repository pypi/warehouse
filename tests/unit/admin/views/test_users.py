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
import uuid

from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from webob.multidict import MultiDict

from warehouse.admin.views import users as views

from ....common.db.accounts import User, UserFactory, EmailFactory
from ....common.db.packaging import ProjectFactory, RoleFactory


class TestUserList:

    def test_no_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(30)],
            key=lambda u: u.username.lower(),
        )
        result = views.user_list(db_request)

        assert result == {
            "users": users[:25],
            "query": None,
        }

    def test_with_page(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(30)],
            key=lambda u: u.username.lower(),
        )
        db_request.GET["page"] = "2"
        result = views.user_list(db_request)

        assert result == {
            "users": users[25:],
            "query": None,
        }

    def test_with_invalid_page(self):
        request = pretend.stub(params={"page": "not an integer"})

        with pytest.raises(HTTPBadRequest):
            views.user_list(request)

    def test_basic_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)],
            key=lambda u: u.username.lower(),
        )
        db_request.GET["q"] = users[0].username
        result = views.user_list(db_request)

        assert result == {
            "users": [users[0]],
            "query": users[0].username,
        }

    def test_wildcard_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)],
            key=lambda u: u.username.lower(),
        )
        db_request.GET["q"] = users[0].username[:-1] + "%"
        result = views.user_list(db_request)

        assert result == {
            "users": [users[0]],
            "query": users[0].username[:-1] + "%",
        }

    def test_email_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)],
            key=lambda u: u.username.lower(),
        )
        emails = [EmailFactory.create(user=u, primary=True) for u in users]
        db_request.GET["q"] = "email:" + emails[0].email
        result = views.user_list(db_request)

        assert result == {
            "users": [users[0]],
            "query": "email:" + emails[0].email,
        }

    def test_or_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)],
            key=lambda u: u.username.lower(),
        )
        emails = [EmailFactory.create(user=u, primary=True) for u in users]
        db_request.GET["q"] = " ".join([
            users[0].username,
            users[1].username[:-1] + "%",
            "email:" + emails[2].email,
            "email:" + emails[3].email[:-5] + "%",
        ])
        result = views.user_list(db_request)

        assert result == {
            "users": users[:4],
            "query": db_request.GET["q"],
        }

    def test_ignores_invalid_query(self, db_request):
        users = sorted(
            [UserFactory.create() for _ in range(5)],
            key=lambda u: u.username.lower(),
        )
        db_request.GET["q"] = "foobar:what"
        result = views.user_list(db_request)

        assert result == {
            "users": users,
            "query": "foobar:what",
        }


class TestUserDetail:

    def test_404s_on_nonexistant_user(self, db_request):
        user = UserFactory.create()
        user_id = uuid.uuid4()
        while user.id == user_id:
            user_id = uuid.uuid4()
        db_request.matchdict["user_id"] = str(user_id)

        with pytest.raises(HTTPNotFound):
            views.user_detail(db_request)

    def test_gets_user(self, db_request):
        user = UserFactory.create()
        project = ProjectFactory.create()
        roles = sorted(
            [RoleFactory(project=project, user=user, role_name='Owner')],
        )
        db_request.matchdict["user_id"] = str(user.id)
        db_request.POST = MultiDict(db_request.POST)
        result = views.user_detail(db_request)

        assert result["user"] == user
        assert result["roles"] == roles

    def test_updates_user(self, db_request):
        user = UserFactory.create()
        db_request.matchdict["user_id"] = str(user.id)
        db_request.method = "POST"
        db_request.POST["name"] = "Jane Doe"
        db_request.POST = MultiDict(db_request.POST)
        db_request.current_route_path = pretend.call_recorder(
            lambda: "/admin/users/{}/".format(user.id)
        )

        resp = views.user_detail(db_request)

        assert resp.status_code == 303
        assert resp.location == "/admin/users/{}/".format(user.id)
        assert user.name == "Jane Doe"


class TestUserDelete:

    def test_deletes_user(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name='Owner')

        db_request.matchdict['user_id'] = str(user.id)
        db_request.params = {'username': user.username}
        db_request.route_path = pretend.call_recorder(lambda a: '/foobar')
        db_request.user = UserFactory.create()
        db_request.remote_addr = '10.10.10.10'

        remove_project = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, 'remove_project', remove_project)

        result = views.user_delete(db_request)

        db_request.db.flush()

        assert not db_request.db.query(User).get(user.id)
        assert remove_project.calls == [
            pretend.call(project, db_request, flash=False),
        ]
        assert db_request.route_path.calls == [pretend.call('admin.user.list')]
        assert result.status_code == 303
        assert result.location == '/foobar'

    def test_deletes_user_bad_confirm(self, db_request, monkeypatch):
        user = UserFactory.create()
        project = ProjectFactory.create()
        RoleFactory(project=project, user=user, role_name='Owner')

        db_request.matchdict['user_id'] = str(user.id)
        db_request.params = {'username': 'wrong'}
        db_request.route_path = pretend.call_recorder(lambda a, **k: '/foobar')

        remove_project = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, 'remove_project', remove_project)

        result = views.user_delete(db_request)

        db_request.db.flush()

        assert db_request.db.query(User).get(user.id)
        assert remove_project.calls == []
        assert db_request.route_path.calls == [
            pretend.call('admin.user.detail', user_id=user.id),
        ]
        assert result.status_code == 303
        assert result.location == '/foobar'
