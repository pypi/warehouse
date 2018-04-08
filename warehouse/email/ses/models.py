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

import automat

from sqlalchemy import sql, orm
from sqlalchemy import (
    CheckConstraint, Column, Enum, ForeignKey, ForeignKeyConstraint, Index,
    Boolean, DateTime, Integer, Float, Table, Text,
)
from sqlalchemy.dialects.postgresql import HSTORE, INET, JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict

from warehouse import db
from warehouse.accounts.models import Email as EmailAddress


MAX_TRANSIENT_BOUNCES = 5


class EmailStatus:

    _machine = automat.MethodicalMachine()

    def __init__(self, db_session):
        self._db = db_session

    # States

    @_machine.state(initial=True, serialized="Accepted")
    def accepted(self):
        """
        In this state, the email has been accepted, but nothing else.
        """

    @_machine.state(serialized="Delivered")
    def delivered(self):
        """
        In this state, the email has successfully been delivered to the
        recipient.
        """

    @_machine.state(serialized="Bounced")
    def bounced(self):
        """
        In this state, the email has bounced when delivery was attempted.
        """

    @_machine.state(serialized="Soft Bounced")
    def soft_bounced(self):
        """
        In this state, the email soft bounced, we can continue sending email
        to this address.
        """

    @_machine.state(serialized="Complained")
    def complained(self):
        """
        In this state, the user has gotten the email, but they've complained
        that we are sending them spam.
        """

    # Inputs
    @_machine.input()
    def deliver(self, email_address):
        """
        We have received an event stating that the email has been delivered.
        """

    @_machine.input()
    def bounce(self, email_address):
        """
        Emails can bounce!
        """

    @_machine.input()
    def soft_bounce(self, email_address):
        """
        Emails can bounce, but only transiently so.
        """

    @_machine.input()
    def complain(self, email_address):
        """
        A recipient can complain about our emaill :(
        """

    # Outputs
    @_machine.output()
    def _flag_email(self, email_address):
        self._unverify_email(self._get_email(email_address))

    @_machine.output()
    def _incr_transient_bounce(self, email_address):
        email = self._get_email(email_address)
        email.transient_bounces += 1

        if email.transient_bounces > MAX_TRANSIENT_BOUNCES:
            self._unverify_email(email_address)

    @_machine.output()
    def _reset_transient_bounce(self, email_address):
        email = self._get_email(email_address)
        email.transient_bounces = 0

    # Transitions

    accepted.upon(deliver, enter=delivered, outputs=[_reset_transient_bounce],
                  collector=lambda iterable: list(iterable)[-1])
    accepted.upon(bounce, enter=bounced, outputs=[_flag_email],
                  collector=lambda iterable: list(iterable)[-1])
    accepted.upon(soft_bounce, enter=soft_bounced,
                  outputs=[_incr_transient_bounce],
                  collector=lambda iterable: list(iterable)[-1])

    # This is an OOTO response, it's techincally a bounce, but we don't
    # really want to treat this as a bounce. We'll record the event
    # for posterity though.
    delivered.upon(soft_bounce, enter=delivered, outputs=[])
    delivered.upon(complain, enter=complained, outputs=[_flag_email],
                   collector=lambda iterable: list(iterable)[-1])

    # Serialization / Deserialization

    @_machine.serializer()
    def save(self, state):
        return state

    @_machine.unserializer()
    def _restore(self, state):
        return state

    @classmethod
    def load(cls, db_session, state):
        self = cls(db_session)
        self._restore(state)
        return self

    # Helper methods
    def _get_email(self, email_address):
        return (self._db.query(EmailAddress)
                        .filter(EmailAddress.email == email_address)
                        .one())

    def _unverify_email(self, email):
        # Unverify the email, and mark why
        email.verified = False
        email.is_having_delivery_issues = True


class EmailMessage(db.Model):

    __tablename__ = "ses_emails"

    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    status = Column(
        Enum("Accepted", "Delivered", "Soft Bounced", "Bounced", "Complained"),
        nullable=False,
        server_default="Accepted",
    )

    message_id = Column(Text, nullable=False, unique=True, index=True)
    from_ = Column("from", Text, nullable=False)
    to = Column(Text, nullable=False)
    subject = Column(Text, nullable=False)

    # Relationships!
    events = orm.relationship(
        "Event",
        backref="email",
        cascade="all, delete-orphan",
        lazy=False,
        order_by=lambda: Event.created,
    )


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
        Enum("Delivery", "Bounce", "Complaint"),
        nullable=False,
    )

    data = Column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        server_default=sql.text("'{}'"),
    )
