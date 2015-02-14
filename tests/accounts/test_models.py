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

from warehouse.accounts.models import User

from ..common.db.accounts import UserFactory, EmailFactory


class TestUser:

    def test_get_primary_email_when_no_emails(self, db_session):
        user = UserFactory.create(session=db_session)
        assert user.email is None

    def test_get_primary_email(self, db_session):
        user = UserFactory.create(session=db_session)
        email = EmailFactory.create(
            user=user, primary=True, session=db_session,
        )
        EmailFactory.create(user=user, primary=False, session=db_session)

        assert user.email == email.email

    def test_query_by_email_when_primary(self, db_session):
        user = UserFactory.create(session=db_session)
        email = EmailFactory.create(
            user=user, primary=True, session=db_session,
        )

        result = db_session.query(User).filter(
            User.email == email.email
        ).first()

        assert result == user

    def test_query_by_email_when_not_primary(self, db_session):
        user = UserFactory.create(session=db_session)
        email = EmailFactory.create(
            user=user, primary=False, session=db_session,
        )

        result = db_session.query(User).filter(
            User.email == email.email
        ).first()

        assert result is None
