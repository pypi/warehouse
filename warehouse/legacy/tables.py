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

# Note: Tables that exist here should not be used anywhere, they only exist
#       here for migration support with alembic. If any of these tables end up
#       being used they should be moved outside of warehouse.legacy. The goal
#       is that once the legacy PyPI code base is gone, that these tables
#       can just be deleted and a migration made to drop them from the
#       database.

from citext import CIText
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Table,
    UniqueConstraint,
    DateTime,
    Text,
)

from warehouse import db


# TODO: Once https://github.com/pypa/warehouse/issues/3632 is solved, then we
#       should be able to get rid of this table too, however keeping it around
#       for now to aid in the resolution of that issue.
rego_otk = Table(
    "rego_otk",
    db.metadata,
    Column("name", CIText(), ForeignKey("accounts_user.username", ondelete="CASCADE")),
    Column("otk", Text()),
    Column("date", DateTime(timezone=False)),
    UniqueConstraint("otk", name="rego_otk_unique"),
)


Index("rego_otk_name_idx", rego_otk.c.name)


Index("rego_otk_otk_idx", rego_otk.c.otk)
