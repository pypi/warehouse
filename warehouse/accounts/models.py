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

    USERNAME_FIELD = "username"

    username = CaseInsensitiveCharField(_("username"),
                    max_length=50,
                    unique=True,
                    help_text=accounts.VALID_USERNAME_DESC,
                    validators=[
                        validators.RegexValidator(
                            re.compile(accounts.VALID_USERNAME_REGEX),
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
                on_delete=models.DO_NOTHING,
            )
    email = models.EmailField(_("email"), max_length=254, unique=True)
    primary = models.BooleanField(_("primary"), default=False)
    verified = models.BooleanField(_("verified"), default=False)

    api = adapters.EmailAdapter(user=User)

    class Meta:
        verbose_name = _("email")
        verbose_name_plural = _("emails")
