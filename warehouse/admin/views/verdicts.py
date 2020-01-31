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

from warehouse.malware.models import (
    MalwareCheck,
    MalwareVerdict,
    VerdictClassification,
    VerdictConfidence,
)
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.verdicts.list",
    renderer="admin/malware/verdicts/index.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def get_verdicts(request):
    result = {}
    result["check_names"] = set(
        [name for (name,) in request.db.query(MalwareCheck.name)]
    )
    result["classifications"] = set([c.value for c in VerdictClassification])
    result["confidences"] = set([c.value for c in VerdictConfidence])

    validate_fields(request, result)

    result["verdicts"] = SQLAlchemyORMPage(
        generate_query(request.db, request.params),
        page=int(request.params.get("page", 1)),
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return result


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


def validate_fields(request, validators):
    try:
        int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    validators = {**validators, **{"manually_revieweds": set(["0", "1"])}}

    for key, possible_values in validators.items():
        # Remove the trailing 's'
        value = request.params.get(key[:-1])
        additional_values = set([None, ""])
        if value not in possible_values | additional_values:
            raise HTTPBadRequest(
                "Invalid value for '%s': %s." % (key[:-1], value)
            ) from None


def generate_query(db, params):
    """
    Returns an SQLAlchemy query wth request params applied as filters.
    """
    query = db.query(MalwareVerdict)
    if params.get("check_name"):
        query = query.join(MalwareCheck)
        query = query.filter(MalwareCheck.name == params["check_name"])
    if params.get("confidence"):
        query = query.filter(MalwareVerdict.confidence == params["confidence"])
    if params.get("classification"):
        query = query.filter(MalwareVerdict.classification == params["classification"])
    if params.get("manually_reviewed") is not None:
        query = query.filter(
            MalwareVerdict.manually_reviewed == bool(int(params["manually_reviewed"]))
        )

    return query.order_by(MalwareVerdict.run_date.desc())
