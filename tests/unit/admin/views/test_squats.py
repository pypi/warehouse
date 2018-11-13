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

from warehouse.admin.squats import Squat
from warehouse.admin.views import squats as views

from ....common.db.packaging import ProjectFactory


class TestGetSquats:
    def test_get_squats(self, db_request):
        project_a = ProjectFactory()
        project_b = ProjectFactory()
        project_c = ProjectFactory()
        squat = Squat(squattee=project_a, squatter=project_b)
        reviewed_squat = Squat(squattee=project_a, squatter=project_c, reviewed=True)
        db_request.db.add(squat)
        db_request.db.add(reviewed_squat)

        assert views.get_squats(db_request) == {"squats": [squat]}


class TestReviewSquat:
    def test_review_squat(self, db_request):
        squat = Squat(squattee=ProjectFactory(), squatter=ProjectFactory())
        db_request.db.add(squat)

        db_request.db.flush()

        db_request.POST = {"id": squat.id}
        db_request.route_path = lambda *a: "/the/redirect"
        db_request.flash = lambda *a: None

        views.review_squat(db_request)

        db_request.db.flush()

        assert squat.reviewed is True
