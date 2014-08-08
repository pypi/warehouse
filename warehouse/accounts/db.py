# Copyright 2013 Donald Stufft
#
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
import logging

from warehouse import db
from warehouse.accounts.tables import users


logger = logging.getLogger(__name__)


class Database(db.Database):

    get_user_id = db.scalar(
        """ SELECT id
            FROM accounts_user
            WHERE username = %s
            LIMIT 1
        """
    )

    get_user_id_by_email = db.scalar(
        """ SELECT user_id
            FROM accounts_email
            WHERE email = %s
            LIMIT 1
        """
    )

    def get_user(self, username):
        query = \
            """ SELECT accounts_user.id, username, name, date_joined, email
                FROM accounts_user
                LEFT OUTER JOIN accounts_email ON (
                    accounts_email.user_id = accounts_user.id
                )
                WHERE username = %(username)s
                LIMIT 1
            """

        result = self.engine.execute(query, username=username).first()

        if result is not None:
            result = dict(result)

        return result

    def is_email_active(self, user_id):
        result = self.engine.execute(users.select(
            columns=[users.c.is_active]
        ).where(
            users.c.id == user_id
        ))
        import pdb; pdb.set_trace()


    def user_authenticate(self, username, password):
        # Get the user with the given username
        query = \
            """ SELECT password
                FROM accounts_user
                WHERE username = %(username)s
                LIMIT 1
            """

        with self.engine.begin():
            password_hash = self.engine.execute(query, username=username).\
                scalar()

            # If the user was not found, then return None
            if password_hash is None:
                return

            try:
                valid, new_hash = self.app.passlib.verify_and_update(
                    password,
                    password_hash,
                )
            except ValueError:
                logger.exception(
                    "An exception occurred attempting to validate the "
                    "password for '%s'",
                    username,
                )
                return

            if valid:
                if new_hash:
                    self.engine.execute(
                        """ UPDATE accounts_user
                            SET password = %(password)s
                            WHERE username = %(username)s
                        """,
                        password=new_hash,
                        username=username,
                    )
                return True

# data modification methods

    def insert_user(self, username, email, password,
                    is_superuser=False, is_staff=False, is_active=False):
        if self.get_user_id_by_email(email) is not None:
            raise ValueError(
                "Email address already belongs to a different user!"
            )
        hashed_password = self.app.passlib.encrypt(password)

        query = \
            """ INSERT INTO accounts_user(
                    username, password,
                    last_login, is_superuser,
                    name, is_staff, date_joined, is_active
                ) VALUES (
                    %(username)s, %(password)s,
                    current_timestamp, %(is_superuser)s,
                    '', %(is_staff)s, current_timestamp, %(is_active)s
                ) RETURNING id
            """
        # Insert the actual row into the user table
        user_id = self.engine.execute(
            query,
            username=username,
            password=hashed_password,
            is_superuser=str(is_superuser).upper(),
            is_staff=str(is_staff).upper(),
            is_active=str(is_active).upper()
        ).scalar()
        self.update_user(user_id, email=email)
        return user_id

    def update_user(self, user_id, password=None, email=None):
        if password is not None:
            self.update_user_password(user_id, password)
        if email is not None:
            self.update_user_email(user_id, email)

    def delete_user(self, username):
        self.engine.execute(
            "DELETE FROM accounts_user WHERE username = %s",
            username
        )

    def activate_user_by_email(self, email):
        user_id = self.get_user_id_by_email(email)

        if user_id is None:
            raise ValueError(
                "Email {0} is not linked to an account!".format(email))

        self.engine.execute(users.update().where(
            users.c.id == user_id
        ).values(
            is_active=True
        ))

    def update_user_password(self, user_id, password):
        query = \
            """ UPDATE accounts_user
                SET password = %s
                WHERE id = %s
            """
        hashed_password = self.app.passlib.encrypt(password)
        self.engine.execute(query, hashed_password, user_id)

    def update_user_email(self, user_id, email):
        query = \
            """ WITH new_values (user_id, email, "primary", verified) AS (
                VALUES
                    (%(user_id)s, %(email)s, TRUE, FALSE)
                ),
                UPSERT AS (
                    UPDATE accounts_email ae
                        set email = nv.email,
                        verified = nv.verified
                    FROM new_values nv
                    WHERE ae.user_id = nv.user_id
                    AND ae.primary = nv.primary
                    RETURNING ae.*
                )
                INSERT INTO accounts_email
                    (user_id, email, "primary", verified)
                SELECT user_id, email, "primary", verified
                FROM new_values
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM upsert up
                    WHERE up.user_id = new_values.user_id
                    AND up.primary = new_values.primary
        )"""
        trans = self.engine.begin()
        self.engine.execute(query, user_id=user_id, email=email)
        trans.commit()
