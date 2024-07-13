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

from tests.common.db.accounts import UserFactory
from warehouse.accounts.utils import UserContext
from warehouse.utils.security_policy import principals_for


def test_user_context_principals(db_request):
    user = UserFactory.create()
    assert principals_for(
        UserContext(user=user, macaroon=pretend.stub())
    ) == principals_for(user)
