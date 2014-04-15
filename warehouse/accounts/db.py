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
import random
import string
import logging

from warehouse import db


logger = logging.getLogger(__name__)

CHARS = string.ascii_letters + string.digits


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

    def get_user(self, name):
        query = \
            """ SELECT username, name, date_joined, email
                FROM accounts_user
                LEFT OUTER JOIN accounts_email ON (
                    accounts_email.user_id = accounts_user.id
                )
                WHERE username = %(username)s
                LIMIT 1
            """

        result = self.engine.execute(query, username=name).first()

        if result is not None:
            result = dict(result)

        return result

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
                    "An exception occured attempting to validate the password "
                    "for '%s'",
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

### data modification methods ###

    def insert_user(self, username, email, password, is_superuser=False,
                    is_staff=False, is_active=False,
                    gpg_keyid=None, generate_otk=False):
        if self.get_user_id_by_email(email) is not None:
            raise ValueError("Email address already belongs to a different user!")
        hashed_password = self.app.passlib.encrypt(password)

        INSERT_STATEMENT = """INSERT INTO accounts_user(
            username, password, last_login, is_superuser,
            name, is_staff, date_joined, is_active
        ) VALUES (
            %(username)s, %(password)s, current_timestamp, %(is_superuser)s,
            '', %(is_staff)s, current_timestamp, %(is_active)s
        ) RETURNING id
        """
        # Insert the actual row into the user table
        user_id = self.engine.execute(
            INSERT_STATEMENT,
            username=username,
            password=hashed_password,
            is_superuser=str(is_superuser).upper(),
            is_staff=str(is_staff).upper(),
            is_active=str(is_active).upper()
        ).scalar()
        self.update_user(user_id, email=email, gpg_keyid=gpg_keyid)
        if generate_otk:
            otk = "".join([random.choice(chars) for x in range(32)])
            return self.insert_user_otk(username, otk)

    def update_user(self, user_id, password=None, email=None,
                    gpg_keyid=None):
        if password is not None:
            self.update_user_password(user_id, password)
        if email is not None:
            self.update_user_email(user_id, email)
        if gpg_keyid is not None:
            self.delete_user_gpg_keyid(user_id)
        # if the string is empty, we don't make a new one
        if gpg_keyid:
            self.insert_user_gpg_keyid(user_id, gpg_keyid)

    def update_user_password(self, user_id, password):
        self.engine.execute("""
        UPDATE accounts_user
            SET password = %s
            WHERE id = %s
        """, password, user_id)

    def update_user_email(self, user_id, email):
        self.engine.execute("""
        WITH new_values (user_id, email, "primary", verified) AS (
            VALUES
                (%(user_id)s, %(email)s, TRUE, FALSE)
        ),
        upsert AS (
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
        )""".strip(), user_id=user_id, email=email)

    def delete_user_gpg_keyid(self, user_id):
        self.engine.execute(
            "DELETE FROM accounts_gpgkey WHERE user_id = %s",
            user_id
        )

    def insert_user_gpg_keyid(self, user_id, gpg_keyid):
        self.engine.execute(
            """
            INSERT INTO accounts_gpgey (user_id, key_id, verified)
            VALUES (%s, %s, FALSE)
            """,
            user_id, gpg_keyid
        )

    def insert_user_otk(self, username, otk):
        self.engine.execute(
            """
            INSERT INTO rego_otk (name, otk, date)
            VALUES (%s, %s, current_timestamp)
            """,
            username, otk
        )

    def get_user_otk(self, username):
        result = self.engine.execute(
            """
            SELECT otk FROM rego_otk WHERE name = %s
            """,
            username
        ).first()
        return result[0] if result else result

    def delete_user_otk(self, username):
        self.engine.execute(
            "DELETE FROM rego_otk WHERE name = %s",
            username
        )
