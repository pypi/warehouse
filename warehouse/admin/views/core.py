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

from pyramid.view import view_config
from sqlalchemy import func

from warehouse.authnz import Permissions
from warehouse.observations.models import Observation, ObservationKind


@view_config(
    route_name="admin.dashboard",
    renderer="admin/dashboard.html",
    permission=Permissions.AdminDashboardRead,
    uses_session=True,
)
def dashboard(request):
    if request.has_permission(Permissions.AdminObservationsRead):
        # Count how many Malware Project Observations are in the database
        malware_reports_count = (
            request.db.query(func.count(Observation.id)).filter(
                Observation.kind == ObservationKind.IsMalware.value[0],
                Observation.related_id.is_not(None),  # Project is not removed
                Observation.actions == {},  # No actions have been taken
            )
        ).scalar()
    else:
        malware_reports_count = None

    return {"malware_reports_count": malware_reports_count}
