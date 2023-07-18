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

from warehouse.accounts.tasks import compute_user_metrics

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory


def _create_email_project_with_release(user, verified):
    EmailFactory.create(user=user, verified=verified)
    result = ProjectFactory.create()
    ReleaseFactory.create(project=result, uploader=user)
    return result


def test_compute_user_metrics(db_request, metrics):
    # Create an active user with no email
    UserFactory.create()
    # Create an inactive user
    UserFactory.create(is_active=False)
    # Create a user with an unverified email
    unverified_email_user = UserFactory.create()
    EmailFactory.create(user=unverified_email_user, verified=False)
    # Create a user with a verified email
    verified_email_user = UserFactory.create()
    EmailFactory.create(user=verified_email_user, verified=True)
    # Create a user with a verified email and a release
    verified_email_release_user = UserFactory.create()
    _create_email_project_with_release(verified_email_release_user, verified=True)
    # Create an active user with an unverified email and a release
    unverified_email_release_user = UserFactory.create(is_active=True)
    _create_email_project_with_release(unverified_email_release_user, verified=False)
    compute_user_metrics(db_request)

    assert metrics.gauge.calls == [
        pretend.call("warehouse.users.count", 6),
        pretend.call("warehouse.users.count", 5, tags=["active:true"]),
        pretend.call(
            "warehouse.users.count", 3, tags=["active:true", "verified:false"]
        ),
        pretend.call(
            "warehouse.users.count",
            1,
            tags=["active:true", "verified:false", "releases:true"],
        ),
    ]
