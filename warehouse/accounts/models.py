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
import re

from django.core import validators
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.models import (
                                    AbstractBaseUser,
                                    BaseUserManager,
                                    PermissionsMixin,
                                )

from warehouse import accounts
from warehouse.accounts import adapters
from warehouse.utils.db_fields import CaseInsensitiveCharField


class UserManager(BaseUserManager):

    def create_user(self, username, password=None, **extra_fields):
        """
        Creates and saves a User with the given username, and password.
        """
        if not username:
            raise ValueError("The given username must be set")

        now = timezone.now()
        user = self.model(
                    username=username,
                    is_staff=False,
                    is_active=True,
                    is_superuser=False,
                    last_login=now,
                    date_joined=now,
                    **extra_fields
                )
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, username, password, **extra_fields):
        u = self.create_user(username, password, **extra_fields)
        u.is_staff = True
        u.is_active = True
        u.is_superuser = True
        u.save(using=self._db)
        return u


class User(AbstractBaseUser, PermissionsMixin):

    # There is a CHECK CONSTRAINT on User that ensures that User.username
    # is a valid username. It checks that:
    # - username begins and ends with ASCII letter or digit
    # - username contains only ASCII letters, digits, periods, hyphens, and
    # underscores

    USERNAME_FIELD = "username"

    username = CaseInsensitiveCharField(_("username"),
                    max_length=50,
                    unique=True,
                    help_text=accounts.VALID_USERNAME_DESC,
                    validators=[
                        validators.RegexValidator(
                            accounts.VALID_USERNAME_REGEX,
                            accounts.INVALID_USERNAME_MSG,
                            "invalid",
                        ),
                    ],
                )

    name = models.CharField(_("name"), max_length=100, blank=True)

    is_staff = models.BooleanField(_("staff status"),
                    default=False,
                    help_text=_("Designates whether the user can log into this"
                                " admin site."),
                )
    is_active = models.BooleanField(_("active"),
                    default=True,
                    help_text=_("Designates whether this user should be "
                                "treated as active. Unselect this instead of "
                                "deleting accounts."),
                )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    objects = UserManager()
    api = adapters.UserAdapter()

    @property
    def email(self):
        emails = self.emails.filter(primary=True, verified=True)[:1]
        if emails:
            return emails[0].email

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def get_full_name(self):
        return self.name or self.username

    def get_short_name(self):
        return self.name or self.username


class Email(models.Model):

    user = models.ForeignKey(User,
                verbose_name=_("user"),
                related_name="emails",
            )
    email = models.EmailField(_("email"), max_length=254, unique=True)
    primary = models.BooleanField(_("primary"), default=False)
    verified = models.BooleanField(_("verified"), default=False)

    api = adapters.EmailAdapter(user=User)

    class Meta:
        verbose_name = _("email")
        verbose_name_plural = _("emails")


class GPGKey(models.Model):

    # There is a CHECK CONSTRAINT on GPGKey that ensures that GPGKey.key_id
    # is a valid short key id. It checks that:
    # - key_id is exactly 8 characters in length (Short ID)
    # - key_id contains only valid characters for a Short ID

    user = models.ForeignKey(User,
                verbose_name=_("user"),
                related_name="gpg_keys",
            )
    key_id = CaseInsensitiveCharField(_("Key ID"),
                    max_length=8,
                    unique=True,
                    validators=[
                        validators.RegexValidator(
                            re.compile(r"^[A-F0-9]{8}$", re.I),
                            _("Key ID must contain a valid short identifier"),
                            "invalid",
                        ),
                    ],
                )
    verified = models.BooleanField(_("Verified"), default=False)

    class Meta:
        verbose_name = _("GPG Key")
        verbose_name_plural = _("GPG Keys")
