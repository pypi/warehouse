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

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy import or_

from warehouse.sponsors.models import Sponsor
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.sponsor.list",
    renderer="admin/sponsors/list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def sponsor_list(request):
    sponsors = request.db.query(Sponsor).order_by(Sponsor.name).all()
    return {"sponsors": sponsors}
