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

from sqlalchemy import Column, DateTime, Integer, Text

from warehouse import db


@enum.unique
class RoleName(enum.Enum):

    Root = "root"
    Snapshot = "snapshot"
    Targets = "targets"
    Timestamp = "timestamp"


class VersionMixin:

    version = Column(Integer, nullable=False, unique=True)


class ExpirationMixin:

    expiration_date = Column(DateTime, nullable=False)


class KeyIDMixin:

    keyid = Column(Text, nullable=False)


class Root(VersionMixin, ExpirationMixin, db.Model):

    __tablename__ = "tuf_roots"

    # keys

    # roles


class Snapshot(VersionMixin, ExpirationMixin, db.Model):

    __tablename__ = "tuf_snapshots"

    # TODO: 1-1 relationshup to targets, via targets.version


class Targets(VersionMixin, ExpirationMixin, db.Model):

    __tablename__ = "tuf_targets"


# A new Timestamp is created every time a file is uploaded, or every day at minimum.
# The timestamp references the most recently created snapshot.


class Timestamp(ExpirationMixin, db.Model):

    __tablename__ = "tuf_timestamps"

    # TODO: 1-1 relationship to snapshot, via snapshot.version


# TODO(ww): Models for delegated targets (bins and bin-ns).
