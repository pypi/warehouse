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

"""Admin Views related to Observations"""

from collections import defaultdict

from pyramid.view import view_config

from warehouse.authnz import Permissions
from warehouse.observations.models import Observation


@view_config(
    route_name="admin.observations.list",
    renderer="admin/observations/list.html",
    permission=Permissions.AdminObservationsRead,
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def observations_list(request):
    """
    List all Observations.

    TODO: Should we filter server-side by `kind`, or in the template?
     Currently the server returns all observations, and then we group them by kind
     for display in the template.

    TODO: Paginate this view, not worthwhile just yet.
    """

    observations = (
        request.db.query(Observation).order_by(Observation.created.desc()).all()
    )

    # Group observations by kind
    grouped_observations = defaultdict(list)
    for observation in observations:
        grouped_observations[observation.kind].append(observation)

    return {"kind_groups": grouped_observations}
