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

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.malware.models import MalwareCheck, MalwareCheckState


@view_config(
    route_name="admin.checks.list",
    renderer="admin/malware/checks/index.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_checks(request):
    all_checks = request.db.query(MalwareCheck).all()
    active_checks = []
    for check in all_checks:
        if not check.is_stale:
            active_checks.append(check)

    return {"checks": active_checks}


@view_config(
    route_name="admin.checks.detail",
    renderer="admin/malware/checks/detail.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_check(request):
    query = (
        request.db.query(MalwareCheck)
        .filter(MalwareCheck.name == request.matchdict["check_name"])
        .order_by(MalwareCheck.version.desc())
    )

    try:
        # Throw an exception if and only if no results are returned.
        newest = query.limit(1).one()
    except NoResultFound:
        raise HTTPNotFound

    return {"check": newest, "checks": query.all(), "states": MalwareCheckState}


@view_config(
    route_name="admin.checks.change_state",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def change_check_state(request):
    try:
        check = (
            request.db.query(MalwareCheck)
            .filter(MalwareCheck.id == request.POST["id"])
            .one()
        )
    except NoResultFound:
        raise HTTPNotFound

    try:
        check.state = getattr(MalwareCheckState, request.POST["check_state"])
    except (AttributeError, KeyError):
        request.session.flash("Invalid check state provided.", queue="error")
    else:
        request.session.flash(
            f"Changed {check.name!r} check to {check.state.value!r}!", queue="success"
        )
    finally:
        return HTTPSeeOther(
            request.route_path("admin.checks.detail", check_name=check.name)
        )
