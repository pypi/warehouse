# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import collections

from django.db import transaction
from django.utils import timezone

from warehouse.adapters import BaseAdapter


User = collections.namedtuple("User", ["username"])
Email = collections.namedtuple("Email",
            ["user", "email", "primary", "verified"],
        )


class UserAdapter(BaseAdapter):

    def _serialize(self, db_user):
        return User(
                    username=db_user.username,
                )

    def create(self, username, password=None):
        if not username:
            raise ValueError("The given username must be set")

        # Create the user in the Database
        now = timezone.now()
        db_user = self.model(
                    username=username,
                    is_staff=False,
                    is_active=True,
                    is_superuser=False,
                    last_login=now,
                    date_joined=now,
                )
        db_user.set_password(password)
        db_user.save()

        # Serialize the db user
        return self._serialize(db_user)

    def username_exists(self, username):
        return self.model.objects.filter(username=username).exists()


class EmailAdapter(BaseAdapter):

    def __init__(self, *args, **kwargs):
        self.User = kwargs.pop("user")
        super(EmailAdapter, self).__init__(*args, **kwargs)

    def _serialize(self, db_email):
        return Email(
                    user=db_email.user.username,
                    email=db_email.email,
                    primary=db_email.primary,
                    verified=db_email.verified,
                )

    def create(self, username, address, primary=False, verified=False):
        # Fetch the user that we need
        user = self.User.objects.get(username=username)

        # Create the email in the database
        db_email = self.model(
                        user=user,
                        email=address,
                        primary=primary,
                        verified=verified,
                    )
        db_email.save()

        return self._serialize(db_email)

    def get_user_emails(self, username):
        for email in self.model.objects.filter(
                                            user__username=username,
                                        ).select_related(
                                            "user",
                                        ).order_by("-primary", "email"):
            yield self._serialize(email)

    def set_user_primary_email(self, username, email):
        with transaction.atomic():
            self.model.objects.filter(
                    user__username=username).update(primary=False)
            updated = self.model.objects.filter(
                    user__username=username, email=email, verified=True
                ).update(primary=True)

            if not updated:
                raise ValueError("Must set a valid verified email as primary")

    def delete_user_email(self, username, email):
        self.model.objects.filter(
                user__username=username, email=email, primary=False).delete()
