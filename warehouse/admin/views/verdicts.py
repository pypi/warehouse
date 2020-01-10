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

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from pyramid.view import view_config

from warehouse.malware.models import MalwareVerdict
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.verdicts.list",
    renderer="admin/malware/verdicts/index.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_verdicts(request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    verdicts_query = request.db.query(MalwareVerdict).order_by(
        MalwareVerdict.run_date.desc()
    )

    verdicts = SQLAlchemyORMPage(
        verdicts_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"verdicts": verdicts}


@view_config(
    route_name="admin.verdicts.detail",
    renderer="admin/malware/verdicts/detail.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_verdict(request):
    verdict = request.db.query(MalwareVerdict).get(request.matchdict["verdict_id"])

    if verdict:
        return {"verdict": verdict}

    raise HTTPNotFound
