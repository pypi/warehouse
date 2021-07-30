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

from sqlalchemy import CheckConstraint, Column, Integer, Text

from warehouse import db
from warehouse.utils.attrs import make_repr


class Classifier(db.ModelBase):

    __tablename__ = "trove_classifiers"
    __tableargs__ = CheckConstraint(
        "classifier not ilike 'private ::%'",
        name="ck_disallow_private_top_level_classifier",
    )

    __repr__ = make_repr("classifier")

    id = Column(Integer, primary_key=True, nullable=False)
    classifier = Column(Text, unique=True)
