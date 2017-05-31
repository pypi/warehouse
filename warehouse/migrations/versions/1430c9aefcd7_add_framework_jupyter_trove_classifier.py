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
Create `Framework::Jupyter` as required on pypi-legace issue 210

Revision ID: 1430c9aefcd7
Revises: ad81a3452b5d
Create Date: 2017-04-06 22:03:40.917628
"""

from alembic import op
import sqlalchemy as sa


revision = '1430c9aefcd7'
down_revision = 'ad81a3452b5d'
classifier = "Framework :: Jupyter"

def upgrade():
    op.execute(
        """
        INSERT into trove_classifiers (classifier, l2, l3, l4, l5) VALUES ('{classifier}', 0, 0, 0, 0);
        UPDATE trove_classifiers set l2=id where classifier='{classifier}';
        """.format(classifier=classifier)
    )
        
    pass


def downgrade():
    op.execute(
        """
        DELETE from release_classifiers where trove_id=(SELECT id from trove_classifiers where classifier='{classifier}');
        DELETE FROM trove_classifiers where classifier='{classifier}';
        """.format(classifier=classifier)
    )
