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
"""
refactor_subscription_customer_id

Revision ID: 5cc657b6cbfb
Revises: 339bc2ea24fc
Create Date: 2022-07-23 18:50:51.444398
"""

import sqlalchemy as sa

from alembic import op

revision = "5cc657b6cbfb"
down_revision = "339bc2ea24fc"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.
#
#       By default, migrations cannot wait more than 4s on acquiring a lock
#       and each individual statement cannot take more than 5s. This helps
#       prevent situations where a slow migration takes the entire site down.
#
#       If you need to increase this timeout for a migration, you can do so
#       by adding:
#
#           op.execute("SET statement_timeout = 5000")
#           op.execute("SET lock_timeout = 4000")
#
#       To whatever values are reasonable for this migration as part of your
#       migration.


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("organizations", sa.Column("customer_id", sa.Text(), nullable=True))
    op.create_unique_constraint(None, "organizations", ["customer_id"])
    op.create_foreign_key(
        None,
        "subscriptions",
        "organizations",
        ["customer_id"],
        ["customer_id"],
        onupdate="CASCADE",
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, "subscriptions", type_="foreignkey")
    op.drop_constraint(None, "organizations", type_="unique")
    op.drop_column("organizations", "customer_id")
    # ### end Alembic commands ###
