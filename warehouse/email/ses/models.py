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

import enum

import automat

from sqlalchemy import sql, orm
from sqlalchemy import Boolean, Column, Enum, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm.session import object_session

from warehouse import db
from warehouse.accounts.models import Email as EmailAddress, UnverifyReasons


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
        A recipient can complain about our emaill :(
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

    accepted.upon(deliver, enter=delivered, outputs=[_reset_transient_bounce],
                  collector=lambda iterable: list(iterable)[-1])
    accepted.upon(bounce, enter=bounced,
                  outputs=[_reset_transient_bounce, _handle_bounce],
                  collector=lambda iterable: list(iterable)[-1])
    accepted.upon(soft_bounce, enter=soft_bounced,
                  outputs=[_incr_transient_bounce],
                  collector=lambda iterable: list(iterable)[-1])

    # This is an OOTO response, it's techincally a bounce, but we don't
    # really want to treat this as a bounce. We'll record the event
    # for posterity though.
    delivered.upon(soft_bounce, enter=delivered, outputs=[])
    delivered.upon(bounce, enter=bounced,
                   outputs=[_reset_transient_bounce, _handle_bounce],
                   collector=lambda iterable: list(iterable)[-1])
    delivered.upon(complain, enter=complained, outputs=[_handle_complaint],
                   collector=lambda iterable: list(iterable)[-1])

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

        db = object_session(self._email_message)
        email = (db.query(EmailAddress)
                   .filter(EmailAddress.email == self._email_message.to)
                   .first())

        # If our email is None, then we'll mark our log so that when we're
        # viewing the log, we can tell that it wasn't recorded.
        if email is None:
            self._email_message.missing = True

        return email


class EmailMessage(db.Model):

    __tablename__ = "ses_emails"

    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    status = Column(
        Enum(EmailStatuses, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=EmailStatuses.Accepted.value,
    )

    message_id = Column(Text, nullable=False, unique=True, index=True)
    from_ = Column("from", Text, nullable=False)
    to = Column(Text, nullable=False, index=True)
    subject = Column(Text, nullable=False)
    missing = Column(Boolean, nullable=False, server_default=sql.false())

    # Relationships!
    events = orm.relationship(
        "Event",
        backref="email",
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

    created = Column(DateTime, nullable=False, server_default=sql.func.now())

    email_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ses_emails.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )

    event_id = Column(Text, nullable=False, unique=True, index=True)
    event_type = Column(
        Enum(EventTypes, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    data = Column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        server_default=sql.text("'{}'"),
    )
