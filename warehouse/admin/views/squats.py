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

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.view import view_config

from warehouse.admin.squats import Squat


@view_config(
    route_name="admin.squats",
    renderer="admin/squats/index.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_squats(request):
    return {
        "squats": (
            request.db.query(Squat)
            .filter(Squat.reviewed.is_(False))
            .order_by(Squat.created.desc())
            .all()
        )
    }


@view_config(
    route_name="admin.squats.review",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
    require_csrf=True,
)
def review_squat(request):
    squat = request.db.query(Squat).get(request.POST["id"])
    squat.reviewed = True

    request.session.flash("Squat marked as reviewed")

    return HTTPSeeOther(request.route_path("admin.squats"))
