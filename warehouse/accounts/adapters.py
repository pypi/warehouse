import collections

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
