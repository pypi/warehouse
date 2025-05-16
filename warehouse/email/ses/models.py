# SPDX-License-Identifier: Apache-2.0

import enum

from uuid import UUID

import automat

from sqlalchemy import Enum, ForeignKey, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.accounts.models import Email as EmailAddress, UnverifyReasons
from warehouse.utils.db import orm_session_from_obj
from warehouse.utils.db.types import bool_false, datetime_now

MAX_TRANSIENT_BOUNCES = 5


class EmailStatuses(enum.Enum):
    Accepted = "Accepted"
    Delivered = "Delivered"
    Bounced = "Bounced"
    SoftBounced = "Soft Bounced"
    Complained = "Complained"


class EmailStatus:
    _machine = automat.MethodicalMachine()

    def __init__(self, email_message):
        self._email_message = email_message

    # States

    @_machine.state(initial=True, serialized=EmailStatuses.Accepted.value)
    def accepted(self):
        """
        In this state, the email has been accepted, but nothing else.
        """

    @_machine.state(serialized=EmailStatuses.Delivered.value)
    def delivered(self):
        """
        In this state, the email has successfully been delivered to the
        recipient.
        """

    @_machine.state(serialized=EmailStatuses.Bounced.value)
    def bounced(self):
        """
        In this state, the email has bounced when delivery was attempted.
        """

    @_machine.state(serialized=EmailStatuses.SoftBounced.value)
    def soft_bounced(self):
        """
        In this state, the email soft bounced, we can continue sending email
        to this address.
        """

    @_machine.state(serialized=EmailStatuses.Complained.value)
    def complained(self):
        """
        In this state, the user has gotten the email, but they've complained
        that we are sending them spam.
        """

    # Inputs
    @_machine.input()
    def deliver(self):
        """
        We have received an event stating that the email has been delivered.
        """

    @_machine.input()
    def bounce(self):
        """
        Emails can bounce!
        """

    @_machine.input()
    def soft_bounce(self):
        """
        Emails can bounce, but only transiently so.
        """

    @_machine.input()
    def complain(self):
        """
        A recipient can complain about our email :(
        """

    # Outputs
    @_machine.output()
    def _handle_bounce(self):
        email = self._get_email()
        if email is not None:
            email.verified = False
            email.unverify_reason = UnverifyReasons.HardBounce

    @_machine.output()
    def _handle_complaint(self):
        email = self._get_email()
        if email is not None:
            email.verified = False
            email.unverify_reason = UnverifyReasons.SpamComplaint

    @_machine.output()
    def _incr_transient_bounce(self):
        email = self._get_email()
        if email is not None:
            email.transient_bounces += 1

            if email.transient_bounces > MAX_TRANSIENT_BOUNCES:
                email.verified = False
                email.unverify_reason = UnverifyReasons.SoftBounce

    @_machine.output()
    def _reset_transient_bounce(self):
        email = self._get_email()
        if email is not None:
            email.transient_bounces = 0

    # Transitions

    accepted.upon(
        deliver,
        enter=delivered,
        outputs=[_reset_transient_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )
    accepted.upon(
        bounce,
        enter=bounced,
        outputs=[_reset_transient_bounce, _handle_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )
    accepted.upon(
        soft_bounce,
        enter=soft_bounced,
        outputs=[_incr_transient_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )

    soft_bounced.upon(
        deliver,
        enter=delivered,
        outputs=[_reset_transient_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )

    # This is an OOTO response, it's technically a bounce, but we don't
    # really want to treat this as a bounce. We'll record the event
    # for posterity though.
    delivered.upon(soft_bounce, enter=delivered, outputs=[])
    # Sometimes we get delivery events twice, we just ignore them.
    delivered.upon(deliver, enter=delivered, outputs=[])
    delivered.upon(
        bounce,
        enter=bounced,
        outputs=[_reset_transient_bounce, _handle_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )
    delivered.upon(
        complain,
        enter=complained,
        outputs=[_handle_complaint],
        collector=lambda iterable: list(iterable)[-1],
    )

    # This happens sometimes. The email will stay unverfied, but this allows us
    # to record the event
    bounced.upon(
        deliver,
        enter=delivered,
        outputs=[_reset_transient_bounce],
        collector=lambda iterable: list(iterable)[-1],
    )

    # Serialization / Deserialization

    @_machine.serializer()
    def _save(self, state):
        return state

    @_machine.unserializer()
    def _restore(self, state):
        return state

    def save(self):
        self._email_message.status = EmailStatuses(self._save())
        return self._email_message

    @classmethod
    def load(cls, email_message):
        self = cls(email_message)
        self._restore(email_message.status.value)
        return self

    # Helper methods
    def _get_email(self):
        # If the email was missing previously, then we don't want subsequent
        # events to re-add it, so we'll just skip them.
        if self._email_message.missing:
            return

        session = orm_session_from_obj(self._email_message)
        email = (
            session.query(EmailAddress)
            .filter(EmailAddress.email == self._email_message.to)
            .first()
        )

        # If our email is None, then we'll mark our log so that when we're
        # viewing the log, we can tell that it wasn't recorded.
        if email is None:
            self._email_message.missing = True

        return email


class EmailMessage(db.Model):
    __tablename__ = "ses_emails"

    created: Mapped[datetime_now]
    status: Mapped[Enum] = mapped_column(
        Enum(EmailStatuses, values_callable=lambda x: [e.value for e in x]),
        server_default=EmailStatuses.Accepted.value,
    )

    message_id: Mapped[str] = mapped_column(unique=True, index=True)
    from_: Mapped[str] = mapped_column("from")
    to: Mapped[str] = mapped_column(index=True)
    subject: Mapped[str]
    missing: Mapped[bool_false]

    # Relationships!
    events: Mapped[list["Event"]] = orm.relationship(
        back_populates="email",
        cascade="all, delete-orphan",
        lazy=False,
        order_by=lambda: Event.created,
    )


class EventTypes(enum.Enum):
    Delivery = "Delivery"
    Bounce = "Bounce"
    Complaint = "Complaint"


class Event(db.Model):
    __tablename__ = "ses_events"

    created: Mapped[datetime_now]

    email_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "ses_emails.id", deferrable=True, initially="DEFERRED", ondelete="CASCADE"
        ),
        index=True,
    )
    email: Mapped[EmailMessage] = orm.relationship(
        back_populates="events",
        lazy=False,
    )

    event_id: Mapped[str] = mapped_column(unique=True, index=True)
    event_type: Mapped[Enum] = mapped_column(
        Enum(EventTypes, values_callable=lambda x: [e.value for e in x])
    )

    data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSONB()), server_default=sql.text("'{}'")
    )
