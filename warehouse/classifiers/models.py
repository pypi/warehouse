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

from sqlalchemy import Boolean, Column, ForeignKey, Integer, orm, Table, Text, sql

from warehouse import db
from warehouse.utils.attrs import make_repr


classification_deprecation_alternatives = Table(
    "classification_deprecation_alternatives",
    db.metadata,
    Column(
        "deprecated_classifier_id",
        Integer,
        ForeignKey("trove_classifiers.id", ondelete="CASCADE", onupdate="CASCADE"),
    ),
    Column(
        "alternative_classifier_id",
        Integer,
        ForeignKey("trove_classifiers.id", ondelete="CASCADE", onupdate="CASCADE"),
    ),
)


class Classifier(db.ModelBase):

    __tablename__ = "trove_classifiers"

    __repr__ = make_repr("classifier")

    id = Column(Integer, primary_key=True, nullable=False)
    classifier = Column(Text, unique=True)
    deprecated = Column(Boolean, nullable=False, server_default=sql.false())
    l2 = Column(Integer)
    l3 = Column(Integer)
    l4 = Column(Integer)
    l5 = Column(Integer)

    alternatives = orm.relationship(
        "Classifier",
        secondary=classification_deprecation_alternatives,
        primaryjoin=(
            classification_deprecation_alternatives.c.deprecated_classifier_id == id
        ),
        secondaryjoin=(
            classification_deprecation_alternatives.c.alternative_classifier_id == id
        ),
    )
