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
Autoincrement trove classifier id when inserting (if id not given). 

Revision ID: ad81a3452b5d
Revises: 5b3f9e687d94
Create Date: 2017-04-04 21:00:25.205245
"""

from alembic import op

revision = 'ad81a3452b5d'
down_revision = '5b3f9e687d94'

def upgrade():
    """
    Autoincrement the trove classifier ID when a new one get inserted.
    """
    op.execute(
        """CREATE SEQUENCE trove_classifiers_seq;
           SELECT setval('trove_classifiers_seq', 
                         (SELECT max(id) from trove_classifiers)
            );
           ALTER TABLE trove_classifiers 
                ALTER COLUMN id
                SET DEFAULT nextval('trove_classifiers_seq');
           ALTER SEQUENCE trove_classifiers_seq
                OWNED BY trove_classifiers.id;
        """)


def downgrade():
    op.execute(
        """ALTER TABLE trove_classifiers
                ALTER COLUMN id SET DEFAULT 1;
           DROP SEQUENCE trove_classifiers_seq;
        """)
