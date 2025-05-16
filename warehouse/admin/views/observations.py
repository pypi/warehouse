# SPDX-License-Identifier: Apache-2.0

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
