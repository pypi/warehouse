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

import datetime

from warehouse import tasks
from warehouse.accounts.models import User
from warehouse.packaging.models import Role, JournalEntry


@tasks.task(ignore_result=True, acks_late=True)
def prune_unused_users(request):
    # We're going to delete any user that matches the following criteria:
    #
    #   - Is not active (e.g. has never verified an email address)
    #   - Joined more than 90 days ago.
    #   - Has never been added to a project.
    #   - Has never released any project.
    #
    # These users effectively add nothing to PyPI. They have never activated their
    # account, they have never released anything to PyPI nor even been added to a
    # project. The bulk of these are spam accounts that were registered or are emphereal
    # auto generated accounts.
    (
        request.db.query(User)
        .filter(User.is_active == False)  # noqa
        .filter(
            User.date_joined
            < (datetime.datetime.utcnow() - datetime.timedelta(days=90))
        )
        .filter(
            ~request.db.query(Role).filter(Role.user_name == User.username).exists()
        )
        .filter(
            ~request.db.query(JournalEntry)
            .filter(JournalEntry._submitted_by == User.username)
            .exists()
        )
        .delete(synchronize_session=False)
    )
