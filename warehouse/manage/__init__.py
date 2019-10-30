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

from warehouse import db
from warehouse.accounts.models import UserEvent


@db.listens_for(db.Session, "after_flush")
def store_2fa_user_events_for_notification(config, session, flush_context):
    # We'll (ab)use the session.info dictionary to store a list of pending
    # two_factor UserEvent inserts with 2fa tags to the session.
    two_factor_additions = session.info.setdefault(
        "two_factor_additions", set()
    )
    two_factor_removals = session.info.setdefault(
        "two_factor_removals", set()
    )
    for obj in session.new:
        if obj.__class__ == UserEvent:
            if obj.tag == "account:two_factor:method_added":
                two_factor_additions.add(obj.additional['method'])
            elif obj.tag == "account:two_factor:method_removed":
                two_factor_removals.add(obj.additional['method'])


@db.listens_for(db.Session, "after_commit")
def execute_2fa_user_event_notification(config, session):
    request = session.info.get('request')
    two_factor_additions = session.info.pop("two_factor_additions", set())
    two_factor_removals = session.info.pop("two_factor_removals", set())

    from warehouse.email import send_2fa_added_email, send_2fa_removed_email

    for method in two_factor_additions:
        send_2fa_added_email(request, request.user, method=method)

    for method in two_factor_removals:
        send_2fa_removed_email(request, request.user, method=method)


def includeme(config):
    pass
